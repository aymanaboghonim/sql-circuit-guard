# SQL Circuit Guard

`sql-circuit-guard` is a deterministic, self-correcting Read-Only Text-to-SQL system designed to safely execute natural language queries against relational databases (using SQLite Chinook). It combines local model execution with cloud rate-limited fallback, dual-layer deterministic security (prompt-level injection screening + `sqlglot` AST guardrail validation), and robust OpenTelemetry / Langfuse observability.

## Architectural Principles

1. **No Monolithic LLM Frameworks**: Built using native Python, `LiteLLM`, `Pydantic v2`, and `instructor`. No heavy framework abstractions.
2. **Strict Decoupling**: Domain logic never calls vendor SDKs directly. All LLM interactions route through `BaseLLMGateway`.
3. **Deterministic Security**: Untrusted prompts are screened by a deterministic prompt-level injection guard **before** any LLM call, and generated SQL is validated via `sqlglot` AST parsing before touching the database. Security is enforced programmatically, never by prompt trust alone.
4. **Bounded Self-Correction Circuit**: Soft failures (database execution errors, hallucinated columns) are fed back as structured feedback prompts for up to $N=2$ retry turns. **Security-class violations (DML/DDL intent, multi-statement payloads, prompt injection) hard-stop the circuit immediately** — no retry loop, no query laundering.
5. **Observability**: Every gateway call and AST verification step is instrumented with OpenTelemetry and Langfuse tracing.

---

## Architecture Flow

```mermaid
graph TD
    User["User Natural Language Query"] --> PromptGuard["PromptGuard (Deterministic Injection Screen)"]
    PromptGuard -->|DML/DDL Intent Detected| HardStop1["🔴 HARD STOP - Blocked Pre-LLM"]
    PromptGuard -->|Valid| Orchestrator["Circuit Orchestrator"]
    Orchestrator --> Gateway["LiteLLM Gateway (Ollama / Cloud Fallback)"]
    Gateway --> ASTGuard["sqlglot AST Guardrail"]

    ASTGuard -->|Security Violation: Mutation / Multi-Statement / Non-SELECT| HardStop2["🔴 HARD STOP - No Retry, No Laundering"]
    ASTGuard -->|DB Execution Error| Loop["Self-Correction Loop (Max N=2)"]
    Loop --> Gateway

    ASTGuard -->|Valid SELECT Only| DB["SQLite Read-Only Executor"]
    DB --> Output["Structured Pydantic Result"]

    Orchestrator -.-> Tracing["OpenTelemetry / Langfuse Tracing"]
    Gateway -.-> Tracing
    ASTGuard -.-> Tracing
```

---

## User Interface & API Integration

- **Interactive Gradio Web App (`src/app.py`)**:
  - Dual-panel modern design with real-time execution results, formatted SQL blocks, architectural reasoning, and circuit telemetry diagnostics.
  - Quick-click sample prompts for immediate testing.
  - Interactive **Database Schema Explorer** tab to inspect tables (`Artist`, `Album`, `Track`, `Invoice`, etc.) and columns.
  - Dynamic **Langfuse Tracing Toggle** allowing users to enable or disable observability in real time.
- **Robust Integration Testing**:
  - Comprehensive unit test suite covering AST guardrails, circuit loops, database execution, LLM gateway, and telemetry.
  - API integration tests (`tests/test_api_service.py`) ensuring schema inspectors and database executors operate correctly.

---

## 🎥 Live Demo & Multi-Query Walkthrough

![Live Demo & Multi-Query Walkthrough](assets/demo_e2e.gif)

---

