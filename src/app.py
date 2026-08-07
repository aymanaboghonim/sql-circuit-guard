"""Interactive Gradio UI and service entrypoint for sql-circuit-guard."""

import logging
import os
import sqlite3
from pathlib import Path

import gradio as gr
import pandas as pd
from dotenv import load_dotenv

from sql_circuit_guard.core.schemas import CircuitExecutionResult, QueryRequest
from sql_circuit_guard.db.executor import SQLiteExecutor
from sql_circuit_guard.db.schema_inspector import SQLiteSchemaInspector
from sql_circuit_guard.gateway.llm_gateway import LiteLLMGateway
from sql_circuit_guard.service.circuit_orchestrator import CircuitOrchestrationEngine
from sql_circuit_guard.telemetry.tracing import init_telemetry

# Initialize logging and environment configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sql_circuit_guard")
load_dotenv()


def build_orchestrator(
    enable_langfuse: bool | None = None,
) -> CircuitOrchestrationEngine:
    """Initialize core dependencies and construct the circuit orchestrator."""
    if enable_langfuse is None:
        enable_langfuse = os.getenv("ENABLE_LANGFUSE", "true").lower() == "true"
    init_telemetry(enable_langfuse=enable_langfuse)

    db_path = Path("data/chinook.db")
    if not db_path.exists():
        raise FileNotFoundError(
            f"Chinook database not found at {db_path.resolve()}. "
            "Ensure chinook.db is present in data/ directory."
        )

    db_executor = SQLiteExecutor(db_path=db_path)
    schema_inspector = SQLiteSchemaInspector(db_path=db_path)

    local_model = os.getenv("LOCAL_MODEL_NAME", "ollama/ibm/granite4.1:8b")
    cloud_model = os.getenv("CLOUD_MODEL_NAME", "gemini/gemini-3.1-flash-lite")
    fallback_enabled = os.getenv("ENABLE_CLOUD_FALLBACK", "true").lower() == "true"

    gateway = LiteLLMGateway(
        local_model=local_model,
        cloud_model=cloud_model,
        enable_fallback=fallback_enabled,
    )

    return CircuitOrchestrationEngine(
        gateway=gateway,
        db_executor=db_executor,
        schema_inspector=schema_inspector,
    )


# Instantiate singleton orchestrator engine
ORCHESTRATOR = build_orchestrator()


def run_query_circuit(
    query_text: str, max_retries: int, enable_langfuse: bool
) -> tuple[pd.DataFrame, str, str, str, str]:
    """Execute Text-to-SQL circuit and format UI component outputs.

    Args:
        query_text: Natural language user query.
        max_retries: Maximum self-correction retry turns.
        enable_langfuse: Whether Langfuse tracing is enabled.

    Returns:
        tuple containing:
            - DataFrame of SQL query results
            - Executed SQL string
            - Architectural reasoning text
            - Telemetry metadata markdown
            - Error trail markdown log
    """
    global ORCHESTRATOR
    # Rebuild orchestrator if langfuse setting changed
    ORCHESTRATOR = build_orchestrator(enable_langfuse=enable_langfuse)

    if not query_text or len(query_text.strip()) < 3:
        empty_df = pd.DataFrame()
        return empty_df, "", "", "### ⚠️ Error\nQuery too short.", ""

    request = QueryRequest(query=query_text.strip(), max_retries=int(max_retries))
    result: CircuitExecutionResult = ORCHESTRATOR.execute_circuit(request)

    # Panel 1: Data & Reasoning
    if result.execution_result and result.execution_result.success:
        df = pd.DataFrame(
            result.execution_result.rows,
            columns=result.execution_result.columns,
        )
    else:
        df = pd.DataFrame()

    # Panel 2: Telemetry & Circuit Diagnostics
    if result.success:
        status_badge = "🟢 **SUCCESS (AST & DB Validated)**"
    elif result.attempts_used == 0 and result.error_trail:
        # Deterministic guardrail hard-stop (PromptGuard runs pre-LLM,
        # consuming zero generation attempts).
        status_badge = "🛡️ **BLOCKED (Deterministic Guardrail)**"
    else:
        status_badge = "🔴 **CIRCUIT EXHAUSTED**"
    latency_ms = (
        result.execution_result.execution_time_ms if result.execution_result else 0.0
    )

    # Identify which guardrail (if any) blocked the query for the telemetry panel
    if result.ast_validation and not result.ast_validation.is_valid:
        guardrail_status = f"BLOCKED ({result.ast_validation.violated_rule})"
    elif not result.success and result.attempts_used == 0:
        guardrail_status = "BLOCKED (Prompt Guard)"
    elif result.success:
        guardrail_status = "PASSED"
    else:
        guardrail_status = "N/A"

    telemetry_md = (
        f"### Circuit Diagnostics\n"
        f"- **Status**: {status_badge}\n"
        f"- **Attempts Consumed**: `{result.attempts_used} / {int(max_retries) + 1}`\n"
        f"- **DB Execution Latency**: `{latency_ms:.2f} ms`\n"
        f"- **Guardrail**: `{guardrail_status}`"
    )

    if result.error_trail:
        error_md = "### Error Trail & Retry History\n" + "\n".join(
            f"- `{err}`" for err in result.error_trail
        )
    else:
        error_md = "### Error Trail\n*No validation or execution errors encountered.*"

    return df, result.final_sql, result.reasoning, telemetry_md, error_md


