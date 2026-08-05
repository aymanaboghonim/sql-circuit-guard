"""API integration tests for sql-circuit-guard service."""

from pathlib import Path

import pytest

from sql_circuit_guard.db.executor import SQLiteExecutor
from sql_circuit_guard.db.schema_inspector import SQLiteSchemaInspector


@pytest.fixture
def db_path():
    return Path("data/chinook.db")


def test_schema_inspector_methods(db_path):
    """Verify schema inspector methods work correctly."""
    inspector = SQLiteSchemaInspector(db_path=db_path)
    tables = inspector.get_table_names()
    assert "Artist" in tables
    assert "Album" in tables

    schema = inspector.get_table_schema("Artist")
    assert "columns" in schema
    assert any(col["name"] == "Name" for col in schema["columns"])


def test_db_executor_execution(db_path):
    """Verify database executor can run queries."""
    executor = SQLiteExecutor(db_path=db_path)
    result = executor.execute_query("SELECT count(*) FROM Artist")
    assert result.success
    assert result.rows[0][0] > 0
