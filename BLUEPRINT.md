# Engineering Blueprint: `sql-circuit-guard`

Deterministic, Self-Correcting Read-Only Text-to-SQL System with AST Guardrails and Local/Cloud LLM Fallback.

---

## 1. System Vision & Objective

### 1.1 Business Problem
Deploying natural language to SQL interfaces in production environments introduces critical security and stability vectors:
* **Unsafe Data Mutation:** LLMs can generate mutating queries (`DELETE`, `DROP`, `UPDATE`, `INSERT`) causing irreversible data corruption.
* **Non-Deterministic Failures:** Runtime SQL syntax or schema mismatch errors occur unpredictably, degrading reliability without automated recovery.
* **Operational Cost & Rate Bottlenecks:** Uncontrolled retry loops on cloud APIs hit strict rate limits (e.g., 10 RPM / 200k TPM) or generate unsustainable operational expenses.

### 1.2 System Objective
`sql-circuit-guard` provides a decoupled, fault-tolerant Text-to-SQL engine. It executes natural language queries against relational databases by combining deterministic Abstract Syntax Tree (AST) parsing, bounded self-correction loops, local-first LLM execution (RTX 3070 8GB), and telemetry-backed cloud fallback options.

---

## 2. Core Architectural Constraints & System Boundaries

* **Local Hardware Footprint:** Primary inference targeted at quantized 7B/8B parameter models (e.g., `ibm/granite4.1:8b` via Ollama) running on an Nvidia RTX 3070 (8GB VRAM) under WSL2.
* **Cloud Rate Limits:** Secondary cloud providers constrained to strict token bucket rate limits (Max 10 RPM / 200k TPM).
* **Deterministic Guardrail First:** No SQL query is executed without prior AST validation.
* **Dataset Zero-Scraping Requirement:** Standard relational dataset (SQLite Chinook DB) packaged locally.
* **Telemetry First:** Every generation step, AST check, DB execution, and retry loop must emit OpenTelemetry/Langfuse traces.

---

## 3. Technology Stack

* **Language Runtime:** Python 3.12+
* **Environment & Package Management:** `uv`
* **Local LLM Server:** `Ollama` (running GGUF/EXL2 quantized models)
* **LLM Abstraction & Schema Parsing:** `LiteLLM` + `Pydantic v2` + `Instructor`
* **AST Parser & Guardrail:** `sqlglot`
* **Relational Engine:** `SQLite3` (Chinook Sample Database)
* **Observability & Tracing:** Self-hosted `Langfuse` or `Arize Phoenix` via OpenTelemetry
* **UI/Service Layer:** `FastAPI` + `Gradio`
* **Containerization:** `Docker` & `Docker Compose`

---

## 4. End-to-End System Flow

```
┌─────────────────┐
│ User Query (NL) │
└────────┬────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│               LLM Gateway (LiteLLM)                    │
│ Primary: Local Ollama (Qwen 2.5 7B)                    │
│ Fallback: Rate-Limited Cloud API (e.g., `gemini-3.1-flash-lite` - 10 RPM / 200k TPM / 400 RPD)   │
└────────┬───────────────────────────────────────────────┘
         │ (Generates SQL String)
         ▼
┌────────────────────────────────────────────────────────┐
│            Deterministic AST Guardrail                 │
│ Engine: sqlglot                                        │
│ Rules: 1. Expression == SELECT                         │
│        2. Mutating AST Nodes == Forbidden              │
│        3. Table/Column Schema Whitelist Check          │
└────────┬───────────────────────────────────────────────┘
         │
         ├──► [FAIL: Security Mutation Violation] ──► Block Query & Return Error
         │
         └──► [PASS: Read-Only Validated]
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│               SQLite Engine Execution                  │
└────────┬───────────────────────────────────────────────┘
         │
         ├──► [FAIL: DB Syntax / Schema Error]
         │          │
         │          ▼
         │   ┌───────────────────────────────────────────┐
         │   │ Self-Correction Circuit Loop (Max 2 turns)│
         │   │ Appends SQL + Error Message to Context    │
         │   └──────┬────────────────────────────────────┘
         │          │
         │          └─► Route back to LLM Gateway
         │
         └──► [SUCCESS: Results Returned]
                    │
                    ▼
┌────────────────────────────────────────────────────────┐
│ Output Formatting + Full Trace Logged to Langfuse      │
└────────────────────────────────────────────────────────┘
```

---

## 5. Phased Implementation Roadmap

### Phase 0: Repository Setup & Engineering Harness
**Goal:** Establish workspace constraints, dependency management, and local development environments.

1. **Repository & Tooling Initialization:**
   * Initialize repository using `uv`: `uv init sql-circuit-guard`.
   * Configure `.python-version` to `3.12`.
   * Configure project tools: `ruff` (linting/formatting), `pytest`, `pydantic`.
2. **Environment & AI Copilot Instruction Rules:**
   * Create `.github/copilot-instructions.md` containing decoupling rules, Pydantic v2 requirement, and OTel/tracing guidelines.
