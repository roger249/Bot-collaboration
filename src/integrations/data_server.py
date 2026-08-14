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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, Path as PathParam, Query

from src.adapters.duckdb_adapter import DuckDBDataAdapter
from src.shared.logging_utils import init_logging

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_DB_PATH = _ROOT_DIR / "data" / "planbot" / "db" / "planbot.duckdb"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_logging()
    LOGGER.info("Bank API Simulator startup complete.")
    yield


app = FastAPI(
    title="PlanBot Bank API Simulator",
    description="Raw client, holding, and product data — a stand-in for bank-internal systems.",
    version="0.1.0",
    lifespan=lifespan,
)

# The simulator always serves DuckDB data (the "bank" test fixture).
_adapter = DuckDBDataAdapter(_DB_PATH)


# ═══════════════════════════════════════════════════════════════════════════
# Response models — the raw row contract the bank implements against.
# ═══════════════════════════════════════════════════════════════════════════


class ClientRow(BaseModel):
    """Raw client row as stored in the client database."""

    client_id: str = Field(..., description="Unique client identifier.")
    name: str = Field(..., description="Client full name.")
    aum: float | None = Field(None, description="Assets under management (USD).")
    cash_pct: float | None = Field(None, description="Reported cash percentage of AUM.")
    region: str | None = None
    birthdate: str | None = Field(None, description="Date of birth (YYYY-MM-DD).")
    occupation: str | None = None
    risk_rating: int | None = Field(None, description="Risk tolerance 1 (low) – 5 (high).")
    marital_status: str | None = None
    children_info: str | None = None
    liquidity_need: str | None = None
    income_stability: str | None = None
    investment_objective: str | None = None
    qualitative_profile: str | None = Field(None, description="Free-text RM notes for suitability analysis.")


class HoldingRow(BaseModel):
    """Raw holding row as stored in the custody/positions database."""

    client_id: str = Field(..., description="Owner client identifier.")
    holding_idx: int = Field(..., description="Zero-based position index within the client.")
    holding_id: str | None = None
    product_id: str | None = Field(None, description="Instrument/product identifier.")
    instrument_name: str | None = None
    symbol: str | None = None
    asset_class: str | None = None
    region: str | None = None
    currency: str | None = None
    quantity: float | None = None
    book_cost: float | None = None
    market_value: float | None = Field(None, description="Current market value in the holding currency.")
    unrealized_pl: float | None = None
    unrealized_pl_pct: float | None = None
    yield_pct: float | None = None
    risk_bucket: str | None = None
    esg_score: str | None = Field(None, description="ESG score; null when no coverage.")
    liquidity: str | None = None


class ProductRow(BaseModel):
    """Raw product row as stored in the product master database."""

    product_id: str = Field(..., description="Unique product identifier.")
    isin: str | None = Field(None, description="ISIN; null for products without one.")
    name: str = Field(..., description="Product name.")
    ticker: str | None = None
    trading_currency: str | None = None
    risk_rating: int = Field(..., description="Risk rating 1 (low) – 5 (high).")
    expected_return: float | None = Field(None, description="Expected annual return (%).")
    region: str | None = None
    country: str | None = None
    sector: str | None = None
    remarks: str | None = None
    product_type: str = Field(..., description="e.g. bond, bond_fund, equity_fund, stock, money_market_fund, balanced_fund.")
    vehicle: str | None = Field(None, description="e.g. Direct, ETF, Mutual Fund.")
    type_specific: dict[str, Any] | None = Field(None, description="Product-type-specific attributes (variable keys).")
    performance_history: dict[str, Any] | None = Field(None, description="Historical return/risk metrics keyed by period (6m/1y/3y/5y/10y).")
    investment_note: str | None = Field(None, description="House view narrative.")


class ErrorDetail(BaseModel):
    """Standard error body returned on 404."""

    detail: str = Field(..., description="Human-readable error message.")


# ── Swagger response examples (captured from the DuckDB test data) ─────────

