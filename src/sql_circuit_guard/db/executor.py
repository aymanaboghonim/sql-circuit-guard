"""Read-only SQLite database execution wrapper."""

import sqlite3
import time
from pathlib import Path
from typing import Any

from sql_circuit_guard.core.schemas import ExecutionResult


class SQLiteExecutor:
    """Executes validated SQL queries against SQLite in strict read-only mode."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found at: {self.db_path}")

    def execute_query(
        self, sql_query: str, params: tuple[Any, ...] = ()
    ) -> ExecutionResult:
        """Execute a read-only SQL query and return structured tabular results.

        Args:
            sql_query: Sanitize SQL string (must be validated by ASTGuardrail prior).
            params: Optional tuple of parameterized query arguments.

        Returns:
            ExecutionResult: Typed execution metrics, headers, and rows.
        """
        # Formulate SQLite Read-Only URI
        db_uri = f"file:{self.db_path}?mode=ro"
        start_time = time.perf_counter()

        try:
            # Connect using URI mode to enforce database-level read-only safety
            with sqlite3.connect(db_uri, uri=True, timeout=5.0) as conn:
                cursor = conn.cursor()
                cursor.execute(sql_query, params)

                columns = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )
                rows = cursor.fetchall()

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ExecutionResult(
                success=True,
                columns=columns,
                rows=rows,
                execution_time_ms=round(elapsed_ms, 2),
            )

        except sqlite3.Error as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ExecutionResult(
                success=False,
                execution_time_ms=round(elapsed_ms, 2),
                error=f"SQLite Execution Failure: {exc}",
            )
