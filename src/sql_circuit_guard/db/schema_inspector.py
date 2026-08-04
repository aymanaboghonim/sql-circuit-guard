"""Dynamic schema inspector for SQLite database context injection."""

import sqlite3
from pathlib import Path


class SQLiteSchemaInspector:
    """Extracts DDL schemas from SQLite databases for LLM prompt context."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).resolve()
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found at: {self.db_path}")

    def get_schema_ddl(self) -> str:
        """Extract formatted CREATE TABLE statements for all user tables.

        Returns:
            str: Clean DDL context block ready for LLM prompt injection.
        """
        db_uri = f"file:{self.db_path}?mode=ro"
        query = """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
        """

        try:
            with sqlite3.connect(db_uri, uri=True, timeout=5.0) as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                ddl_statements = [row[0] for row in cursor.fetchall() if row[0]]

            return "\n\n".join(ddl_statements)
        except sqlite3.Error as exc:
            raise RuntimeError(f"Failed to inspect SQLite schema: {exc}") from exc