_CLIENT_EXAMPLE = {
    "client_id": "PB-HK-000007-5",
    "name": "Akira Tanaka",
    "aum": 28000000.0,
    "cash_pct": 12.0,
    "region": "APAC",
    "birthdate": "1980-01-01",
    "occupation": "Real Estate Developer",
    "risk_rating": 4,
    "marital_status": "Single",
    "children_info": "2 children",
    "liquidity_need": "Low",
    "income_stability": "Stable salaried income",
    "investment_objective": "Long-term capital growth",
    "qualitative_profile": "Self-made real estate developer with entrepreneurial mindset. Comfortable with illiquid and alternative investments.",
}

_HOLDING_EXAMPLE = {
    "client_id": "PB-HK-000007-5",
    "holding_idx": 0,
    "holding_id": "ph-6-us1mt-rr-0",
    "product_id": "PROD053",
    "instrument_name": "US 1-Month Treasury Bill Rate",
    "symbol": "US1MT=RR",
    "asset_class": "Cash",
    "region": "North America",
    "currency": "USD",
    "quantity": 153494.7465,
    "book_cost": 2352941.1765,
    "market_value": 3360000.0,
    "unrealized_pl": 1007058.8235,
    "unrealized_pl_pct": 42.8,
    "yield_pct": 15.7,
    "risk_bucket": "Low",
    "esg_score": None,
    "liquidity": "T+2",
}

_PRODUCT_EXAMPLE = {
    "product_id": "PROD053",
    "isin": None,
    "name": "US Treasury 4.375% 31Aug26",
    "ticker": "XHLF",
    "trading_currency": "USD",
    "risk_rating": 1,
    "expected_return": 3.7,
    "region": "US",
    "country": None,
    "sector": "Government",
    "remarks": "Bridge row for holdings product_id=PROD053. Group: holdings_treasury_bonds.",
    "product_type": "bond",
    "vehicle": "Direct",
    "type_specific": {
        "issuer_name": "U.S. Treasury",
        "issuer_sector": "government",
        "coupon_type": "fixed",
        "coupon_rate": 0.04375,
        "coupon_frequency": "semi-annual",
        "credit_rating": "AA+",
        "maturity": "2026-08-31",
        "seniority": "senior",
        "callable": False,
    },
    "performance_history": {
        "1y": {"return": 3.65, "cagr": 3.72, "max_drawdown": 0.0, "volatility": 0.2},
        "3y": {"return": 14.22, "cagr": 4.53, "max_drawdown": -0.03, "volatility": 0.28},
    },
    "investment_note": "Individual bonds allow precise maturity-matching for liability-driven investing.",
}


def _example_response(example) -> dict:
    """OpenAPI 200 response body with a single real-data example."""
    return {200: {"content": {"application/json": {"example": example}}}}


def _split_ids(raw: str | None) -> list[str] | None:
    """Split a comma-separated id query param into a list (or None if empty)."""
    if not raw:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


# ═══════════════════════════════════════════════════════════════════════════
# Client endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.get(
    "/api/v1/clients",
    response_model=list[ClientRow],
    responses=_example_response([_CLIENT_EXAMPLE]),
)
def list_clients(
    client_id: str | None = Query(
        default=None,
        description="Comma-separated list of client IDs to filter by (e.g. `PB-HK-000007-5,PB-HK-000002-6`). "
        "Omit to return all clients.",
        openapi_examples={
            "Akira Tanaka (bond holder)": {"value": "PB-HK-000007-5"},
            "Two clients (comma-separated)": {"value": "PB-HK-000007-5,PB-HK-000002-6"},
        },
    ),
    offset: int = Query(
        default=0, ge=0,
        description="Number of rows to skip (0-based).",
        examples=[0],
    ),
    limit: int | None = Query(
        default=None, ge=1,
        description="Maximum number of rows to return. Omit for all.",
        examples=[10],
    ),
) -> list[dict]:
    """List raw client rows.

    ``client_id`` accepts a **comma-separated** list to fetch multiple clients
    in one call.  Example: `?client_id=PB-HK-000007-5,PB-HK-000002-6`
    """
    return _adapter.fetch_clients(
        _split_ids(client_id), limit=limit, offset=offset,
    )


