"""Unit tests for offline observability and tracing resilience."""

import pytest

from sql_circuit_guard.telemetry.tracing import (
    init_telemetry,
    trace_span,
    update_trace_metadata,
)


def test_init_telemetry_offline_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify telemetry init returns False without crashing when env vars are absent."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    success = init_telemetry()
    assert success is False


def test_trace_span_decorator_resilience() -> None:
    """Verify decorated functions execute normally in offline/noop mode."""

    @trace_span(name="test_span_execution")
    def add_numbers(a: int, b: int) -> int:
        return a + b

    result = add_numbers(10, 20)
    assert result == 30


def test_update_trace_metadata_noop_safety() -> None:
    """Verify trace metadata updates fail silently when no active trace exists."""
    # Should not raise an exception
    update_trace_metadata(
        trace_id="mock-trace-id",
        tags=["test-tag"],
        metadata={"env": "pytest"},
    )
