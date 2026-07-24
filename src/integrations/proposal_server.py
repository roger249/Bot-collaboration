"""
Proposal API server — reinvestment proposal endpoints (standalone).

This server exposes the proposal-generation API.  For client/product data it
delegates to the Data API server (``data_service_url`` in config) when Phase B
is enabled, or falls back to local imports when Phase A is active.

Start with:
  python -m src.integrations.proposal_server
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from fastapi import FastAPI

from src.integrations.reinvestment_proposal import (
    propose_reinvestment,
    propose_reinvestment_for_maturing_holdings,
)

app = FastAPI(
    title="PlanBot Proposal API",
    description="Reinvestment proposal generation API.",
    version="0.1.0",
)


# ═══════════════════════════════════════════════════════════════════════════
# Request models
# ═══════════════════════════════════════════════════════════════════════════


class ReinvestmentTarget(BaseModel):
    """A client→product pair to generate a reinvestment proposal for."""

    client_id: str = Field(
        ...,
        description="Client identifier, e.g. 'PB-HK-000007-5'",
        json_schema_extra={"example": "PB-HK-000007-5"},
    )
    source_product_id: str = Field(
        ...,
        description="Maturing product ID, e.g. 'PROD053' (US Treasury 4.375% 31Aug26)",
        json_schema_extra={"example": "PROD053"},
    )


class ProposeReinvestmentRequest(BaseModel):
    """Generate reinvestment proposals for one or more target pairs."""

    model_config = ConfigDict(extra="allow")  # backward compat with old body: dict

    reinvestment_targets: list[ReinvestmentTarget] = Field(
        ..., description="List of (client_id, source_product_id) pairs to process",
        min_length=1,
    )
    max_per_product_type: int = Field(
        2, description="Max candidates per product type", ge=1, le=10,
    )
    top_n_per_client: int = Field(
        10, description="Max candidate products per client", ge=1, le=50,
    )
    risk_rating_hard_filter: bool = Field(
        True, description="If True, only return products within client's risk tolerance",
    )
    response_mode: str = Field(
        "path", description="'path' | 'inline' | 'both' — how to return the proposal",
    )
    include_llm_input: bool = Field(
        False, description="Include the raw LLM input in the response",
    )
    include_market_outlook: bool = Field(
        True, description="Include market outlook in the proposal",
    )
    include_debug_scores: bool = Field(
        False, description="Include debug scoring details in the response",
    )


class MaturingHoldingsRequest(BaseModel):
    """Discover clients with maturing bonds and generate proposals."""

    model_config = ConfigDict(extra="allow")  # backward compat with old body: dict

    within_days: int = Field(
        365, description="Look ahead this many days for maturing holdings", ge=1,
    )
    as_of_date: str | None = Field(
        None,
        description="Reference date (ISO 8601). Defaults to today.",
        json_schema_extra={"example": "2026-07-23"},
    )
    max_clients: int = Field(
        2, description="Cap on number of clients to process", ge=1, le=100,
    )
    max_per_product_type: int = Field(
        2, description="Max candidates per product type", ge=1, le=10,
    )
    top_n_per_client: int = Field(
        10, description="Max candidate products per client", ge=1, le=50,
    )
    risk_rating_hard_filter: bool = Field(
        True, description="If True, only return products within client's risk tolerance",
    )
    response_mode: str = Field(
        "path", description="'path' | 'inline' | 'both' — how to return the proposal",
    )
    include_llm_input: bool = Field(
        False, description="Include the raw LLM input in the response",
    )
    include_market_outlook: bool = Field(
        True, description="Include market outlook in the proposal",
    )
    include_debug_scores: bool = Field(
        False, description="Include debug scoring details in the response",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Response models (for OpenAPI documentation only — not validated at runtime)
# ═══════════════════════════════════════════════════════════════════════════


class PerClientResult(BaseModel):
    """Result for a single client→product pair."""

    client_id: str = Field(..., json_schema_extra={"example": "PB-HK-000007-5"})
    source_product_id: str = Field(..., json_schema_extra={"example": "PROD053"})
    candidate_products: list[dict] = Field(
        default_factory=list,
        json_schema_extra={"example": [{"product_id": "PROD054", "similarity_score": 0.9933}]},
    )
    output_path: str | None = Field(
        None, json_schema_extra={"example": "runs/reinvestment_proposal/reinvestment_proposal_PB-HK-000007-5.md"},
    )
    markdown_output: str | None = Field(
        None, json_schema_extra={"example": "# Reinvestment Proposal\n\n## Executive Summary\n..."},
    )
    error: str | None = Field(
        None, json_schema_extra={"example": "Data service unreachable at http://localhost:8001/api/v1: [Errno 61] Connection refused. Is the data server running?"},
    )


class ProposalResponse(BaseModel):
    """Top-level response from the reinvestment proposal API."""

    status: str = Field(..., json_schema_extra={"example": "success"})
    results_by_client: list[PerClientResult] = Field(default_factory=list)


class ValidationErrorDetail(BaseModel):
    detail: str = Field(..., json_schema_extra={"example": "Client not found: PB-HK-999"})


# ═══════════════════════════════════════════════════════════════════════════
# Reinvestment proposal endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.post("/api/v1/reinvestment-proposals", response_model=ProposalResponse)
def get_reinvestment_proposals(body: ProposeReinvestmentRequest) -> dict:
    """Generate reinvestment proposals for one or more target pairs."""
    return propose_reinvestment(
        reinvestment_targets=[t.model_dump() for t in body.reinvestment_targets],
        max_per_product_type=body.max_per_product_type,
        top_n_per_client=body.top_n_per_client,
        risk_rating_hard_filter=body.risk_rating_hard_filter,
        response_mode=body.response_mode,
        include_llm_input=body.include_llm_input,
        include_market_outlook=body.include_market_outlook,
        include_debug_scores=body.include_debug_scores,
    )


@app.post(
    "/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings",
    response_model=ProposalResponse,
)
def propose_for_maturing_holdings(body: MaturingHoldingsRequest) -> dict:
    """Discover clients with maturing bond/bond-fund holdings and generate reinvestment proposals."""
    return propose_reinvestment_for_maturing_holdings(
        within_days=body.within_days,
        as_of_date=body.as_of_date,
        max_clients=body.max_clients,
        max_per_product_type=body.max_per_product_type,
        top_n_per_client=body.top_n_per_client,
        risk_rating_hard_filter=body.risk_rating_hard_filter,
        response_mode=body.response_mode,
        include_llm_input=body.include_llm_input,
        include_market_outlook=body.include_market_outlook,
        include_debug_scores=body.include_debug_scores,
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
    server_cfg = (cfg.get("server") or {}).get("proposal", {})

    uvicorn.run(
        "src.integrations.proposal_server:app",
        host=server_cfg.get("host", "127.0.0.1"),
        port=server_cfg.get("port", 8000),
    )
