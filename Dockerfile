# ---- Build stage: install dependencies with uv ----
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first (cached layer — only invalidated when the lock
# file changes, not on every code edit)
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Then install the project itself
COPY app ./app
RUN uv sync --locked --no-dev

# ---- Runtime stage: slim image, no uv, non-root ----
FROM python:3.13-slim

RUN useradd --create-home --uid 1000 appuser

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER appuser

# Cloud Run injects PORT (defaults to 8080)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
