"""Unit tests for the SQLite read-only executor."""

from pathlib import Path

import pytest

from sql_circuit_guard.db.executor import SQLiteExecutor


@pytest.fixture
def db_executor() -> SQLiteExecutor:
    """Return an SQLiteExecutor bound to the local Chinook database."""
    db_path = Path("data/chinook.db")
    if not db_path.exists():
        pytest.skip("chinook.db not found in data/ directory.")
    return SQLiteExecutor(db_path=db_path)


def test_select_execution_success(db_executor: SQLiteExecutor) -> None:
    """Verify standard SELECT queries return columns and tuples correctly."""
    query = "SELECT ArtistId, Name FROM Artist LIMIT 3;"
    result = db_executor.execute_query(query)

    assert result.success is True
    assert result.columns == ["ArtistId", "Name"]
    assert len(result.rows) == 3
    assert result.error is None
    assert result.execution_time_ms > 0.0


def test_invalid_table_schema_error(db_executor: SQLiteExecutor) -> None:
    """Verify querying non-existent tables returns a clean Error string."""
    query = "SELECT * FROM NonExistentTable;"
    result = db_executor.execute_query(query)

    assert result.success is False
    assert result.error is not None
    assert "no such table" in result.error.lower()
