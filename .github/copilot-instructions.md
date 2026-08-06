# Agent Execution Rules & Engineering Standards

---

## PART 1: Universal Agent Execution & Human-Paced Audit Protocol
*(Reusable across ALL projects to eliminate cognitive load and enforce single-step steering)*

### 1. Communication Rules (Strict Low-Cognitive-Load Constraints)
* **Micro-Reasoning Only:** Total text explanation per turn MUST NOT exceed **60 words**. No long walls of text, no deep chain-of-thought dumps.
* **No Code Sprawls:** Output ONLY the specific modified function or block—never reprint entire unchanged files.
* **Explicit Assumptions:** State system/codebase assumptions *before* executing tools or proposing diffs.

### 2. Mandatory Audit Format
Every single turn MUST follow this exact 4-line format before taking action:
* 🎯 **Intent:** [1 sentence explaining what you are trying to achieve]
* ⚠️ **Key Assumption:** [Max 2 bullet points on what you assume about the codebase/state]
* 🛠️ **Single Action:** [1 line describing the exact tool call or file diff you will run]
* 🛑 **Checkpoint:** "Waiting for approval to execute."

### 3. Step-and-Steer Control Loop
* **Single-Step Limit:** You are strictly forbidden from executing multiple tool calls or multi-file edits in a single turn.
* **Mandatory Pause:** Execute ONE action, emit the Audit Format, and STOP immediately to wait for human confirmation.

---

## PART 2: Universal AI Engineering Standards
*(Reusable architectural principles for robust, vendor-agnostic AI systems)*

1. **No Monolithic LLM Frameworks:** Do NOT suggest or use `langchain`, `llama-index`, or high-level magic abstractions. Use native Python, lightweight gateways (e.g., `LiteLLM`), and structured output wrappers (`instructor`, native tool calling).
2. **Strict Gateway Decoupling:** Domain logic must NEVER call vendor SDKs directly. All model calls must route through an abstract gateway interface (e.g., `BaseLLMGateway`).
3. **Pydantic v2 Contracts:** All LLM inputs, outputs, and internal system data boundaries must use Pydantic v2 `BaseModel` with explicit typing and validation.
4. **Deterministic Safety First:** Never rely on LLM prompts alone for system safety, validation, or access control. Security rules MUST be enforced by deterministic code, parsers, or AST guardrails.
5. **Observability Native:** Every model call, gateway transition, and safety check must be wrapped in OpenTelemetry / tracing spans (e.g., Langfuse / Arize Phoenix).

---

## PART 3: Project-Specific Configuration (`sql-circuit-guard`)
*(Plug project-specific models, guardrails, and constraints here)*

* **Project Name:** `sql-circuit-guard`
* **Deterministic Guardrail Tool:** `sqlglot` AST parsing (SQL MUST be validated read-only before touching the database).
* **Local Target Model:** `ibm/granite4.1:8b` via Ollama
* **Cloud Fallback Model:** `gemini-3.1-flash-lite` via LiteLLM (Strict limit: 10 RPM / 200k TPM)
