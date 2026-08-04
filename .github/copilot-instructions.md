# Project Rules & Constraints for `sql-circuit-guard`

## Architecture & Coding Principles
1. **No Monolithic LLM Frameworks**: Do NOT suggest or use `langchain`, `llama-index`, or high-level abstractions. Use native Python, `LiteLLM`, `Pydantic v2`, and `instructor`.
2. **Strict Decoupling**: Domain logic must never call vendor SDKs directly. All LLM calls must route through the `BaseLLMGateway` abstraction.
3. **Pydantic v2 First**: All LLM outputs and internal data contracts must use Pydantic v2 `BaseModel` with explicit typing.
4. **Deterministic Security**: SQL queries MUST be validated via `sqlglot` AST parsing before touching the database. Never rely on LLM prompts alone for security.
5. **Observability**: Every gateway call and AST verification step must be wrapped in OpenTelemetry / Langfuse spans.

## Target Models
- Local: `ibm/granite4.1:8b` via Ollama
- Cloud Fallback: `gemini-3.1-flash-lite` via LiteLLM (Strict limit: 10 RPM / 200k TPM)
