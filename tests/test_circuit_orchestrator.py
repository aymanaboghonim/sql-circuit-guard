"""Unit tests verifying self-correction retry circuit logic."""

from pathlib import Path

import pytest

from sql_circuit_guard.core.schemas import (
    QueryRequest,
    SQLGenerationOutput,
)
from sql_circuit_guard.db.executor import SQLiteExecutor
from sql_circuit_guard.db.schema_inspector import SQLiteSchemaInspector
from sql_circuit_guard.service.circuit_orchestrator import CircuitOrchestrationEngine


class MockLLMGateway:
    """Mock gateway that simulates sequential failures followed by recovery."""

    def __init__(self, responses: list[SQLGenerationOutput]) -> None:
        self.responses = responses
        self.call_count = 0

    def generate_sql(self, prompt: str, schema_context: str) -> SQLGenerationOutput:
        """Return sequential canned responses to test retry loops."""
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        raise RuntimeError("MockLLMGateway exhausted configured responses.")


@pytest.fixture
def db_tools() -> tuple[SQLiteExecutor, SQLiteSchemaInspector]:
    """Return configured SQLite executor and schema inspector."""
    db_path = Path("data/chinook.db")
    if not db_path.exists():
        pytest.skip("chinook.db not found in data/ directory.")
    return SQLiteExecutor(db_path), SQLiteSchemaInspector(db_path)


def test_first_attempt_success(
    db_tools: tuple[SQLiteExecutor, SQLiteSchemaInspector],
) -> None:
    """Verify circuit completes on attempt 1 when valid SQL is generated."""
    executor, inspector = db_tools
    mock_gateway = MockLLMGateway(
        responses=[
            SQLGenerationOutput(
                sql_query="SELECT Name FROM Artist LIMIT 2;",
                reasoning="Select first two artists.",
            )
        ]
    )

    orchestrator = CircuitOrchestrationEngine(
        gateway=mock_gateway,  # type: ignore[arg-type]
        db_executor=executor,
        schema_inspector=inspector,
    )

    request = QueryRequest(query="Show me 2 artists.")
    result = orchestrator.execute_circuit(request)

    assert result.success is True
    assert result.attempts_used == 1
    assert len(result.error_trail) == 0
    assert result.execution_result is not None
    assert len(result.execution_result.rows) == 2


def test_ast_violation_recovery(
    db_tools: tuple[SQLiteExecutor, SQLiteSchemaInspector],
) -> None:
    """Verify circuit intercepts UPDATE mutation and corrects on attempt 2."""
    executor, inspector = db_tools
    mock_gateway = MockLLMGateway(
        responses=[
            SQLGenerationOutput(
                sql_query="UPDATE Artist SET Name = 'Hacked'; SELECT Name FROM Artist;",
                reasoning="Malicious mutation attempt.",
            ),
            SQLGenerationOutput(
                sql_query="SELECT Name FROM Artist LIMIT 1;",
                reasoning="Corrected to read-only SELECT.",
            ),
        ]
    )

    orchestrator = CircuitOrchestrationEngine(
        gateway=mock_gateway,  # type: ignore[arg-type]
        db_executor=executor,
        schema_inspector=inspector,
    )

    request = QueryRequest(query="Get one artist after attempting mutation.")
    result = orchestrator.execute_circuit(request)

    assert result.success is True
    assert result.attempts_used == 2
    assert len(result.error_trail) == 1
    assert "AST Guardrail Blocked" in result.error_trail[0]
    assert "MULTI_STATEMENT_BLOCKED" in result.error_trail[0]
    assert result.execution_result is not None
    assert len(result.execution_result.rows) == 1


def test_db_syntax_error_recovery(
    db_tools: tuple[SQLiteExecutor, SQLiteSchemaInspector],
) -> None:
    """Verify circuit catches SQLite column hallucination and corrects on attempt 2."""
    executor, inspector = db_tools
    mock_gateway = MockLLMGateway(
        responses=[
            SQLGenerationOutput(
                sql_query="SELECT NonExistentColumn FROM Artist LIMIT 1;",
                reasoning="Hallucinated column name.",
            ),
            SQLGenerationOutput(
                sql_query="SELECT ArtistId, Name FROM Artist LIMIT 1;",
                reasoning="Corrected column name using DDL schema.",
            ),
        ]
    )

    orchestrator = CircuitOrchestrationEngine(
        gateway=mock_gateway,  # type: ignore[arg-type]
        db_executor=executor,
        schema_inspector=inspector,
    )

    request = QueryRequest(query="Get one artist.")
    result = orchestrator.execute_circuit(request)

    assert result.success is True
    assert result.attempts_used == 2
    assert len(result.error_trail) == 1
    assert "Database Execution Error" in result.error_trail[0]
    assert result.execution_result is not None
    assert result.execution_result.success is True