## Core Components
- **`guardrails/prompt_guard.py`**: Deterministic natural-language injection screen rejecting DML/DDL keyword intent and SQL comment/statement markers before any LLM call (closes the query-laundering gap).
- **`guardrails/ast_guard.py`**: Deterministic AST parser (`sqlglot`) ensuring single-statement read-only `SELECT` queries and blocking DDL/DML mutations. Security violations hard-stop the circuit.
- **`db/executor.py`**: SQLite database executor operating in strict read-only URI mode (`mode=ro`).
- **`db/schema_inspector.py`**: Extracts table schemas and DDL definitions for reliable LLM grounding.
- **`gateway/llm_gateway.py`**: `LiteLLMGateway` supporting local Ollama models (`ibm/granite4.1:8b`) and rate-limited cloud fallback (`gemini-3.1-flash-lite`) via `instructor`.
- **`gateway/rate_limiter.py`**: In-memory Token Bucket rate limiter enforcing Requests Per Minute (RPM) and Tokens Per Minute (TPM) limits.
- **`service/circuit_orchestrator.py`**: Manages the bounded self-correction loop, security-class hard-stops, and Langfuse trace decoration (`@observe`).
- **`service/evaluator.py`**: `SystemsEvaluationRunner` computing execution accuracy, adversarial rejection, AST mutation block, self-correction recovery, and mean latency metrics.
- **`service/run_evals.py`**: CLI entrypoint executing the 20-case benchmark suite and enforcing the zero-tolerance guardrail compliance gate.
- **`telemetry/tracing.py`**: OpenTelemetry tracing setup with offline resilience for Langfuse.

---

## Quick Start

1. **Clone Repository & Prerequisites**
   Ensure **Python 3.12+** and `uv` package manager are installed.

2. **Environment Configuration**
   Copy `.env.example` to `.env` and configure your API keys and local endpoint settings:
   ```bash
   cp .env.example .env
   ```

   | Variable | Description |
   | :--- | :--- |
   | `OLLAMA_API_BASE` | Local Ollama endpoint (default `http://localhost:11434`) |
   | `LOCAL_MODEL_NAME` | Primary local model, e.g. `ollama/ibm/granite4.1:8b` |
   | `GEMINI_API_KEY` | Cloud fallback API key (Gemini AI Studio free tier) |
   | `CLOUD_MODEL_NAME` | Cloud fallback model, e.g. `gemini/gemini-3.1-flash-lite` |
   | `ENABLE_CLOUD_FALLBACK` | `true`/`false` — route to cloud only when local fails |
   | `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | Self-hosted Langfuse telemetry |

3. **Install Dependencies**
   ```bash
   uv sync
   ```

4. **Launch the Interactive UI** (Gradio web app):
   ```bash
   uv run python src/app.py
   ```

---

## Running Tests

Run the test suite via `pytest`:
```bash
uv run pytest tests/ -v
```

---

## Automated Evaluation Suite

The system ships with a deterministic 20-case benchmark (`data/eval_benchmark.json`) across three categories — **valid read-only queries** (VAL-01..10), **adversarial mutation attacks** (ADV-01..07), and **hallucination traps** (HAL-01..03). Run the full suite against your local model:

```bash
uv run python -m sql_circuit_guard.service.run_evals
```

This executes every case through the real circuit, exports `reports/benchmark_report.json` and `reports/benchmark_report.md`, and enforces a **zero-tolerance guardrail compliance gate** — the CLI exits with code 1 if either security metric drops below 100%.

### Latest Benchmark Results (local `ibm/granite4.1:8b`)

| Metric | Result | Target Guardrail |
| :--- | :---: | :---: |
| **Execution Accuracy Rate** | `100.0%` | `≥ 85.0%` |
| **Adversarial Intent Rejection Rate** | `100.0%` | **`100.0%` (Zero Tolerance)** |
| **AST Mutation Execution Block Rate** | `100.0%` | **`100.0%` (Zero Tolerance)** |
| **Self-Correction Recovery Rate** | `100.0%` | `≥ 75.0%` |
| **Mean Latency per Query** | `4565.63 ms` | `< 3000 ms` |
| **Mean Generation Attempts** | `0.75` | `≤ 1.5` |

> **Latency note:** the mean is skewed by one reproducible model-inference stall (VAL-02, ~59s); the remaining 19 cases average ~2.4s. Full per-case logs: [reports/benchmark_report.md](reports/benchmark_report.md).

### Quality Gates

Every change is validated by the production pre-commit pipeline plus strict static typing:

```bash
uv run pre-commit run --all-files   # ruff lint/format, mypy --strict, gitleaks, check-json, actionlint
uv run mypy src/                    # strict static typing
uv run pytest tests/ -v             # full unit + integration suite (51 tests)
```

---

## License

This project is licensed under the terms of the MIT License.
