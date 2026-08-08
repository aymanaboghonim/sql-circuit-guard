"""Resilience and edge-case tests for the circuit orchestrator and guardrails."""

import sqlite3
from pathlib import Path

import pytest

from sql_circuit_guard.core.schemas import QueryRequest, SQLGenerationOutput
from sql_circuit_guard.db.executor import SQLiteExecutor
from sql_circuit_guard.db.schema_inspector import SQLiteSchemaInspector
from sql_circuit_guard.gateway.llm_gateway import LiteLLMGateway
from sql_circuit_guard.guardrails.ast_guard import ASTGuardrail
from sql_circuit_guard.service.circuit_orchestrator import CircuitOrchestrationEngine


class RateLimitExhaustedGateway(LiteLLMGateway):
    """Simulates a persistent cloud rate-limit failure on every generation."""

    def generate_sql(self, prompt: str, schema_context: str) -> SQLGenerationOutput:
        raise RuntimeError(
            "Cloud fallback rate limit exceeded (10 RPM / 200k TPM). Request aborted."
        )


@pytest.fixture
def db_tools() -> tuple[SQLiteExecutor, SQLiteSchemaInspector]:
    """Provide local SQLite execution dependencies, skipping if the DB is absent."""
    db_path = Path("data/chinook.db")
    if not db_path.exists():
        pytest.skip("chinook.db missing.")
    return SQLiteExecutor(db_path), SQLiteSchemaInspector(db_path)


def test_circuit_handles_total_gateway_failure(
    db_tools: tuple[SQLiteExecutor, SQLiteSchemaInspector],
) -> None:
    """Gateway RuntimeError terminates the circuit without retries or exceptions."""
    executor, inspector = db_tools
    failing_gateway = RateLimitExhaustedGateway(enable_fallback=False)

    orchestrator = CircuitOrchestrationEngine(
        gateway=failing_gateway,
        db_executor=executor,
        schema_inspector=inspector,
    )

    request = QueryRequest(query="Show me all artists.", max_retries=2)
    result = orchestrator.execute_circuit(request)

    assert result.success is False
    assert result.attempts_used == 1
    assert "Cloud fallback rate limit exceeded" in result.error_trail[0]


def test_concurrent_read_only_connections(
    db_tools: tuple[SQLiteExecutor, SQLiteSchemaInspector],
) -> None:
    """Simultaneous read-only connections must not contend (no SQLITE_BUSY)."""
    _executor, _inspector = db_tools
    db_path = Path("data/chinook.db").resolve()

    conn1 = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn2 = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    cursor1 = conn1.cursor()
    cursor2 = conn2.cursor()

    cursor1.execute("SELECT COUNT(*) FROM Artist;")
    cursor2.execute("SELECT COUNT(*) FROM Invoice;")

    res1 = cursor1.fetchone()[0]
    res2 = cursor2.fetchone()[0]

    conn1.close()
    conn2.close()

    assert res1 > 0
    assert res2 > 0


@pytest.mark.parametrize(
    "payload",
    [
        "SELECT * FROM Customer; ATTACH DATABASE 'malicious.db' AS poison;",
        "SELECT * FROM Customer WHERE 1=1; PRAGMA writable_schema=ON;",
        "PRAGMA writable_schema=ON;",
    ],
    ids=["multi-statement-attach", "multi-statement-pragma", "pragma-root"],
)
def test_guardrail_rejects_injection_and_pragma_payloads(payload: str) -> None:
    """AST guardrail must fail closed on stacking, ATTACH, and PRAGMA attempts."""
    guard = ASTGuardrail(dialect="sqlite")
    result = guard.validate(payload)

    assert result.is_valid is False
    assert result.violated_rule in {
        "MULTI_STATEMENT_BLOCKED",
        "NON_SELECT_ROOT_BLOCKED",
    }
