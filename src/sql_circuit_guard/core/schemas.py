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


class PromptGuardResult(BaseModel):
    """Result of deterministic natural-language prompt injection screening."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool = Field(
        ..., description="True if the prompt shows no DML/DDL or injection intent."
    )
    violated_rule: str | None = Field(
        default=None,
        description="Security rule triggered (e.g., 'DML_DDL_KEYWORD_DETECTED').",
    )
    error_message: str | None = Field(
        default=None,
        description="Human-readable description of the detected injection vector.",
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


class CircuitExecutionResult(BaseModel):
    """Full trace and outcome of the self-correcting text-to-SQL circuit."""

    model_config = ConfigDict(frozen=True)

    success: bool = Field(
        ..., description="True if query eventually passed AST and executed."
    )
    final_sql: str = Field(default="", description="The final executed SQL query.")
    reasoning: str = Field(
        default="", description="LLM architectural reasoning for the final query."
    )
    attempts_used: int = Field(
        default=0, description="Number of LLM generation attempts consumed."
    )
    execution_result: ExecutionResult | None = Field(
        default=None,
        description="Final SQLite tabular execution result.",
    )
    ast_validation: ASTValidationResult | None = Field(
        default=None,
        description="Final AST validation outcome.",
    )
    error_trail: list[str] = Field(
        default_factory=list,
        description="Chronological log of AST/DB errors encountered during retries.",
    )


class EvalTestCase(BaseModel):
    """Single evaluation scenario loaded from the JSON benchmark dataset."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique benchmark case ID (e.g., VAL-01).")
    category: str = Field(
        ...,
        description="Category: 'valid_read', 'adversarial', or 'hallucination_trap'.",
    )
    query: str = Field(..., description="Natural language question or attack payload.")
    expected_block: bool = Field(
        ..., description="True if AST guardrail MUST block query."
    )
    expected_min_rows: int = Field(
        default=0, description="Minimum expected rows returned."
    )


class EvalCaseResult(BaseModel):
    """Execution outcome of a single evaluation scenario."""

    model_config = ConfigDict(frozen=True)

    test_case_id: str
    category: str
    passed: bool
    blocked_by_ast: bool
    any_guardrail_blocked: bool = Field(
        default=False,
        description=(
            "True if any attempt in the circuit hit a deterministic guardrail "
            "block (prompt-level injection guard or AST security stop)."
        ),
    )
    self_corrected: bool
    attempts_used: int
    latency_ms: float
    error_summary: str | None = None


class EvalBenchmarkReport(BaseModel):
    """Aggregate quantitative metrics report for the entire benchmark suite."""

    model_config = ConfigDict(frozen=True)

    total_tests: int
    passed_tests: int
    execution_accuracy_rate: float = Field(
        description="Percentage of passed non-adversarial test cases."
    )
    adversarial_intent_rejection_rate: float = Field(
        description="Percentage of adversarial queries rejected by the circuit."
    )
    ast_mutation_execution_block_rate: float = Field(
        description="Percentage of adversarial queries where no mutation executed (invariant)."
    )
    self_correction_recovery_rate: float = Field(
        description="Percentage of failed queries corrected on retry."
    )
    mean_latency_ms: float
    mean_attempts_per_query: float
    results: list[EvalCaseResult]
