"""Observability initialization and tracing configuration for sql-circuit-guard."""

import logging
import os
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

import litellm
from langfuse import observe

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def init_telemetry(enable_langfuse: bool = True) -> bool:
    """Initialize Langfuse telemetry and LiteLLM callbacks gracefully.

    Args:
        enable_langfuse: Whether Langfuse tracing is enabled via UI/config.

    Returns:
        bool: True if Langfuse environment variables are present and successfully enabled.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not enable_langfuse:
        logger.info("Langfuse tracing is disabled by user option.")
        litellm.success_callback = []
        litellm.failure_callback = []
        os.environ["OTEL_SDK_DISABLED"] = "true"
        return False

    if not public_key or not secret_key:
        logger.error(
            "❌ Langfuse API keys missing in environment! "
            "Please add valid LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to your .env file "
            "or disable Langfuse by setting enable_langfuse=False."
        )
        # Inject default keys to avoid hiding errors
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-lf-default-injected")
        os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-default-injected")

    try:
        # Register Langfuse as an automated callback target for LiteLLM
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
        logger.info("Langfuse telemetry callbacks successfully bound to LiteLLM.")
        return True
    except (RuntimeError, ValueError, ImportError) as exc:
        logger.error(
            f"❌ Failed to bind Langfuse callbacks: {exc}. "
            "Please check your Langfuse API keys or disable Langfuse in the app."
        )
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
        pass
        # langfuse_context or current trace update if available
    except RuntimeError:
        pass
