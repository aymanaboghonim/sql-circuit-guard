"""Core Pydantic v2 data contracts for sql-circuit-guard."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QueryRequest(BaseModel):
    """Incoming natural language query request from client or UI."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language question targeting the Chinook database.",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        le=3,
        description="Maximum self-correction retry turns allowed.",
    )


class SQLGenerationOutput(BaseModel):
    """Structured output expected from the LLM Gateway via Instructor."""

    model_config = ConfigDict(frozen=True)

    sql_query: str = Field(
        ...,
        description="The generated SQLite-compatible SQL query.",
    )
    reasoning: str = Field(
        ...,
        description="Brief architectural reasoning for schema tables and joins selected.",
    )


class ASTValidationResult(BaseModel):
    """Result of deterministic sqlglot AST verification."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool = Field(
        ..., description="True if query is strictly read-only SELECT."
    )
    sanitized_sql: str = Field(
        default="", description="Normalized SQL string if valid."
    )
    error_message: str | None = Field(
        default=None,
        description="Detailed security violation or syntax parse error.",
    )
    violated_rule: str | None = Field(
        default=None,
        description="Name of the security rule triggered (e.g., 'MUTATION_BLOCKED').",
    )


class ExecutionResult(BaseModel):
    """Final output from SQLite database execution."""

    model_config = ConfigDict(frozen=True)

    success: bool = Field(..., description="True if DB query executed successfully.")
    columns: list[str] = Field(
        default_factory=list, description="Returned column headers."
    )
    rows: list[tuple[Any, ...]] = Field(
        default_factory=list, description="Returned tuples."
    )
    execution_time_ms: float = Field(
        default=0.0, description="Query latency in milliseconds."
    )
    error: str | None = Field(
        default=None,
        description="Database driver error string if execution failed.",
    )
