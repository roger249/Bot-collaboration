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
# The uv download cache (~1.4 GB) is removed in the same RUN so it never
# becomes part of the final image layer.
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-install-project \
    && rm -rf /root/.cache/uv

# Copy application code and runtime assets.
COPY src /app/src
COPY config /app/config-default
COPY data /app/data-default

# Container startup helper to materialize default+override config/data.
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# YAML deep-merge helper used by entrypoint.sh for partial config overrides.
COPY docker/merge_yaml.py /app/merge_yaml.py

# Multi-server launcher (proposal + optional data API server).
COPY docker/run_servers.py /app/run_servers.py

# Self-contained deployment bundle for clients (no source access required).
# Extract with `docker run --rm --entrypoint cat` (see README.md).
COPY compose.yaml /app/deploy/compose.yaml

# Create writable output folders used by the proposal pipeline.
RUN mkdir -p /app/log /app/runs /app/temp /app/config /app/data /app/config-override /app/data-override

EXPOSE 8000 8001

# Run both servers via the launcher (see docker/run_servers.py for switches).
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "/app/run_servers.py"]