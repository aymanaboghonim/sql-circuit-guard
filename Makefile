# ==============================================================================
# SQL-Circuit-Guard: Developer Interface
# ==============================================================================
# Unified entrypoints for the common workflows. Run `make help` for the list.
#
# Services (Docker Compose):
#   - Gradio Web UI:      http://localhost:7860
#   - Langfuse Dashboard: http://localhost:3001  (v4 canonical stack)
#
# First boot (pull the local model into the Ollama container, ~5.3 GB):
#   docker compose up -d ollama
#   docker exec sql_circuit_guard_ollama ollama pull ibm/granite4.1:8b
# ==============================================================================
.PHONY: help install format lint test eval up down logs profile clean clean-all

PYTHON := uv run python
PYTEST := uv run pytest
RUFF := uv run ruff

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Sync dependencies and install pre-commit hooks
	uv sync --frozen
	uv run pre-commit install

format: ## Format and lint-fix the codebase
	$(RUFF) check --fix .
	$(RUFF) format .

lint: ## Run static type checking and the full pre-commit pipeline
	uv run mypy src/
	uv run pre-commit run --all-files

test: ## Execute the unit, guardrail, and resilience test suites
	$(PYTEST) tests/ -v

eval: ## Run the automated evaluation benchmark suite
	$(PYTHON) -m sql_circuit_guard.service.run_evals

up: ## Build and start the full stack (Gradio, Ollama, Langfuse)
	docker compose up --build -d

down: ## Stop the container stack
	docker compose down

logs: ## Tail the application container logs
	docker compose logs -f app

profile: ## Run the WSL2 GPU memory and throughput profiler
	bash scripts/profile_gpu.sh

clean: ## Remove local caches (keeps data/, reports/, and .venv/)
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} +

clean-all: ## Remove caches, virtualenv, and generated reports (keeps data/)
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/ .venv/ reports/
	find . -type d -name "__pycache__" -exec rm -rf {} +