3. **Repository Directory Layout:**
   ```text
   sql-circuit-guard/
   ├── .github/
   │   └── copilot-instructions.md
   ├── src/
   │   ├── sql_circuit_guard/
   │   │   ├── core/           # Interfaces, Pydantic schemas, Config
   │   │   ├── gateway/        # LiteLLM/Ollama wrapper & rate-limit logic
   │   │   ├── guardrails/     # sqlglot AST verification rules
   │   │   ├── db/             # SQLite connection & execution
   │   │   ├── telemetry/      # Langfuse tracing & OTel spans
   │   │   └── service/        # Circuit-breaker flow orchestrator
   │   └── app.py              # Gradio / API entrypoint
   ├── tests/                  # Unit, Integration, and Guardrail tests
   ├── data/                   # Chinook SQLite database
   ├── docker/                 # Container configs
   ├── docker-compose.yml
   ├── pyproject.toml
   └── README.md
   ```

---

### Phase 1: Core Schemas, AST Guardrail, & Database Layer
**Goal:** Implement the execution engine and security validation mechanisms without LLM dependencies.

1. **Pydantic Contract Definitions:**
   * Define `QueryRequest`, `SQLGenerationOutput`, `ASTValidationResult`, and `ExecutionResult` models using Pydantic v2.
2. **Deterministic AST Parser (`sqlglot`):**
   * Write `ASTGuardrail` class that parses raw SQL strings into syntax trees.
   * Enforce restrictions: Must be `sqlglot.exp.Select`, must not contain `Insert`, `Update`, `Delete`, `Drop`, `Alter`, or multiple statements in a single payload.
3. **Database Execution Wrapper:**
   * Download and mount `chinook.db` in `data/`.
   * Implement `DBExecutor` with read-only SQLite connections (`file:chinook.db?mode=ro`).
   * Unit test DB execution against valid queries and verify security exceptions on forced mutations.

---

### Phase 2: Decoupled LLM Gateway & Self-Correction Circuit
**Goal:** Integrate model inference with a bounded error-handling loop.

1. **Abstract LLM Gateway Interface:**
   * Define `BaseLLMGateway` interface protocol.
   * Implement `LiteLLMGateway` supporting local Ollama (`ibm/granite4.1:8b`) and Cloud providers.
   * Implement token bucket rate limiter to keep Cloud execution under 10 RPM / 200k TPM.
2. **Self-Correction Orchestrator:**
   * Build `CircuitOrchestrationEngine`.
   * Sequence: `NL Query` $\rightarrow$ `LLM Generation` $\rightarrow$ `AST Check` $\rightarrow$ `DB Exec`.
   * If AST check or DB execution fails, capture exception string, construct a feedback message, and invoke a retry. Set absolute maximum attempt counter $N=2$.

---

### Phase 3: Observability & Telemetry Integration
**Goal:** Instrument end-to-end tracing across all processing nodes.

1. **Observability Stack Infrastructure:**
   * Add self-hosted `Langfuse` service to `docker-compose.yml` (or set up API key for managed instance).
2. **Telemetry Instrumentation:**
   * Decorate Gateway calls with execution metadata (model version, prompt tokens, completion tokens, latency).
   * Wrap AST validation and SQLite execution nodes in OpenTelemetry trace spans.
   * Trace multi-turn self-correction loops as nested sub-spans to monitor total cost and latency per NL query.

---

### Phase 4: Application Layer & Docker Containerization
**Goal:** Containerize the full service ecosystem for local reproduction.

1. **User Interface (`Gradio`):**
   * Build a minimalist dual-panel UI:
     * Panel 1: Natural Language input + generated SQL + execution results table.
     * Panel 2: Live trace metadata (AST Pass/Fail status, Retry Attempts, Latency, Token Usage).
2. **Multi-Stage Docker Setup:**
   * Build multi-stage `Dockerfile` leveraging `uv` for reproducible image building.
   * Write `docker-compose.yml` orchestrating:
     * `app`: Python service + Gradio UI.
     * `ollama`: Local GPU runner (configured with Nvidia container toolkit support for RTX 3070).
     * `langfuse`: Telemetry server.

---

### Phase 5: Automated Evaluation Suite
**Goal:** Measure system performance on standard test inputs.

1. **Eval Dataset Configuration:**
   * Construct a benchmark set of 20 natural language questions targeting Chinook DB (ranging from simple joins to aggregation queries).
2. **Eval Pipeline Execution:**
   * Run evaluation suite to compute metrics:
     * **Exact Match / Execution Accuracy Rate** (%)
     * **AST Mutation Block Rate** (%)
     * **Self-Correction Recovery Success Rate** (%)
     * **Mean Latency per Query** (Local vs. Cloud Fallback)

---

### Phase 6: Static Documentation & CI
**Goal:** Publish system artifacts and enforce quality gates.

1. **GitHub Pages Documentation Site:**
   * Deploy static documentation site containing architecture diagrams, component specifications, and exported Langfuse trace visualizers.
2. **Continuous Integration:**
   * Enforce `ruff`, `mypy`, and `pytest` via GitHub Actions on every push and pull request.
