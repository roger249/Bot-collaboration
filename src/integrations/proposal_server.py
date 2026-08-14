"""
Proposal API server — reinvestment proposal endpoints (standalone).

This server exposes the proposal-generation API.  For client/product data it
delegates to the Data API server (``data_service_url`` in config) when Phase B
is enabled, or falls back to local imports when Phase A is active.

Start with:
  python -m src.integrations.proposal_server
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fastapi import FastAPI, Query

from src.integrations.reinvestment_proposal import (
    propose_reinvestment,
    propose_reinvestment_for_maturing_holdings,
)
from src.integrations.product_investor_matcher import product_investor_matcher
from src.integrations.product_opportunity_proposal import (
    propose_product_opportunity,
    propose_product_opportunity_automatch,
)
from src.integrations.portfolio_review import propose_portfolio_review
from src.integrations.client_api import (
    search_by_investor_readiness_score,
    search_holdings_maturing,
)
from src.integrations.product_tool import (
    search_product_by_fitness_score,
    search_reinvestment_candidates,
    search_similar,
)

from src.shared.logging_utils import init_logging

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_logging()
    LOGGER.info("Proposal Server startup complete.")
    yield


app = FastAPI(
    title="PlanBot Proposal API",
    description="Reinvestment proposal generation API.",
    version="0.1.0",
    lifespan=lifespan,
)


# Shared request-body documentation, rendered by Swagger UI as Markdown at the
# top of each reinvestment endpoint.  Kept as module constants so the two
# reinvestment endpoints (explicit targets + maturing-holdings) stay in sync.
_RESPONSE_MODE_DOC = (
    "How the proposal is returned in the response:\n"
    "- `path` — return only the output file path.\n"
    "- `markdown` — return only the proposal markdown.\n"
    "- `both` — return the path **and** the markdown."
)

_COMMON_SCORING_PARAMS_DOC = (
    "| Field | Type | Description |\n"
    "|---|---|---|\n"
    "| `max_candidates_per_product_type` | int (1–10) | Diversification cap on how many "
    "candidate products are kept per product type. Default `2`. |\n"
    "| `max_candidates_per_client` | int (1–50) | Max candidate products passed to the "
    "LLM per client. Default `10`. |\n"
    "| `risk_rating_hard_filter` | bool | When `true`, only products with "
    "`risk_rating <= client.risk_rating` are considered. Default `true`. |\n"
    "| `response_mode` | enum | " + _RESPONSE_MODE_DOC + " Default `path`. |\n"
    "| `include_llm_input` | bool | Include the assembled LLM prompt in the "
    "response. Default `false`. |\n"
    "| `include_market_outlook` | bool | Include the market outlook section. "
    "Default `true`. |\n"
    "| `include_debug_scores` | bool | Include debug scoring details. Default "
    "`false`. |"
)


# ═══════════════════════════════════════════════════════════════════════════
# Request models
# ═══════════════════════════════════════════════════════════════════════════

ResponseMode = Literal["path", "markdown", "both"]


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

    reinvestment_targets: list[ReinvestmentTarget] = Field(
        ...,
        description="List of (client_id, source_product_id) pairs to process. "
        "Each pair produces one reinvestment proposal.",
        min_length=1,
        json_schema_extra={
            "example": [
                {"client_id": "PB-HK-000007-5", "source_product_id": "PROD053"},
            ],
        },
    )
    max_candidates_per_product_type: int = Field(
        2,
        description="Max candidate products per product type. "
        "Diversification cap applied when selecting similar products.",
        ge=1, le=10,
    )
    max_candidates_per_client: int = Field(
        10,
        description="Max candidate products per client. "
        "Total number of replacement candidates passed to the LLM.",
        ge=1, le=50,
    )
    risk_rating_hard_filter: bool = Field(
        True,
        description="If True, only products with risk_rating <= client's "
        "risk_rating are considered.",
    )
    response_mode: ResponseMode = Field(
        "path",
        description="How the proposal is returned in the response. "
        "'path' = only the output file path. 'markdown' = only the markdown. "
        "'both' = path + markdown.",
    )
    include_llm_input: bool = Field(
        False,
        description="Include the raw LLM input (assembled prompt) in the response.",
    )
    include_market_outlook: bool = Field(
        True,
        description="Include the market outlook section in the proposal.",
    )
    include_debug_scores: bool = Field(
        False,
        description="Include debug scoring details (candidate similarity "
        "scores) in the response.",
    )


class MaturingHoldingsRequest(BaseModel):
    """Discover clients with maturing bonds and generate proposals."""

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
    max_candidates_per_product_type: int = Field(
        2, description="Max candidates per product type", ge=1, le=10,
    )
    max_candidates_per_client: int = Field(
        10, description="Max candidate products per client", ge=1, le=50,
    )
    risk_rating_hard_filter: bool = Field(
        True, description="If True, only return products within client's risk tolerance",
    )
    response_mode: ResponseMode = Field(
        "path",
        description="How the proposal is returned in the response. "
        "'path' = only the output file path. 'markdown' = only the markdown. "
        "'both' = path + markdown.",
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
# Product-Investor Matcher models
# ═══════════════════════════════════════════════════════════════════════════


class MatcherProposal(BaseModel):
    """A single matched client→product proposal."""

    client_id: str = Field(..., json_schema_extra={"example": "PB-HK-000001-8"})
    product_id: str = Field(..., json_schema_extra={"example": "ETF-HYG"})
    investment_amount: str = Field("", json_schema_extra={"example": "$500,000"})
    funding_source: str = Field("", json_schema_extra={"example": "Cash reserves"})
    buying_score: float = Field(0, json_schema_extra={"example": 4.5})
    rationale: str = Field("", json_schema_extra={"example": "Strong fit due to income objective"})
    proposal_markdown: str = Field("", json_schema_extra={"example": "# Client Product Fit Analysis\n..."})
    error: str | None = Field(None)


class MatcherSummary(BaseModel):
    status: str = Field("success", json_schema_extra={"example": "success"})
    total_clients_retrieved: int = Field(0)
    clients_after_readiness: int = Field(0)
    top_n_returned: int = Field(0)


class MatcherErrorDetail(BaseModel):
    code: str = Field("", json_schema_extra={"example": "NO_ELIGIBLE_CLIENTS"})
    message: str = Field("")


class ProductSource(str, Enum):
    """Where the product universe is defined."""

    DEFAULT_YAML = "default_yaml"
    REQUEST_PAYLOAD = "request_payload"


class ProductInvestorMatcherRequest(BaseModel):
    """Request payload for the product-investor matcher.

    When *product_source* is ``default_yaml``, *product_ids* may contain
    group names defined in ``config_planbot.yaml`` under ``product_groups``
    (expanded to their member product IDs).  When *product_source* is
    ``request_payload``, *product_ids* are always literal product IDs.
    """

    product_source: ProductSource = Field(
        ProductSource.DEFAULT_YAML,
        json_schema_extra={"example": "default_yaml"},
    )
    product_ids: list[str] | None = Field(
        None, json_schema_extra={"example": ["bank_recommended"]},
    )
    client_selection: dict | None = Field(
        None, json_schema_extra={"example": {"risk_rating": [3, 5]}},
    )
    top_n: int = Field(3, ge=1, le=20, json_schema_extra={"example": 3})
    market_outlook: str | None = Field(
        default=None, json_schema_extra={"example": "Rates remain elevated; favor short-duration high-quality credit over long duration."},
    )


class ProductInvestorMatcherResponse(BaseModel):
    run_id: str = Field(..., json_schema_extra={"example": "run-20260730-120000"})
    summary: MatcherSummary = Field(default_factory=MatcherSummary)
    product_investor_matching_markdown: str = Field("")
    final_proposals: list[MatcherProposal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[MatcherErrorDetail] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Product-Investor Matcher endpoint
# ═══════════════════════════════════════════════════════════════════════════


@app.post(
    "/api/v1/product-investor-matcher",
    response_model=ProductInvestorMatcherResponse,
)
def match_products_to_investors_endpoint(
    body: ProductInvestorMatcherRequest,
) -> dict:
    """Run the full product-investor matcher pipeline.

    Accepts product IDs and client selection criteria, returns ranked
    client×product proposals with buying scores, investment rationale,
    and final proposal markdown.
    """
    return product_investor_matcher(
        product_ids=body.product_ids,
        product_source=body.product_source.value,
        client_selection=body.client_selection,
        top_n=body.top_n,
        market_outlook=body.market_outlook,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Reinvestment proposal endpoints
# ═══════════════════════════════════════════════════════════════════════════


@app.post(
    "/api/v1/reinvestment-proposals",
    response_model=ProposalResponse,
    summary="Generate reinvestment proposals for explicit client×product targets",
    description=(
        "Generate one reinvestment proposal per (client_id, source_product_id) "
        "pair.\n\n"
        "### Request body\n\n"
        "| Field | Type | Description |\n"
        "|---|---|---|\n"
        "| `reinvestment_targets` | array (required) | List of "
        "`{client_id, source_product_id}` pairs. Each pair produces one "
        "proposal. |\n"
        + _COMMON_SCORING_PARAMS_DOC
        + "\n\n"
        "### Example\n\n"
        "```json\n"
        "{\n"
        "  \"reinvestment_targets\": [\n"
        "    {\"client_id\": \"PB-HK-000007-5\", \"source_product_id\": \"PROD053\"}\n"
        "  ],\n"
        "  \"max_candidates_per_product_type\": 2,\n"
        "  \"max_candidates_per_client\": 10,\n"
        "  \"risk_rating_hard_filter\": true,\n"
        "  \"response_mode\": \"both\",\n"
        "  \"include_debug_scores\": false\n"
        "}\n"
        "```"
    ),
)
def get_reinvestment_proposals(body: ProposeReinvestmentRequest) -> dict:
    """Generate reinvestment proposals for one or more target pairs."""
    return propose_reinvestment(
        reinvestment_targets=[t.model_dump() for t in body.reinvestment_targets],
        max_candidates_per_product_type=body.max_candidates_per_product_type,
        max_candidates_per_client=body.max_candidates_per_client,
        risk_rating_hard_filter=body.risk_rating_hard_filter,
        response_mode=body.response_mode,
        include_llm_input=body.include_llm_input,
        include_market_outlook=body.include_market_outlook,
        include_debug_scores=body.include_debug_scores,
    )


@app.post(
    "/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings",
    response_model=ProposalResponse,
    summary="Discover maturing holdings and generate reinvestment proposals",
    description=(
        "Discover clients with maturing bond/bond-fund holdings within a "
        "look-ahead window, then generate one reinvestment proposal per client.\n\n"
        "### Request body\n\n"
        "| Field | Type | Description |\n"
        "|---|---|---|\n"
        "| `within_days` | int (≥1) | Look ahead this many days for maturing "
        "holdings. Default `365`. |\n"
        "| `as_of_date` | string (ISO 8601) | Reference date for maturity "
        "calculation. Defaults to today. |\n"
        "| `max_clients` | int (1–100) | Cap on number of clients to process. "
        "Default `2`. |\n"
        + _COMMON_SCORING_PARAMS_DOC
    ),
)
def propose_for_maturing_holdings(body: MaturingHoldingsRequest) -> dict:
    """Discover clients with maturing bond/bond-fund holdings and generate reinvestment proposals."""
    return propose_reinvestment_for_maturing_holdings(
        within_days=body.within_days,
        as_of_date=body.as_of_date,
        max_clients=body.max_clients,
        max_candidates_per_product_type=body.max_candidates_per_product_type,
        max_candidates_per_client=body.max_candidates_per_client,
        risk_rating_hard_filter=body.risk_rating_hard_filter,
        response_mode=body.response_mode,
        include_llm_input=body.include_llm_input,
        include_market_outlook=body.include_market_outlook,
        include_debug_scores=body.include_debug_scores,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Product Opportunity Proposal endpoints
# ═══════════════════════════════════════════════════════════════════════════


class OpportunityProposalRequest(BaseModel):
    """Single-shot product opportunity proposal."""
    model_config = ConfigDict(extra="allow")

    client_id: str = Field(
        ..., description="Client identifier",
        json_schema_extra={"example": "PB-HK-000007-5"},
    )
    product_id: str = Field(
        ..., description="Primary suggested product ID",
        json_schema_extra={"example": "PROD054"},
    )
    rationale: str = Field("", description="Freeform markdown rationale")
    suggested_products_and_rationale: str = Field(
        "",
        description="Matcher per-client analysis in markdown (product recommendations, fitness scores, funding sources, client needs). Populated from product_investor_matcher output.",
        json_schema_extra={"default": ""},
    )
    run_matcher: bool = Field(False, description="Run matcher to obtain rationale")
    market_outlook: str | None = Field(
        default=None, json_schema_extra={"example": "Rates remain elevated; favor short-duration high-quality credit over long duration."},
    )
    alternative_count: int = Field(3, description="Number of alternative products", ge=0)


class OpportunityProposalResponse(BaseModel):
    client_id: str
    product_id: str
    output_filename: str
    proposal_markdown: str
    metadata: dict = Field(default_factory=dict)


class AutomatchRequest(BaseModel):
    """Batch product opportunity proposal via product-investor matching.

    Example payload::

        {
          "product_source": "default_yaml",
          "product_ids": ["bank_recommended"],
          "client_selection": {"risk_rating": [1, 5]},
          "run_matcher": true,
          "max_proposals": 2
        }

    When *product_source* is ``default_yaml``, *product_ids* may contain
    group names defined in ``config_planbot.yaml`` under ``product_groups``
    (expanded to their member product IDs).  When *product_source* is
    ``request_payload``, *product_ids* are always literal product IDs.
    """
    model_config = ConfigDict(extra="allow")

    product_source: ProductSource = Field(
        ProductSource.DEFAULT_YAML,
        json_schema_extra={"example": "default_yaml"},
    )
    product_ids: list[str] = Field(
        default=["bank_recommended"],
        json_schema_extra={"example": ["bank_recommended"]},
    )
    client_selection: dict | None = Field(
        None, json_schema_extra={"example": {"risk_rating": [1, 5]}},
    )
    run_matcher: bool = Field(False, json_schema_extra={"example": True})
    max_proposals: int = Field(
        10, json_schema_extra={"example": 2},
    )


class AutomatchProposalItem(BaseModel):
    client_id: str
    product_id: str
    output_filename: str | None = None
    proposal_markdown: str
    metadata: dict = Field(default_factory=dict)


class AutomatchResponse(BaseModel):
    matcher_run_id: str
    total_clients_matched: int
    total_proposals_generated: int
    proposals: list[AutomatchProposalItem] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


@app.post(
    "/api/v1/product-opportunity-proposal",
    response_model=OpportunityProposalResponse,
)
def generate_opportunity_proposal(body: OpportunityProposalRequest) -> dict:
    """Generate a single product opportunity proposal for one client–product pair."""
    return propose_product_opportunity(
        client_id=body.client_id,
        product_id=body.product_id,
        rationale=body.rationale,
        suggested_products_and_rationale=body.suggested_products_and_rationale,
        run_matcher=body.run_matcher,
        market_outlook=body.market_outlook,
        alternative_count=body.alternative_count,
    )


@app.post(
    "/api/v1/product-opportunity-proposal-automatch",
    response_model=AutomatchResponse,
)
def generate_opportunity_proposal_automatch(body: AutomatchRequest) -> dict:
    """Run product-investor matching, then generate one proposal per pair."""
    return propose_product_opportunity_automatch(
        product_ids=body.product_ids,
        product_source=body.product_source,
        client_selection=body.client_selection,
        run_matcher=body.run_matcher,
        max_proposals=body.max_proposals,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Portfolio Review endpoint
# ═══════════════════════════════════════════════════════════════════════════


class PortfolioReviewRequest(BaseModel):
    """Generate a portfolio health review for a single client."""

    client_id: str = Field(
        ..., description="Client identifier, e.g. 'PB-HK-000001-8'",
        json_schema_extra={"example": "PB-HK-000001-8"},
    )
    market_outlook: str | None = Field(
        default=None, json_schema_extra={"example": "Rates remain elevated; favor short-duration high-quality credit over long duration."},
    )


class PortfolioReviewResponse(BaseModel):
    client_id: str
    output_filename: str
    proposal_markdown: str


@app.post(
    "/api/v1/portfolio-review",
    response_model=PortfolioReviewResponse,
)
def generate_portfolio_review(body: PortfolioReviewRequest) -> dict:
    """Generate a portfolio health review for a single client.

    Takes only a ``client_id``.  Fetches client profile + holdings,
    product catalog, and market outlook from the data service, then
    invokes the LLM to produce a portfolio health review in markdown.
    """
    return propose_portfolio_review(
        client_id=body.client_id,
        market_outlook=body.market_outlook,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Data lookup endpoints (moved from the data server for the front-end app)
# ═══════════════════════════════════════════════════════════════════════════


class SimilarProductSearchRequest(BaseModel):
    """Proximity search returning products ranked by similarity."""

    query: dict = Field(
        ..., description="Product attributes to match against",
        json_schema_extra={"example": {"risk_rating": 1, "expected_return": 3.7, "product_type": "bond"}},
    )
    top_n: int = Field(3, ge=1, le=50)
    risk_rating_hard_filter: bool = True
    diversification: bool = True
    max_candidates_per_product_type: int = Field(2, ge=1, le=10)
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
    max_candidates_per_product_type: int = Field(2, ge=1, le=10)
    max_candidates_per_client: int | None = Field(None, ge=1, le=50)
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
        None, json_schema_extra={"example": ["diversification_score"]},
    )


# ── Response models (for OpenAPI documentation only) ──────────────────────


class SimilarProductSearchResult(BaseModel):
    results: list[dict] = Field(default_factory=list)


class CandidateResultItem(BaseModel):
    product_id: str = Field(..., json_schema_extra={"example": "PROD054"})
    similarity_score: float = Field(..., json_schema_extra={"example": 0.9933})
    name: str | None = None
    product_type: str | None = None
    investment_note: str | None = None


class CandidatesResult(BaseModel):
    results_by_client: dict[str, list[CandidateResultItem]] = Field(default_factory=dict)


class ComponentScores(BaseModel):
    model_config = ConfigDict(extra="allow")
    risk_rating_match_score: float | None = None
    diversification_score: float | None = None
    has_similar_investment_experience_score: float | None = None
    better_product_score: float | None = None


class FitnessScoreItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    client_id: str
    product_id: str
    product_name: str | None = None
    investment_note: str | None = None
    fitness_score: float
    component_scores: ComponentScores


class FitnessScoreResult(BaseModel):
    results: list[FitnessScoreItem] = Field(default_factory=list)


class ReadinessItem(BaseModel):
    rank: int
    client_id: str
    name: str
    investor_readiness_score: float
    cash_score: float
    concentration_score: float
    active_score: float
    life_stage_score: float


class MaturingHoldingItem(BaseModel):
    client_id: str
    product_id: str
    market_value: float
    days_to_mature: int


# ── Endpoints ─────────────────────────────────────────────────────────────


def _example_response(example) -> dict:
    """OpenAPI 200 response body with a single real-data example."""
    return {200: {"content": {"application/json": {"example": example}}}}


_MATURING_EXAMPLE = {
    "client_id": "PB-HK-000007-5",
    "product_id": "PROD053",
    "market_value": 3360000.0,
    "days_to_mature": 17,
}

_READINESS_EXAMPLE = {
    "rank": 1,
    "client_id": "PB-HK-000001-8",
    "name": "David Kim",
    "investor_readiness_score": 29.5,
    "cash_score": 8.0,
    "concentration_score": 10.0,
    "active_score": 3.0,
    "life_stage_score": 8.5,
}

_SEARCH_SIMILAR_EXAMPLE = {
    "results": [
        {
            "product_id": "PROD044",
            "name": "China Government Bond",
            "product_type": "bond",
            "risk_rating": 1,
            "expected_return": 3.5,
            "investment_note": "Individual bonds allow precise maturity-matching for liability-driven investing.",
            "similarity_score": 1.0,
        }
    ]
}

_CANDIDATES_EXAMPLE = {
    "results_by_client": {
        "PB-HK-000007-5": [
            {
                "product_id": "PROD054",
                "name": "US Treasury 3.75% 30Jun27",
                "product_type": "bond",
                "investment_note": "Individual bonds allow precise maturity-matching for liability-driven investing.",
                "similarity_score": 0.9366,
            }
        ]
    }
}

_FITNESS_EXAMPLE = {
    "results": [
        {
            "client_id": "PB-HK-000007-5",
            "product_id": "PROD054",
            "product_name": "US Treasury 3.75% 30Jun27",
            "investment_note": "Individual bonds allow precise maturity-matching for liability-driven investing.",
            "fitness_score": 0.75,
            "component_scores": {
                "risk_rating_match_score": 2.5,
                "diversification_score": 0.0,
                "has_similar_investment_experience_score": 0.0,
                "better_product_score": 0.0,
            },
        }
    ]
}


@app.get(
    "/api/v1/clients/holdings/maturing",
    response_model=list[MaturingHoldingItem],
    responses=_example_response([_MATURING_EXAMPLE]),
)
def get_holdings_maturing(
    product_types: str | None = Query(
        default=None,
        description="Comma-separated list of product types to include (e.g. `bond,bond_fund`). "
        "Omit to default to `bond` only.",
        openapi_examples={
            "Bonds + bond funds": {"value": "bond,bond_fund"},
        },
    ),
    within_days: int = Query(
        default=14, description="Calendar days to maturity.",
        openapi_examples={"One year": {"value": 365}},
    ),
    as_of_date: str | None = Query(
        default=None,
        description="Reference date (ISO 8601). Defaults to system date.",
        openapi_examples={"Explicit date": {"value": "2026-08-14"}},
    ),
) -> list[dict]:
    """Find clients with bonds or fixed-income products maturing."""
    pts = [t.strip() for t in product_types.split(",")] if product_types else None
    return search_holdings_maturing(
        product_types=pts,
        within_days=within_days,
        as_of_date=as_of_date,
    )


@app.get(
    "/api/v1/clients/readiness",
    response_model=list[ReadinessItem],
    responses=_example_response([_READINESS_EXAMPLE]),
)
def get_investor_readiness(
    top_n: int = Query(
        default=10,
        description="Max results. 0 = return all.",
        openapi_examples={"Top 10": {"value": 10}},
    ),
) -> list[dict]:
    """Return clients ranked by investor readiness score."""
    ranked = search_by_investor_readiness_score(top_n or None)
    return [
        {
            "rank": r["rank"],
            "client_id": r["client_id"],
            "name": r["name"],
            "investor_readiness_score": r["total_score"],
            "cash_score": r["s_cash"],
            "concentration_score": r["s_concentration"],
            "active_score": r["s_active"],
            "life_stage_score": r["s_lifestage"],
        }
        for r in ranked
    ]


@app.post(
    "/api/v1/products/search-similar",
    response_model=SimilarProductSearchResult,
    responses=_example_response(_SEARCH_SIMILAR_EXAMPLE),
)
def search_similar_products(body: SimilarProductSearchRequest) -> dict:
    """Proximity search returning products ranked by similarity."""
    return search_similar(
        query=body.query,
        top_n=body.top_n,
        risk_rating_hard_filter=body.risk_rating_hard_filter,
        diversification=body.diversification,
        max_candidates_per_product_type=body.max_candidates_per_product_type,
        exclude_product_ids=body.exclude_product_ids,
    )


@app.post(
    "/api/v1/products/reinvestment-candidates",
    response_model=CandidatesResult,
    responses=_example_response(_CANDIDATES_EXAMPLE),
)
def get_reinvestment_candidates(body: ReinvestmentCandidatesRequest) -> dict:
    """Find reinvestment candidates per client."""
    return search_reinvestment_candidates(
        client_ids=body.client_ids,
        source_product_id=body.source_product_id,
        max_candidates_per_product_type=body.max_candidates_per_product_type,
        max_candidates_per_client=body.max_candidates_per_client,
        risk_rating_hard_filter=body.risk_rating_hard_filter,
        exclude_product_ids=body.exclude_product_ids,
    )


@app.post(
    "/api/v1/products/fitness-score",
    response_model=FitnessScoreResult,
    responses=_example_response(_FITNESS_EXAMPLE),
)
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

    _ROOT = Path(__file__).resolve().parents[2]
    config_path = _ROOT / "config" / "config_planbot.yaml"
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    server_cfg = (cfg.get("server") or {}).get("proposal", {})

    uvicorn.run(
        "src.integrations.proposal_server:app",
        host=server_cfg.get("host", "127.0.0.1"),
        port=server_cfg.get("port", 8000),
        log_config=None,
    )