def get_schema_summary() -> str:
    """Retrieve formatted database schema overview for user guidance."""
    try:
        tables = ORCHESTRATOR.schema_inspector.get_table_names()
        summary_lines = ["### 📊 Database Schema Summary (Chinook DB)"]
        for table in tables:
            schema_info = ORCHESTRATOR.schema_inspector.get_table_schema(table)
            cols = [col["name"] for col in schema_info.get("columns", [])]
            summary_lines.append(f"- **{table}**: `{', '.join(cols)}`")
        return "\n".join(summary_lines)
    except (sqlite3.Error, RuntimeError, ValueError) as e:
        return f"*(Schema summary unavailable: {e})*"


def create_ui() -> gr.Blocks:
    """Construct professional dual-panel Gradio interface with modern UX."""
    custom_css = """
    .gradio-container {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .header-box {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        color: #ffffff !important;
        padding: 24px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .header-box h1, .header-box h3, .header-box p, .header-box span, .header-box strong {
        color: #ffffff !important;
    }
    .card-panel {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px;
    }
    """

    demo = gr.Blocks(title="SQL-Circuit-Guard | Secure Text-to-SQL", css=custom_css)
    with demo:
        with gr.Row(elem_classes="header-box"):
            gr.Markdown(
                "# 🛡️ SQL-Circuit-Guard\n"
                "### Secure, Deterministic Read-Only Text-to-SQL Execution & Circuit Guardrail Engine\n"
                "Local Ollama (`ibm/granite4.1:8b`) with resilient Cloud Fallback & strict `sqlglot` AST Security Guardrails."
            )

        with gr.Tabs():
            with gr.TabItem("🚀 Query Execution & Circuit"):
                with gr.Row():
                    with gr.Column(scale=3):
                        query_input = gr.Textbox(
                            label="Natural Language Query",
                            placeholder=(
                                "e.g., Show me the top 5 artists by total album count."
                            ),
                            lines=2,
                        )

                        # Example queries prompt helper
                        gr.Markdown("💡 **Quick Click Examples:**")
                        with gr.Row():
                            ex1 = gr.Button("Top 5 Artists by Albums", size="sm")
                            ex2 = gr.Button("List Top 10 Invoices by Total", size="sm")
                            ex3 = gr.Button("Count Tracks per Genre", size="sm")

                    with gr.Column(scale=1):
                        retry_slider = gr.Slider(
                            minimum=0,
                            maximum=3,
                            value=2,
                            step=1,
                            label="Max Self-Correction Retries",
                        )
                        langfuse_toggle = gr.Checkbox(
                            label="Enable Langfuse Tracing",
                            value=os.getenv("ENABLE_LANGFUSE", "true").lower()
                            == "true",
                        )
                        submit_btn = gr.Button(
                            "⚡ Execute Circuit", variant="primary", size="lg"
                        )

                with gr.Row():
                    # Panel 1: SQL Output & Data Table
                    with gr.Column(scale=2):
                        gr.Markdown("### 📋 Panel 1: Execution Results & Reasoning")
                        sql_output = gr.Code(
                            label="Validated Read-Only SQL", language="sql"
                        )
                        reasoning_output = gr.Textbox(
                            label="Architectural Reasoning", lines=2
                        )
                        results_table = gr.Dataframe(
                            label="Query Results Table", wrap=True, max_height=400
                        )

                    # Panel 2: Telemetry & Resilience Diagnostics
                    with gr.Column(scale=1):
                        gr.Markdown("### 🔬 Panel 2: Circuit Diagnostics & Telemetry")
                        telemetry_display = gr.Markdown()
                        error_trail_display = gr.Markdown()

                # Wire example buttons
                # mypy's cold cache cannot resolve gradio 6.22.0 stub instance
                # methods (see button.pyi); unused-ignore is disabled in
                # pyproject.toml so these suppression comments are safe everywhere.
                ex1.click(  # type: ignore[attr-defined]
                    lambda: "Show me the top 5 artists by total album count.",
                    outputs=query_input,
                )
                ex2.click(  # type: ignore[attr-defined]
                    lambda: "Show top 10 invoices by total amount.", outputs=query_input
                )
                ex3.click(  # type: ignore[attr-defined]
                    lambda: "Count how many tracks exist for each genre.",
                    outputs=query_input,
                )

            with gr.TabItem("📊 Database Schema Explorer"):
                gr.Markdown(
                    "Inspect available database tables and schema definitions to help craft precise natural language queries."
                )
                schema_markdown = gr.Markdown(get_schema_summary())
                refresh_schema_btn = gr.Button("🔄 Refresh Schema Info", size="sm")
                refresh_schema_btn.click(  # type: ignore[attr-defined]
                    fn=get_schema_summary, outputs=schema_markdown
                )

        # Wire event handlers
        submit_btn.click(  # type: ignore[attr-defined]
            fn=run_query_circuit,
            inputs=[query_input, retry_slider, langfuse_toggle],
            outputs=[
                results_table,
                sql_output,
                reasoning_output,
                telemetry_display,
                error_trail_display,
            ],
        )

    return demo


if __name__ == "__main__":
    app = create_ui()
    app.launch(
        server_name="0.0.0.0",
        # PaaS platforms (Render, etc.) inject PORT; fall back to the default 7860.
        server_port=int(os.getenv("PORT", "7860")),
        # Share links are opt-in (GRADIO_SHARE=true); hosted platforms provide
        # their own public URL and must not spawn a gradio share session.
        share=os.getenv("GRADIO_SHARE", "false").lower() == "true",
    )
