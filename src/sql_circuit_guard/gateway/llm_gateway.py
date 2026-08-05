"""Decoupled LLM Gateway utilizing LiteLLM and Instructor for structured generation."""

from typing import Any, Protocol, TypeVar

import instructor
import langfuse
from litellm import completion
from pydantic import BaseModel

# Patch langfuse version attribute if missing
if not hasattr(langfuse, "version"):
    import langfuse._version as version

    langfuse.version = version

from sql_circuit_guard.core.schemas import SQLGenerationOutput
from sql_circuit_guard.gateway.rate_limiter import GateRateLimiter

T = TypeVar("T", bound=BaseModel)


class BaseLLMGateway(Protocol):
    """Abstract protocol defining the LLM Gateway contract."""

    def generate_sql(self, prompt: str, schema_context: str) -> SQLGenerationOutput:
        """Generate a structured SQL query from natural language."""
        ...


class LiteLLMGateway:
    """Production gateway handling local inference and rate-limited cloud fallback."""

    def __init__(
        self,
        local_model: str = "ollama/ibm/granite4.1:8b",
        cloud_model: str = "gemini/gemini-3.1-flash-lite",
        enable_fallback: bool = True,
    ) -> None:
        self.local_model = local_model
        self.cloud_model = cloud_model
        self.enable_fallback = enable_fallback
        self.rate_limiter = GateRateLimiter(max_rpm=10, max_tpm=200_000)

        # Patch LiteLLM completion client with Instructor for Pydantic schema validation
        self.client = instructor.from_litellm(completion)

    def generate_sql(self, prompt: str, schema_context: str) -> SQLGenerationOutput:
        """Execute text-to-SQL generation against local model, failing over to Cloud.

        Args:
            prompt: User natural language request or retry correction prompt.
            schema_context: DDL schema definition of the target tables.

        Returns:
            SQLGenerationOutput: Typed Pydantic object containing sql_query and reasoning.
        """
        system_instruction = (
            "You are a deterministic SQLite SQL engineer. "
            "Generate ONLY valid read-only SELECT queries based on the provided schema. "
            f"\n\nDATABASE SCHEMA:\n{schema_context}"
        )

        messages: list[Any] = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]

        try:
            # Primary Execution: Local GPU (RTX 3070 via Ollama)
            return self._call_model(model_name=self.local_model, messages=messages)
        except Exception as local_exc:
            if not self.enable_fallback:
                raise RuntimeError(
                    f"Local model generation failed: {local_exc}"
                ) from local_exc

            # Check rate limiter before invoking Cloud Fallback
            if not self.rate_limiter.acquire(estimated_tokens=1500):
                raise RuntimeError(
                    "Cloud fallback rate limit exceeded (10 RPM / 200k TPM). Request aborted."
                ) from local_exc

            # Secondary Execution: Cloud Free-Tier Fallback
            return self._call_model(model_name=self.cloud_model, messages=messages)

    def _call_model(
        self, model_name: str, messages: list[dict[str, str]]
    ) -> SQLGenerationOutput:
        """Invoke Instructor schema-validated completion."""
        # Convert messages to the expected format with explicit typing
        formatted_messages: list[Any] = [
            {"role": "system", "content": messages[0]["content"]},
            {"role": "user", "content": messages[1]["content"]},
        ]
        response: SQLGenerationOutput = self.client.chat.completions.create(
            model=model_name,
            messages=formatted_messages,
            response_model=SQLGenerationOutput,
            temperature=0.0,
            max_tokens=1024,
        )
        return response
