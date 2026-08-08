#!/usr/bin/env bash
# ==============================================================================
# GPU Memory & Throughput Profiler (WSL2 / Nvidia RTX 3070 8GB)
# ==============================================================================
# Reports VRAM state and measures token/s throughput for the local Ollama model.
# Usage: ./scripts/profile_gpu.sh
# Exits 0 on success; 1 when nvidia-smi is unavailable; 2 when Ollama is down.
# ==============================================================================
set -euo pipefail

echo "========================================================================"
echo "1. VERIFYING NVIDIA DRIVER & WSL2 CUDA ACCESS"
echo "========================================================================"
if ! command -v nvidia-smi &>/dev/null; then
    echo "ERROR: nvidia-smi not found. Check the WSL2 Nvidia driver installation."
    exit 1
fi
nvidia-smi --query-gpu=name,memory.total,memory.free,memory.used --format=csv,noheader

# Resolve the Ollama model id. LOCAL_MODEL_NAME may carry a LiteLLM provider
# prefix (ollama/...) which the Ollama HTTP API does not accept.
LOCAL_MODEL_NAME="${LOCAL_MODEL_NAME:-ibm/granite4.1:8b}"
MODEL_NAME="${LOCAL_MODEL_NAME#ollama/}"

echo ""
echo "========================================================================"
echo "2. CHECKING OLLAMA REACHABILITY"
echo "========================================================================"
if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "ERROR: Ollama is not reachable at http://localhost:11434."
    echo "Start it with: docker compose up -d ollama"
    exit 2
fi
echo "Ollama reachable. Model: ${MODEL_NAME}"

echo ""
echo "========================================================================"
echo "3. WARM-UP GENERATION"
echo "========================================================================"
curl -s -X POST http://localhost:11434/api/generate -d "{
  \"model\": \"${MODEL_NAME}\",
  \"prompt\": \"SELECT Name FROM Artist;\",
  \"stream\": false
}" >/dev/null

echo "Capturing VRAM footprint during inference..."
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv

echo ""
echo "========================================================================"
echo "4. THROUGHPUT BENCHMARK"
echo "========================================================================"
curl -s -X POST http://localhost:11434/api/generate -d "{
  \"model\": \"${MODEL_NAME}\",
  \"prompt\": \"Explain the differences between SQL INNER JOIN and LEFT JOIN in two paragraphs.\",
  \"stream\": false
}" | python3 -c "
import sys, json
res = json.load(sys.stdin)
eval_count = res.get('eval_count', 0)
eval_duration_ns = res.get('eval_duration', 1)
tps = eval_count / (eval_duration_ns / 1e9)
print(f'Total Tokens Generated: {eval_count}')
print(f'Generation Latency:     {eval_duration_ns / 1e6:.2f} ms')
print(f'Inference Throughput:   {tps:.2f} tokens/second')
"
