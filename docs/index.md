---
layout: default
title: SQL-Circuit-Guard — Architecture & Benchmarks
---

# SQL-Circuit-Guard

Deterministic, self-correcting read-only Text-to-SQL with `sqlglot` AST guardrails, a bounded retry circuit, and local GPU / rate-limited cloud fallback routing. No SQL string touches the SQLite engine unless it is verified as a single-statement, read-only `SELECT`.

- Source: [github.com/aymanaboghonim/sql-circuit-guard](https://github.com/aymanaboghonim/sql-circuit-guard)
- Benchmark artifacts: [`reports/benchmark_report.json`](https://github.com/aymanaboghonim/sql-circuit-guard/blob/main/reports/benchmark_report.json) · [`reports/benchmark_report.md`](https://github.com/aymanaboghonim/sql-circuit-guard/blob/main/reports/benchmark_report.md)
- Operations: [`docs/RUNBOOK.md`](https://github.com/aymanaboghonim/sql-circuit-guard/blob/main/docs/RUNBOOK.md)

<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
  mermaid.initialize({ startOnLoad: true, theme: "default" });
</script>

## 1. Execution Flow

<pre class="mermaid">
graph TD
    User["User NL Query"] --> PG["PromptGuard (deterministic injection screen)"]
    PG -->|"DML/DDL intent or SQL markers"| HARD1["BLOCKED pre-LLM · attempts = 0"]
    PG -->|clean| ORCH["Circuit OrchestrationEngine"]
    ORCH --> GW["LiteLLMGateway (instructor + Pydantic v2)"]
    GW -->|"primary: ollama/ibm/granite4.1:8b"| AST["ASTGuardrail (sqlglot)"]
    GW -->|"rate-limited fallback: gemini/*"| AST
    AST -->|"security violation"| HARD2["BLOCKED · no retry, no laundering"]
    AST -->|"valid single-statement SELECT"| DB["SQLite executor (mode=ro)"]
    DB -->|"syntax/schema error"| RETRY["Self-correction loop (max N=2)"]
    RETRY -->|"annotated error feedback"| GW
    DB -->|"success"| OUT["Tabular results + Pydantic result"]
    ORCH -.->|"@observe"| OTel["OpenTelemetry / Langfuse"]
    GW -.-> OTel
    AST -.-> OTel
</pre>

## 2. Security Rule Matrix

Security is enforced by deterministic code — never by LLM judgment. Two layers gate execution.

### Prompt screening (`guardrails/prompt_guard.py`) — pre-LLM

| Attack vector | Detection | Enforcement | Rule code |
| :--- | :--- | :--- | :--- |
| DML/DDL keyword intent (`DROP`, `DELETE`, `UPDATE`, `INSERT`, …) | keyword scan | Request blocked before any model call | `DML_DDL_KEYWORD_DETECTED` |
| SQL injection markers (`;`, `--`, `/*`) | marker scan | Request blocked before any model call | `SQL_MARKER_DETECTED` |

### AST validation (`guardrails/ast_guard.py`) — post-LLM, pre-execution

| Input | `sqlglot` AST check | Enforcement | Rule code |
| :--- | :--- | :--- | :--- |
| Mutation statements | `Insert`/`Update`/`Delete`/`Drop`/`Alter`/`Create`/`Command`/`Transaction` node detection | Execution blocked, hard stop | `MUTATION_BLOCKED` |
| Multiple statements | `sqlglot.parse` returns > 1 non-`None` statement | Execution blocked, hard stop | `MULTI_STATEMENT_BLOCKED` |
| Non-`SELECT` root | root expression is not `exp.Select` | Execution blocked, hard stop | `NON_SELECT_ROOT_BLOCKED` |
| Malformed SQL | `ParseError` during parse | Execution blocked | `SYNTAX_PARSE_ERROR` |
| Empty payload | empty string after strip | Execution blocked | `EMPTY_QUERY` |
| Read-only `SELECT` | single `Select` root, no mutation nodes | Transpiled to SQLite dialect and executed | pass |

A third, engine-level layer backs both: the SQLite connection is opened with `mode=ro`, so the database itself rejects any write.

## 3. Rate Limiting

`GateRateLimiter` (token bucket, monotonic clock) caps cloud fallback traffic before any request reaches the provider: **10 requests/min** and **200k tokens/min**. A rejected fallback raises a `RuntimeError` and the request is aborted — the limiter is a deterministic gate, not a probabilistic one.

## 4. Tracing Hierarchy

Every execution emits a chain trace (`@observe`, name `sql_circuit_execution`) to Langfuse:

```text
[Trace] sql_circuit_execution (chain)
  ├── [Span] PromptGuard screening
  ├── [Span] LLM gateway generation (model: local or fallback)
  ├── [Span] AST guardrail validation (engine: sqlglot)
  └── [Span] SQLite read-only execution (uri: file:chinook.db?mode=ro)
        └── [Retry sub-span] (on syntax/schema error, up to N=2)
```

## 5. Benchmark Results

20-case suite (`data/eval_benchmark.json`): 10 valid reads (VAL), 7 adversarial mutation attacks (ADV), 3 hallucination traps (HAL). Snapshot `2026-08-06`, model `ibm/granite4.1:8b` (Ollama, local), commit `de6ee95`. Full per-case data: [`reports/benchmark_report.md`](https://github.com/aymanaboghonim/sql-circuit-guard/blob/main/reports/benchmark_report.md).

| Metric | Result | Target |
| :--- | :---: | :---: |
| Execution accuracy rate | `100.0%` | `≥ 85.0%` |
| Adversarial intent rejection rate | `100.0%` | `100.0%` (zero tolerance) |
| AST mutation execution block rate | `100.0%` | `100.0%` (zero tolerance) |
| Self-correction recovery rate | `100.0%` | `≥ 75.0%` |
| Mean latency per query | `4565.63 ms` | `< 3000 ms` |
| Mean generation attempts | `0.75` | `≤ 1.5` |

Latency note: the mean is skewed by one reproducible model-inference stall (VAL-02, ~59 s); the remaining 19 cases average ~2.4 s. The eval CLI (`uv run python -m sql_circuit_guard.service.run_evals`) exits non-zero if either security metric drops below 100%.

## 6. Quality Gates

| Gate | Command |
| :--- | :--- |
| Lint + format | `uv run ruff check src/ tests/` · `uv run ruff format --check src/ tests/` |
| Static typing (strict) | `uv run mypy src/` |
| Tests | `uv run pytest tests/ -v` |
| Pre-commit (ruff, mypy, gitleaks, actionlint) | `uv run pre-commit run --all-files` |
| CI (on push/PR) | `.github/workflows/ci.yml` |
