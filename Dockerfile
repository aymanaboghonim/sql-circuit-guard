# ==============================================================================
# Multi-Stage Build: sql-circuit-guard (Python 3.12 / uv)
# ==============================================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Enable bytecode compilation and frozen sync
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copy dependency specifications first for Docker layer caching
COPY pyproject.toml uv.lock ./

# Sync dependencies without installing the project root package yet
RUN uv sync --frozen --no-install-project --no-dev

# Copy application source code, readme, and dataset
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
COPY data/ ./data/

# Sync project package itself
RUN uv sync --frozen --no-dev


# ==============================================================================
# Stage 2: Clean Runtime Image
# ==============================================================================
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Add non-root system user for container security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy virtual environment and necessary data from builder stage
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/src /app/src
COPY --from=builder --chown=appuser:appuser /app/data /app/data

# Ensure virtual environment binaries take precedence in PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 7860

ENTRYPOINT ["python", "src/app.py"]
