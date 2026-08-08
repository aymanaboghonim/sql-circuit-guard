# Operational Runbook: `sql-circuit-guard`

Troubleshooting procedures for the local stack (WSL2, RTX 3070, Docker Compose, Langfuse v4). Companion tooling:

- GPU/throughput profiling: `./scripts/profile_gpu.sh`
- Resilience test suite: `uv run pytest tests/test_resilience.py -v`

---

## 1. CUDA / Ollama Out-of-Memory (OOM) on RTX 3070

**Symptom:** Local model latency exceeds 10 000 ms, or Ollama logs `CUDA out of memory`. The RTX 3070 has 8 GB VRAM; concurrent model loads or an oversized context window can exceed it.

**Remediation:**
1. Check current VRAM usage:
   ```bash
   nvidia-smi --query-gpu=memory.used,memory.free --format=csv
   ```
2. Unload dormant Ollama models from VRAM (`keep_alive: 0` evicts immediately):
   ```bash
   curl -X POST http://localhost:11434/api/generate \
     -d '{"model": "ibm/granite4.1:8b", "keep_alive": 0}'
   ```
3. Restart the Ollama container to reset its runtime state:
   ```bash
   docker compose restart ollama
   ```
4. If a single model still OOMs at the default context, reduce the context size in Ollama's model settings before restarting.

---

## 2. Cloud Rate-Limit Throttling (HTTP 429)

**Symptom:** Logs report `Cloud fallback rate limit exceeded (10 RPM / 200k TPM). Request aborted.`

**Root cause:** The in-memory token bucket (`GateRateLimiter`, 10 RPM / 200k TPM) is exhausted, so the gateway aborts rather than hammering the provider.

**Remediation:**
1. Confirm whether requests actually reached the cloud: check the app logs and the Langfuse dashboard (`http://localhost:3001`) — the `attempts_used` value in the trace metadata shows whether the circuit consumed generation attempts.
2. Verify the local GPU model is healthy to reduce unnecessary cloud failover:
   ```bash
   curl -s http://localhost:11434/api/tags | head -c 200
   ```
3. To temporarily disable cloud fallback, set in `.env`:
   ```ini
   ENABLE_CLOUD_FALLBACK=false
   ```
   then restart the app (`docker compose restart app`).
4. The limiter is in-memory per process: a restart resets the buckets if throttling persists.

---

## 3. Stale Schema Cache After Database Replacement

**Symptom:** Generated SQL throws `no such table` or `no such column` after replacing `data/chinook.db`.

**Root cause:** `CircuitOrchestrationEngine` caches the DDL schema in memory (`_cached_schema`) for the process lifetime; it is not refreshed when the database file changes.

**Remediation:**
1. Replace `data/chinook.db` with the updated read-only SQLite database.
2. Restart the application service to invalidate the singleton schema cache:
   ```bash
   docker compose restart app
   ```
3. For a local (non-container) run, restart the `uv run python src/app.py` process instead.
