"""Self-correcting orchestrator circuit combining Gateway, AST Guardrail, and DB Executor."""

from langfuse import observe

from sql_circuit_guard.core.schemas import (
    ASTValidationResult,
    CircuitExecutionResult,
    QueryRequest,
    SQLGenerationOutput,
)
from sql_circuit_guard.db.executor import SQLiteExecutor
from sql_circuit_guard.db.schema_inspector import SQLiteSchemaInspector
from sql_circuit_guard.gateway.llm_gateway import BaseLLMGateway
from sql_circuit_guard.guardrails.ast_guard import ASTGuardrail
from sql_circuit_guard.guardrails.prompt_guard import PromptGuard


class CircuitOrchestrationEngine:
    """Orchestrates Text-to-SQL generation with AST verification and self-correction loops."""

    # Security-class violations terminate the circuit immediately.
    # Soft failures (DB execution errors) are the only retryable class.
    SECURITY_VIOLATION_RULES: frozenset[str] = frozenset(
        {
            "MUTATION_BLOCKED",
            "NON_SELECT_ROOT_BLOCKED",
            "MULTI_STATEMENT_BLOCKED",
        }
    )

    def __init__(
        self,
        gateway: BaseLLMGateway,
        db_executor: SQLiteExecutor,
        schema_inspector: SQLiteSchemaInspector,
        ast_guard: ASTGuardrail | None = None,
        prompt_guard: PromptGuard | None = None,
    ) -> None:
        self.gateway = gateway
        self.db_executor = db_executor
        self.schema_inspector = schema_inspector
        self.ast_guard = ast_guard or ASTGuardrail(dialect="sqlite")
        self.prompt_guard = prompt_guard or PromptGuard()
        self._cached_schema: str | None = None

    @observe(name="sql_circuit_execution", as_type="chain")  # type: ignore[untyped-decorator]
    def execute_circuit(self, request: QueryRequest) -> CircuitExecutionResult:
        """Execute the self-correcting Text-to-SQL generation and validation circuit.

        Deterministic prompt-level injection screening runs BEFORE any LLM call.
        Security-class AST violations (mutation, non-SELECT root, multi-statement)
        hard-stop the circuit without triggering self-correction retries. Only
        soft database execution errors are fed back into the bounded retry loop.
        """
        # Step 0: Deterministic prompt-level injection screening (untrusted input)
        prompt_result = self.prompt_guard.validate(request.query)
        if not prompt_result.is_valid:
            error_msg = (
                f"Prompt Guard Blocked -> Rule: {prompt_result.violated_rule} | "
                f"Error: {prompt_result.error_message}"
            )
            return CircuitExecutionResult(
                success=False,
                final_sql="",
                reasoning="",
                attempts_used=0,
                ast_validation=None,
                error_trail=[error_msg],
            )

        if self._cached_schema is None:
            self._cached_schema = self.schema_inspector.get_schema_ddl()

        # Tag root trace with query properties
        # update_trace_metadata(
        #     tags=["text-to-sql", "sqlite-chinook"],
        #     metadata={"max_retries": request.max_retries, "initial_query": request.query},
        # )

        current_prompt = request.query
        error_trail: list[str] = []
        max_attempts = request.max_retries + 1

        last_ast: ASTValidationResult | None = None
        last_generation: SQLGenerationOutput | None = None

        for attempt in range(1, max_attempts + 1):
            # Step 1: Generate SQL via LLM Gateway
            try:
                generation: SQLGenerationOutput = self.gateway.generate_sql(
                    prompt=current_prompt,
                    schema_context=self._cached_schema,
                )
                last_generation = generation
            except RuntimeError as exc:
                error_msg = f"Attempt {attempt}: LLM Gateway generation failure: {exc}"
                error_trail.append(error_msg)
                break

            # Step 2: Validate Generated SQL through Deterministic AST Guardrail
            ast_result: ASTValidationResult = self.ast_guard.validate(
                generation.sql_query
            )
            last_ast = ast_result

            if not ast_result.is_valid:
                error_msg = (
                    f"Attempt {attempt}: AST Guardrail Blocked -> "
                    f"Rule: {ast_result.violated_rule} | Error: {ast_result.error_message}"
                )
                error_trail.append(error_msg)

                # Security-class violations hard-stop the circuit: no retry loop
                # (prevents attempt exhaustion and adversarial query laundering).
                if ast_result.violated_rule in self.SECURITY_VIOLATION_RULES:
                    return CircuitExecutionResult(
                        success=False,
                        final_sql=generation.sql_query,
                        reasoning=generation.reasoning,
                        attempts_used=attempt,
                        ast_validation=ast_result,
                        error_trail=error_trail,
                    )

                # Feed AST failure back into prompt for correction
                current_prompt = self._format_retry_prompt(
                    original_query=request.query,
                    failed_sql=generation.sql_query,
                    error_feedback=str(ast_result.error_message),
                )
                continue

            # Step 3: Execute Validated SQL on SQLite Database
            db_result = self.db_executor.execute_query(ast_result.sanitized_sql)

            if not db_result.success:
                error_msg = (
                    f"Attempt {attempt}: Database Execution Error -> {db_result.error}"
                )
                error_trail.append(error_msg)

                # Feed DB driver failure back into prompt for correction
                current_prompt = self._format_retry_prompt(
                    original_query=request.query,
                    failed_sql=ast_result.sanitized_sql,
                    error_feedback=str(db_result.error),
                )
                continue

            # Step 4: Circuit Success
            return CircuitExecutionResult(
                success=True,
                final_sql=ast_result.sanitized_sql,
                reasoning=generation.reasoning,
                attempts_used=attempt,
                execution_result=db_result,
                ast_validation=ast_result,
                error_trail=error_trail,
            )

        # Failure: Exceeded maximum attempts without resolving errors
        return CircuitExecutionResult(
            success=False,
            final_sql=last_generation.sql_query if last_generation else "",
            reasoning=last_generation.reasoning if last_generation else "",
            attempts_used=len(error_trail),
            ast_validation=last_ast,
            error_trail=error_trail,
        )

    def _format_retry_prompt(
        self,
        original_query: str,
        failed_sql: str,
        error_feedback: str,
    ) -> str:
        """Construct a structured correction prompt for the LLM Gateway."""
        return (
            f"Original Question: {original_query}\n\n"
            f"Your previous query failed validation or execution:\n"
            f"FAILED SQL: {failed_sql}\n"
            f"ERROR REASON: {error_feedback}\n\n"
            "Analyze the schema and generate a corrected read-only SELECT query."
        )
