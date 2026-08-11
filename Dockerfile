# ==========================================
# Stage 1: Build virtual environment
# ==========================================
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 1. Install dependencies first (leveraging Docker layer caching)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# 2. Copy source code and build project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ==========================================
# Stage 2: Minimal Secure Runtime
# ==========================================
FROM python:3.12-slim-bookworm AS runner

# Create a non-root user for security best practices
RUN addgroup --system appgroup && adduser --system --group appuser

WORKDIR /app

# Copy virtualenv and app code from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app

# Set PATH so python/uvicorn runs directly from virtual environment
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8000

# Exec form CMD for graceful SIGTERM/SIGINT shutdown handling
CMD ["fastapi", "run", "app/main.py", "--port", "8000"]