"""
Data API server — client and product endpoints (standalone).

Start with:
  python -m src.integrations.data_server
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fastapi import FastAPI, HTTPException, Path, Query

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
    """Filter clients by demographic and portfolio criteria.

    Numeric fields accept a single value (exact match) or a [min, max] list for range matching.
    """

    risk_rating: int | list[int] | None = Field(
        None, description="Client risk rating (1-5) or range e.g. [1,3]",
        json_schema_extra={"example": [1, 3]},
    )
    age: int | list[int] | None = Field(
        None, description="Client age or range e.g. [35,70]",
        json_schema_extra={"example": [35, 70]},
    )
    product_types_in_holdings: str | list[str] | None = Field(
        None, description="Filter by product family: 'bond', 'equity', 'cash', or 'balanced'",
        json_schema_extra={"example": "bond"},
    )
    concentration_score: float | list[float] | None = Field(
        None, description="0-10 score or range e.g. [6,10]",
        json_schema_extra={"example": [6, 10]},
    )
    cash_score: float | list[float] | None = Field(
        None, description="0-10 score or range e.g. [0,5]",
        json_schema_extra={"example": [0, 5]},
    )


class ProductSearchRequest(BaseModel):
    """Proximity search returning products ranked by similarity."""

    query: dict = Field(
        ..., description="Product attributes to match against",
        json_schema_extra={"example": {"risk_rating": 1, "expected_return": 3.7, "product_type": "bond"}},
    )
    top_n: int = Field(3, ge=1, le=50)
    risk_rating_hard_filter: bool = True
    diversification: bool = True
    max_per_product_type: int = Field(2, ge=1, le=10)
    exclude_product_ids: list[str] | None = Field(
        None, json_schema_extra={"example": ["PROD053"]},
    )


class ReinvestmentCandidatesRequest(BaseModel):
    """Find reinvestment candidates for a list of clients."""

    client_ids: list[str] = Field(
        ..., min_length=1, json_schema_extra={"example": ["PB-HK-000007-5"]},
    )
    source_product_id: str = Field(
        ..., description="Maturing product to find replacements for",
        json_schema_extra={"example": "PROD053"},
    )
    max_per_product_type: int = Field(2, ge=1, le=10)
    top_n_per_client: int | None = Field(None, ge=1, le=50)
    risk_rating_hard_filter: bool = True
    exclude_product_ids: list[str] | None = None


class FitnessScoreRequest(BaseModel):
    """Compute product fitness scores for client×product pairs."""

    client_ids: list[str] = Field(
        ..., min_length=1, json_schema_extra={"example": ["PB-HK-000007-5"]},
    )
    product_ids: list[str] = Field(
        ..., min_length=1, json_schema_extra={"example": ["PROD054", "ETF-BIL", "ETF-SHV"]},
    )
    top_n: int = Field(10, ge=1, le=50)
    risk_rating_hard_filter: bool = True
    exclude_dimensions: list[str] | None = Field(
        None, json_schema_extra={"example": ["concentration_score"]},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Response models (for OpenAPI documentation only — not validated at runtime)
# ═══════════════════════════════════════════════════════════════════════════


class ClientResponse(BaseModel):
    model_config = ConfigDict(extra="allow")  # flexible — search vs get_by_id return different shapes

    client_id: str = Field(..., json_schema_extra={"example": "PB-HK-000007-5"})
    name: str | None = Field(None, json_schema_extra={"example": "William Chen"})
    age: int | None = Field(None, json_schema_extra={"example": 68})
    risk_rating: int | None = Field(None, json_schema_extra={"example": 1})
    aum: float | None = Field(None, json_schema_extra={"example": 18500000.0})
    region: str | None = Field(None, json_schema_extra={"example": "HK"})
    cash_pct: float | None = Field(None, json_schema_extra={"example": 5.0})
    cash_score: float | None = Field(None, json_schema_extra={"example": 2.3})
    concentration_score: float | None = Field(None, json_schema_extra={"example": 4.1})
    active_score: float | None = Field(None, json_schema_extra={"example": 3.0})
    life_stage_score: float | None = Field(None, json_schema_extra={"example": 8.5})
    investor_readiness_score: float | None = Field(None, json_schema_extra={"example": 8.2})


class ProductResponse(BaseModel):
    product_id: str = Field(..., json_schema_extra={"example": "PROD053"})
    name: str = Field(..., json_schema_extra={"example": "US Treasury 4.375% 31Aug26"})
    risk_rating: int | None = Field(None, json_schema_extra={"example": 1})
    expected_return: float | None = Field(None, json_schema_extra={"example": 3.7})
    product_type: str | None = Field(None, json_schema_extra={"example": "bond"})


class SearchSimilarResult(BaseModel):
    results: list[dict] = Field(
        ...,
        json_schema_extra={"example": [
            {"product_id": "PROD054", "similarity_score": 0.9933, "name": "US Treasury 3.75% 30Jun27"},
            {"product_id": "ETF-BIL", "similarity_score": 0.7725, "name": "SPDR Bloomberg 1-3 Month T-Bill ETF"},
        ]},
    )


class CandidateResultItem(BaseModel):
    product_id: str = Field(..., json_schema_extra={"example": "PROD054"})
    similarity_score: float = Field(..., json_schema_extra={"example": 0.9933})


class CandidatesResult(BaseModel):
    results_by_client: dict[str, list[CandidateResultItem]] = Field(
        ...,
        json_schema_extra={"example": {
            "PB-HK-000007-5": [
                {"product_id": "PROD054", "similarity_score": 0.9933},
                {"product_id": "ETF-BIL", "similarity_score": 0.7725},
            ],
        }},
    )


class ComponentScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_rating_match_score: float | None = Field(None, json_schema_extra={"example": 9.0})
    concentration_score: float | None = Field(None, json_schema_extra={"example": 8.5})
    has_similar_investment_experience_score: float | None = Field(None, json_schema_extra={"example": 10.0})
    better_product_score: float | None = Field(None, json_schema_extra={"example": 6.2})


class FitnessScoreItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(..., json_schema_extra={"example": "PB-HK-000007-5"})
    product_id: str = Field(..., json_schema_extra={"example": "PROD054"})
    fitness_score: float = Field(..., json_schema_extra={"example": 8.35})
    component_scores: ComponentScores = Field(
        ...,
        json_schema_extra={"example": {
            "risk_rating_match_score": 9.0,
            "concentration_score": 8.5,
            "has_similar_investment_experience_score": 10.0,
            "better_product_score": 6.2,
        }},
    )


class FitnessScoreResult(BaseModel):
    results: list[FitnessScoreItem] = Field(default_factory=list)


class ReadinessItem(BaseModel):
    rank: int = Field(..., json_schema_extra={"example": 1})
    client_id: str = Field(..., json_schema_extra={"example": "PB-HK-000007-5"})
    name: str = Field(..., json_schema_extra={"example": "William Chen"})
    investor_readiness_score: float = Field(..., json_schema_extra={"example": 8.2})
    cash_score: float = Field(..., json_schema_extra={"example": 7.0})
    concentration_score: float = Field(..., json_schema_extra={"example": 8.5})
    active_score: float = Field(..., json_schema_extra={"example": 9.0})
    life_stage_score: float = Field(..., json_schema_extra={"example": 8.0})


class MaturingHoldingItem(BaseModel):
    client_id: str = Field(..., json_schema_extra={"example": "PB-HK-000007-5"})
    product_id: str = Field(..., json_schema_extra={"example": "PROD053"})
    market_value: float = Field(..., json_schema_extra={"example": 1750000.0})
    days_to_mature: int = Field(..., json_schema_extra={"example": 39})


class ErrorDetail(BaseModel):
    detail: str = Field(..., json_schema_extra={"example": "Client not found: PB-HK-999"})



# ═══════════════════════════════════════════════════════════════════════════
# Client endpoints
# ═══════════════════════════════════════════════════════════════════════════
# IMPORTANT: static routes (/readiness, /holdings/maturing, /search) MUST
# be declared BEFORE the parameterised /{client_id} route, otherwise FastAPI
# matches "readiness" as a client_id.


@app.post("/api/v1/clients/search", response_model=list[ClientResponse])
def search_clients(body: ClientSearchRequest) -> list[dict]:
    """Filter clients by demographic and portfolio criteria."""
    return search(**body.model_dump(exclude_none=True))


@app.get("/api/v1/clients/holdings/maturing", response_model=list[MaturingHoldingItem])
def get_holdings_maturing(
    product_types: str | None = Query(
        default=None,
        description="Comma-separated product types",
        examples=["bond,bond_fund"],
    ),
    within_days: int = Query(default=14, description="Calendar days to maturity", examples=[365]),
    as_of_date: str | None = Query(
        default=None,
        description="Reference date (ISO 8601). Defaults to system date.",
        examples=["2026-07-24"],
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


@app.get("/api/v1/clients/readiness", response_model=list[ReadinessItem])
def get_investor_readiness(
    top_n: int = Query(default=0, description="Max results. 0 = return all.", examples=[10]),
) -> list[dict]:
    """Return clients ranked by investor readiness score."""
    from src.planbot.investor_readiness_score import run_score_card

    scores = run_score_card("config/config_planbot.yaml")
    results: list[dict] = []
    for rank, s in enumerate(scores, start=1):
        results.append({
            "rank": rank,
            "client_id": s.client_id,
            "name": s.name,
            "investor_readiness_score": s.total_score,
            "cash_score": s.s_cash,
            "concentration_score": s.s_concentration,
            "active_score": s.s_active,
            "life_stage_score": s.s_lifestage,
        })
    if top_n and top_n > 0:
        results = results[:top_n]
    return results


@app.get(
    "/api/v1/clients/{client_id}",
    response_model=ClientResponse,
    responses={404: {"model": ErrorDetail, "description": "Client not found"}},
)
def get_client(
    client_id: str = Path(
        ...,
        description="Client identifier",
        openapi_examples={"PB-HK-000007-5 (bond holder)": {"value": "PB-HK-000007-5"}},
    ),
) -> dict:
    """Return full client profile including nested holdings."""
    result = search_by_id(client_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Client not found: {client_id}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Product endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.get(
    "/api/v1/products/{product_id}",
    response_model=ProductResponse,
    responses={404: {"model": ErrorDetail, "description": "Product not found"}},
)
def get_product(
    product_id: str = Path(
        ...,
        description="Product identifier",
        openapi_examples={"PROD053 (US Treasury 4.375%)": {"value": "PROD053"}},
    ),
) -> dict:
    """Look up a single product by its ID."""
    result = search_by_product_id(product_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Product not found: {product_id}")
    return result


@app.post("/api/v1/products/search", response_model=SearchSimilarResult)
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


@app.post("/api/v1/products/reinvestment-candidates", response_model=CandidatesResult)
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


@app.post("/api/v1/products/fitness-score", response_model=FitnessScoreResult)
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
