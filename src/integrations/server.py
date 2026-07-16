"""
FastAPI server exposing client and product APIs.

Endpoints
---------
Clients:
  GET  /api/v1/clients/{client_id}
  POST /api/v1/clients/search
  GET  /api/v1/clients/holdings/maturing
  GET  /api/v1/clients/readiness

Products:
  GET  /api/v1/products/{product_id}
  POST /api/v1/products/search
  POST /api/v1/products/reinvestment-candidates
  POST /api/v1/products/fitness-score

Start with:
  .venv/bin/uvicorn src.integrations.server:app --reload

Reinvestment Proposals:
  POST /api/v1/reinvestment-proposals
"""

from __future__ import annotations

from typing import Any

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
from src.integrations.reinvestment_proposal import propose_reinvestment

app = FastAPI(
    title="PlanBot API",
    description="Client and product APIs for investment proposal generation.",
    version="0.1.0",
)


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
def search_clients(body: dict) -> list[dict]:
    """Filter clients by demographic and portfolio criteria.

    Accepts: risk_rating, age, product_types_in_holdings,
    concentration_score, cash_score.
    """
    return search(**body)


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
def search_products(body: dict) -> dict:
    """Proximity search returning products ranked by similarity.

    Request body matches the ``search_similar`` contract.
    """
    query = body.get("query", {})
    return search_similar(
        query=query,
        top_n=body.get("top_n", 3),
        risk_rating_hard_filter=body.get("risk_rating_hard_filter", True),
        diversification=body.get("diversification", True),
        max_per_product_type=body.get("max_per_product_type", 2),
        exclude_product_ids=body.get("exclude_product_ids"),
    )


@app.post("/api/v1/products/reinvestment-candidates")
def get_reinvestment_candidates(body: dict) -> dict:
    """Find reinvestment candidates per client.

    Request body matches the ``search_reinvestment_candidates`` contract.
    """
    return search_reinvestment_candidates(
        client_ids=body["client_ids"],
        source_product_id=body["source_product_id"],
        max_per_product_type=body.get("max_per_product_type", 2),
        top_n_per_client=body.get("top_n_per_client"),
        risk_rating_hard_filter=body.get("risk_rating_hard_filter", True),
        exclude_product_ids=body.get("exclude_product_ids"),
    )


@app.post("/api/v1/products/fitness-score")
def get_product_fitness_score(body: dict) -> dict:
    """Compute product fitness scores for client×product pairs.

    Request body matches the ``search_product_by_fitness_score`` contract.
    """
    return search_product_by_fitness_score(
        client_ids=body["client_ids"],
        product_ids=body["product_ids"],
        top_n=body.get("top_n", 10),
        risk_rating_hard_filter=body.get("risk_rating_hard_filter", True),
        exclude_dimensions=body.get("exclude_dimensions"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Reinvestment proposal endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.post("/api/v1/reinvestment-proposals")
def get_reinvestment_proposals(body: dict) -> dict:
    """Generate reinvestment proposals for one or more target pairs.

    Request body matches the ``generate_reinvestment_proposal`` contract.
    """
    return propose_reinvestment(
        reinvestment_targets=body["reinvestment_targets"],
        max_per_product_type=body.get("max_per_product_type", 2),
        top_n_per_client=body.get("top_n_per_client", 10),
        risk_rating_hard_filter=body.get("risk_rating_hard_filter", True),
        response_mode=body.get("response_mode", "path"),
        include_llm_input=body.get("include_llm_input", False),
        include_market_outlook=body.get("include_market_outlook", True),
        include_debug_scores=body.get("include_debug_scores", False),
    )
