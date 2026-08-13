"""
Bank API Simulator — raw client/holding/product data endpoints (standalone).

Sprint 2: this replaces the old Data API server.  It exposes ONLY raw data —
clients, holdings, products — the same contract a real bank would expose.
All business logic (scorecards, similarity, fitness, search) now lives in the
Python Logic Layer and is invoked in-process by the proposal server.

Start with:
  python -m src.integrations.data_server

The simulator is always backed by DuckDB test data (regardless of the
``get_client_product_from_restapi`` flag), so developers can exercise the
REST adapter path without a real bank integration.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Path as PathParam, Query

from src.adapters.duckdb_adapter import DuckDBDataAdapter
from src.shared.logging_utils import init_logging

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_DB_PATH = _ROOT_DIR / "data" / "planbot" / "db" / "planbot.duckdb"

app = FastAPI(
    title="PlanBot Bank API Simulator",
    description="Raw client, holding, and product data — a stand-in for bank-internal systems.",
    version="0.1.0",
)

# The simulator always serves DuckDB data (the "bank" test fixture).
_adapter = DuckDBDataAdapter(_DB_PATH)


@app.on_event("startup")
async def _on_startup() -> None:
    init_logging()
    LOGGER.info("Bank API Simulator startup complete.")


def _split_ids(raw: str | None) -> list[str] | None:
    """Split a comma-separated id query param into a list (or None if empty)."""
    if not raw:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


# ═══════════════════════════════════════════════════════════════════════════
# Client endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.get("/api/v1/clients")
def list_clients(
    client_id: str | None = Query(default=None, description="Comma-separated client IDs to filter"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int | None = Query(default=None, ge=1, description="Pagination limit"),
) -> list[dict]:
    """List clients (raw rows).  Optionally filter by ``client_id``."""
    return _adapter.fetch_clients(
        _split_ids(client_id), limit=limit, offset=offset,
    )


@app.get("/api/v1/clients/{client_id}")
def get_client(
    client_id: str = PathParam(..., description="Client identifier"),
) -> dict:
    """Return a single raw client row."""
    rows = _adapter.fetch_clients([client_id])
    if not rows:
        raise HTTPException(status_code=404, detail=f"Client not found: {client_id}")
    return rows[0]


# ═══════════════════════════════════════════════════════════════════════════
# Holdings endpoint
# ═══════════════════════════════════════════════════════════════════════════


@app.get("/api/v1/holdings")
def list_holdings(
    client_id: str | None = Query(default=None, description="Comma-separated client IDs to filter"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int | None = Query(default=None, ge=1, description="Pagination limit"),
) -> list[dict]:
    """List holdings (raw rows).  Optionally filter by ``client_id``."""
    return _adapter.fetch_holdings(
        _split_ids(client_id), limit=limit, offset=offset,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Product endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.get("/api/v1/products")
def list_products(
    product_id: str | None = Query(default=None, description="Comma-separated product IDs to filter"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int | None = Query(default=None, ge=1, description="Pagination limit"),
) -> list[dict]:
    """List products (raw rows).  Optionally filter by ``product_id``."""
    return _adapter.fetch_products(
        _split_ids(product_id), limit=limit, offset=offset,
    )


@app.get("/api/v1/products/{product_id}")
def get_product(
    product_id: str = PathParam(..., description="Product identifier"),
) -> dict:
    """Return a single raw product row."""
    rows = _adapter.fetch_products([product_id])
    if not rows:
        raise HTTPException(status_code=404, detail=f"Product not found: {product_id}")
    return rows[0]


# ═══════════════════════════════════════════════════════════════════════════
# Startup (production)
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import os
    import uvicorn
    import yaml

    config_path = _ROOT_DIR / "config" / "config_planbot.yaml"
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    server_cfg = (cfg.get("server") or {}).get("data", {})

    host = os.environ.get("HOST", server_cfg.get("host", "127.0.0.1"))
    port = int(os.environ.get("PORT", server_cfg.get("port", 8001)))

    uvicorn.run(
        "src.integrations.data_server:app",
        host=host,
        port=port,
        reload=os.environ.get("RELOAD", "1") == "1",
        log_config=None,
    )
