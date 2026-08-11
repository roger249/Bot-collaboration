FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

WORKDIR /app

# Install OS packages needed by runtime libs and health check.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better Docker layer caching.
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code and runtime assets.
COPY src /app/src
COPY config /app/config-default
COPY data /app/data-default

# Container startup helper to materialize default+override config/data.
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create writable output folders used by the proposal pipeline.
RUN mkdir -p /app/log /app/runs /app/temp /app/config /app/data /app/config-override /app/data-override

EXPOSE 8000

# Run Proposal Server directly with container-friendly bind address.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "src.integrations.proposal_server:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "config/logging_config.ini"]