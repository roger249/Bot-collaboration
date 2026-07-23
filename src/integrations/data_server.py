"""
Data API server — client and product endpoints (standalone).

Start with:
  python -m src.integrations.data_server
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, Query

from src.integrations.client_api import (
    search_by_id,
    search,
    search_holdings_maturing,
)
from src.integrations.product_tool import (
    search_by_product_id,
    search_similar,
    search_reinvestment_candidates,
    search_product_by_fitness_score,
)

app = FastAPI(
    title="PlanBot Data API",
    description="Client and product APIs for investment proposal generation.",
    version="0.1.0",
)


# ═══════════════════════════════════════════════════════════════════════════
# Request models
# ═══════════════════════════════════════════════════════════════════════════


class ClientSearchRequest(BaseModel):
    """Filter clients by demographic and portfolio criteria."""

    risk_rating: int | None = Field(None, description="Client risk rating (1-5)", ge=1, le=5)
    age: int | None = Field(None, description="Client age", ge=18)
    product_types_in_holdings: list[str] | None = Field(
        None, description="Filter by product types held, e.g. ['bond', 'equity']",
    )
    concentration_score: float | None = Field(None, ge=0, le=10)
    cash_score: float | None = Field(None, ge=0, le=10)


class ProductSearchRequest(BaseModel):
    """Proximity search returning products ranked by similarity."""

    query: dict = Field(..., description="Product attributes to match against")
    top_n: int = Field(3, ge=1, le=50)
    risk_rating_hard_filter: bool = True
    diversification: bool = True
    max_per_product_type: int = Field(2, ge=1, le=10)
    exclude_product_ids: list[str] | None = None


class ReinvestmentCandidatesRequest(BaseModel):
    """Find reinvestment candidates for a list of clients."""

    client_ids: list[str] = Field(..., min_length=1)
    source_product_id: str = Field(..., description="Maturing product to find replacements for")
    max_per_product_type: int = Field(2, ge=1, le=10)
    top_n_per_client: int | None = Field(None, ge=1, le=50)
    risk_rating_hard_filter: bool = True
    exclude_product_ids: list[str] | None = None


class FitnessScoreRequest(BaseModel):
    """Compute product fitness scores for client×product pairs."""

    client_ids: list[str] = Field(..., min_length=1)
    product_ids: list[str] = Field(..., min_length=1)
    top_n: int = Field(10, ge=1, le=50)
    risk_rating_hard_filter: bool = True
    exclude_dimensions: list[str] | None = None


# ═══════════════════════════════════════════════════════════════════════════
# Client endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.get("/api/v1/clients/{client_id}")
def get_client(client_id: str) -> dict:
    """Return full client profile including nested holdings."""
    result = search_by_id(client_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Client not found: {client_id}")
    return result


@app.post("/api/v1/clients/search")
def search_clients(body: ClientSearchRequest) -> list[dict]:
    """Filter clients by demographic and portfolio criteria."""
    return search(**body.model_dump(exclude_none=True))


@app.get("/api/v1/clients/holdings/maturing")
def get_holdings_maturing(
    product_types: str | None = Query(
        default=None,
        description="Comma-separated product types, e.g. 'bond,bond_fund'",
    ),
    within_days: int = Query(default=14, description="Calendar days to maturity"),
    as_of_date: str | None = Query(
        default=None,
        description="Reference date (ISO 8601). Defaults to system date.",
    ),
) -> list[dict]:
    """Find clients with bonds or fixed-income products maturing."""
    pts = None
    if product_types:
        pts = [t.strip() for t in product_types.split(",")]
    kwargs: dict[str, Any] = {"within_days": within_days}
    if pts:
        kwargs["product_types"] = pts
    if as_of_date:
        kwargs["as_of_date"] = as_of_date
    return search_holdings_maturing(**kwargs)


@app.get("/api/v1/clients/readiness")
def get_investor_readiness(
    top_n: int = Query(default=0, description="Max results. 0 = return all."),
) -> list[dict]:
    """Return clients ranked by investor readiness score."""
    from src.planbot.investor_readiness_score import run_score_card

    scores = run_score_card("config/config_planbot.yaml")
    results: list[dict] = []
    for s in scores:
        results.append({
            "rank": s.rank,
            "client_id": s.client_id,
            "name": s.name,
            "total_score": s.total_score,
            "s_cash": s.s_cash,
            "s_concentration": s.s_concentration,
            "s_active": s.s_active,
            "s_lifestage": s.s_lifestage,
        })
    if top_n and top_n > 0:
        results = results[:top_n]
    return results


# ═══════════════════════════════════════════════════════════════════════════
# Product endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.get("/api/v1/products/{product_id}")
def get_product(product_id: str) -> dict:
    """Look up a single product by its ID."""
    result = search_by_product_id(product_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Product not found: {product_id}")
    return result


@app.post("/api/v1/products/search")
def search_products(body: ProductSearchRequest) -> dict:
    """Proximity search returning products ranked by similarity."""
    return search_similar(
        query=body.query,
        top_n=body.top_n,
        risk_rating_hard_filter=body.risk_rating_hard_filter,
        diversification=body.diversification,
        max_per_product_type=body.max_per_product_type,
        exclude_product_ids=body.exclude_product_ids,
    )


@app.post("/api/v1/products/reinvestment-candidates")
def get_reinvestment_candidates(body: ReinvestmentCandidatesRequest) -> dict:
    """Find reinvestment candidates per client."""
    return search_reinvestment_candidates(
        client_ids=body.client_ids,
        source_product_id=body.source_product_id,
        max_per_product_type=body.max_per_product_type,
        top_n_per_client=body.top_n_per_client,
        risk_rating_hard_filter=body.risk_rating_hard_filter,
        exclude_product_ids=body.exclude_product_ids,
    )


@app.post("/api/v1/products/fitness-score")
def get_product_fitness_score(body: FitnessScoreRequest) -> dict:
    """Compute product fitness scores for client×product pairs."""
    return search_product_by_fitness_score(
        client_ids=body.client_ids,
        product_ids=body.product_ids,
        top_n=body.top_n,
        risk_rating_hard_filter=body.risk_rating_hard_filter,
        exclude_dimensions=body.exclude_dimensions,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Startup (production)
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    from pathlib import Path
    import yaml

    config_path = Path(__file__).resolve().parents[2] / "config" / "config_planbot.yaml"
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    server_cfg = (cfg.get("server") or {}).get("data", {})

    uvicorn.run(
        "src.integrations.data_server:app",
        host=server_cfg.get("host", "127.0.0.1"),
        port=server_cfg.get("port", 8001),
        reload=True,
    )
