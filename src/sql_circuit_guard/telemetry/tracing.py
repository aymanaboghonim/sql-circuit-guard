"""Observability initialization and tracing configuration for sql-circuit-guard."""

import logging
import os
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import litellm  # type: ignore[import-not-found]
from langfuse import observe  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def init_telemetry() -> bool:
    """Initialize Langfuse telemetry and LiteLLM callbacks gracefully.

    Returns:
        bool: True if Langfuse environment variables are present and enabled.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        logger.info(
            "Langfuse API keys not found in environment. Running in offline/noop tracing mode."
        )
        return False

    try:
        # Register Langfuse as an automated callback target for LiteLLM
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
        logger.info("Langfuse telemetry callbacks successfully bound to LiteLLM.")
        return True
    except RuntimeError as exc:
        logger.warning(f"Failed to bind Langfuse callbacks: {exc}")
        return False


def trace_span(name: str | None = None) -> Callable[[F], F]:
    """Safe decorator wrapper around Langfuse @observe to prevent offline crashes.

    Args:
        name: Custom trace or span name.

    Returns:
        Callable: Wrapped function emitting OpenTelemetry spans when configured.
    """

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                # Use Langfuse native @observe decorator if enabled
                observed_fn = observe(name=name)(fn)
                return observed_fn(*args, **kwargs)
            except RuntimeError:
                # Execute original function without tracing if telemetry fails
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def update_trace_metadata(
    trace_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Update current execution trace context with custom metadata and tags."""
    try:
        from langfuse import langfuse_context

        langfuse_context.update_current_trace(
            user_id=user_id,
            tags=tags or [],
            metadata=metadata or {},
        )
    except RuntimeError:
        pass