@app.get(
    "/api/v1/clients/{client_id}",
    response_model=ClientRow,
    responses={
        200: {"content": {"application/json": {"example": _CLIENT_EXAMPLE}}},
        404: {"model": ErrorDetail, "description": "Client not found"},
    },
)
def get_client(
    client_id: str = PathParam(
        ...,
        description="Client identifier.",
        openapi_examples={
            "Akira Tanaka (bond holder)": {"value": "PB-HK-000007-5"},
            "Sarah Chen": {"value": "PB-HK-000002-6"},
        },
    ),
) -> dict:
    """Return a single raw client row."""
    rows = _adapter.fetch_clients([client_id])
    if not rows:
        raise HTTPException(status_code=404, detail=f"Client not found: {client_id}")
    return rows[0]


# ═══════════════════════════════════════════════════════════════════════════
# Holdings endpoint
# ═══════════════════════════════════════════════════════════════════════════


@app.get(
    "/api/v1/holdings",
    response_model=list[HoldingRow],
    responses=_example_response([_HOLDING_EXAMPLE]),
)
def list_holdings(
    client_id: str | None = Query(
        default=None,
        description="Comma-separated list of client IDs to filter by (e.g. `PB-HK-000007-5`). "
        "Omit to return all holdings.",
        openapi_examples={
            "Akira Tanaka (bond holder)": {"value": "PB-HK-000007-5"},
            "Two clients (comma-separated)": {"value": "PB-HK-000007-5,PB-HK-000002-6"},
        },
    ),
    offset: int = Query(
        default=0, ge=0,
        description="Number of rows to skip (0-based).",
        examples=[0],
    ),
    limit: int | None = Query(
        default=None, ge=1,
        description="Maximum number of rows to return. Omit for all.",
        examples=[20],
    ),
) -> list[dict]:
    """List raw holding rows.

    ``client_id`` accepts a **comma-separated** list to fetch holdings for
    multiple clients in one call.
    """
    return _adapter.fetch_holdings(
        _split_ids(client_id), limit=limit, offset=offset,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Product endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.get(
    "/api/v1/products",
    response_model=list[ProductRow],
    responses=_example_response([_PRODUCT_EXAMPLE]),
)
def list_products(
    product_id: str | None = Query(
        default=None,
        description="Comma-separated list of product IDs to filter by (e.g. `PROD053,ETF-HYG`). "
        "Omit to return the full product catalog.",
        openapi_examples={
            "US Treasury 4.375% 31Aug26": {"value": "PROD053"},
            "Two products (comma-separated)": {"value": "PROD053,ETF-HYG"},
        },
    ),
    offset: int = Query(
        default=0, ge=0,
        description="Number of rows to skip (0-based).",
        examples=[0],
    ),
    limit: int | None = Query(
        default=None, ge=1,
        description="Maximum number of rows to return. Omit for all.",
        examples=[10],
    ),
) -> list[dict]:
    """List raw product rows.

    ``product_id`` accepts a **comma-separated** list to fetch multiple products
    in one call.  Example: `?product_id=PROD053,PROD054`
    """
    return _adapter.fetch_products(
        _split_ids(product_id), limit=limit, offset=offset,
    )


@app.get(
    "/api/v1/products/{product_id}",
    response_model=ProductRow,
    responses={
        200: {"content": {"application/json": {"example": _PRODUCT_EXAMPLE}}},
        404: {"model": ErrorDetail, "description": "Product not found"},
    },
)
def get_product(
    product_id: str = PathParam(
        ...,
        description="Product identifier.",
        openapi_examples={
            "US Treasury 4.375% 31Aug26": {"value": "PROD053"},
            "High Yield Corporate Bond ETF": {"value": "ETF-HYG"},
        },
    ),
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
