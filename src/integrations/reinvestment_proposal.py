"""
Reinvestment Proposal API — Full pipeline from API data to LLM-generated proposal.

Implements the contract defined in:
    docs/prod_spec/reinvestment_proposal_api.md

All client and product data are retrieved through the integration APIs.
The endpoint composes reference files, invokes CrewAI, and returns output paths.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.integrations.client_api import search_by_id, search_holdings_maturing
from src.integrations.product_tool import (
    search_by_product_id,
    search_similar_to_product,
)
from src.planbot.crew_workflow import run_crew_planbot
from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_PRODUCT_CATALOG,
    ReferenceDocument,
)
from src.planbot.pipeline_engine import PipelineEngine, get_input_default_sources
from src.planbot.workflow import read_prompt_snapshot
from src.shared.config_loader import load_config
from src.shared.market_outlook_utils import (
    API_MARKET_OUTLOOK,
    resolve_market_outlook,
)
from src.shared.resolver_formatters import (
    build_proposal_resolver,
    compute_pfs_for_products,
    format_client_and_holdings,
    format_irs_section,
    format_product_catalog,
    resolve_holdings_to_products,
)

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def propose_reinvestment(
    reinvestment_targets: list[dict[str, str]],
    max_candidates_per_product_type: int = 2,
    max_candidates_per_client: int = 10,
    risk_rating_hard_filter: bool = True,
    response_mode: str = "path",
    output_prompt_to_llm: bool = False,
    market_outlook: str | None = None,
    market_outlook_source: str | None = None,
) -> dict:
    """Generate reinvestment proposals for one or more target pairs.

    Parameters
    ----------
    reinvestment_targets : list[dict]
        Each dict must contain ``client_id`` and ``source_product_id``.
    max_candidates_per_product_type : int
        Diversification cap for candidate selection.
    max_candidates_per_client : int
        Maximum number of candidate products passed to the LLM.
    risk_rating_hard_filter : bool
        Whether to enforce the hard risk filter in the product API.
    response_mode : str
        One of ``path``, ``markdown``, ``both``.
    output_prompt_to_llm : bool
        Whether to return the exact prompt sent to the LLM (per item, as
        ``prompt_to_llm``).  Independent of ``response_mode``.
    market_outlook : str | None
        Free-form market narrative for the LLM context.
    market_outlook_source : str | None
        ``"request"`` or ``"static"``.  ``static`` ignores ``market_outlook``
        and always uses the static default.

    Returns
    -------
    dict
        Response payload containing ``status`` and ``results_by_client``.
    """
    if response_mode not in ("path", "markdown", "both"):
        raise ValueError(
            f"Invalid response_mode: {response_mode!r}. "
            "Must be one of: path, markdown, both."
        )

    app_config = load_config(str(_ROOT_DIR / "config" / "config.yaml"))

    results: list[dict] = []

    errors_occurred = False

    for target in reinvestment_targets:
        client_id = target.get("client_id")
        source_product_id = target.get("source_product_id")

        if not client_id or not source_product_id:
            LOGGER.warning(
                "Skipping target with missing client_id or source_product_id: %s",
                target,
            )
            results.append({
                "client_id": client_id or "<missing>",
                "source_product_id": source_product_id or "<missing>",
                "error": "Missing required field 'client_id' or 'source_product_id'.",
            })
            errors_occurred = True
            continue

        try:
            result = _process_one_target(
                app_config=app_config,
                client_id=client_id,
                source_product_id=source_product_id,
                max_candidates_per_product_type=max_candidates_per_product_type,
                max_candidates_per_client=max_candidates_per_client,
                risk_rating_hard_filter=risk_rating_hard_filter,
                response_mode=response_mode,
                output_prompt_to_llm=output_prompt_to_llm,
                market_outlook=market_outlook,
                market_outlook_source=market_outlook_source,
            )
        except Exception as exc:
            LOGGER.error("Error processing %s/%s: %s", client_id, source_product_id, exc)
            result = {
                "client_id": client_id,
                "source_product_id": source_product_id,
                "error": str(exc),
            }
            errors_occurred = True

        results.append(result)

    return {
        "status": "partial_error" if errors_occurred else "success",
        "results_by_client": results,
    }


# ---------------------------------------------------------------------------
# Convenience: discover maturing → propose reinvestment
# ---------------------------------------------------------------------------


def propose_reinvestment_for_maturing_holdings(
    *,
    within_days: int = 365,
    as_of_date: str | None = None,
    max_clients: int = 2,
    max_candidates_per_product_type: int = 2,
    max_candidates_per_client: int = 10,
    risk_rating_hard_filter: bool = True,
    response_mode: str = "path",
    output_prompt_to_llm: bool = False,
    market_outlook: str | None = None,
    market_outlook_source: str | None = None,
) -> dict:
    """Discover maturing bond/bond fund holdings and generate reinvestment proposals.

    Calls :func:`search_holdings_maturing` internally, deduplicates by
    client, caps at ``max_clients``, and delegates to
    :func:`propose_reinvestment`.

    Parameters
    ----------
    within_days : int
        Maturity window in days (default 365).
    as_of_date : str | None
        Reference date for maturity calculation (default today).
    max_clients : int
        Safety cap on the number of clients to process (default 2).
    max_candidates_per_product_type : int
        Passed to :func:`propose_reinvestment`.
    max_candidates_per_client : int
        Passed to :func:`propose_reinvestment`.
    risk_rating_hard_filter : bool
        Passed to :func:`propose_reinvestment`.
    response_mode : str
        Passed to :func:`propose_reinvestment`.
    output_prompt_to_llm : bool
        Passed to :func:`propose_reinvestment`.

    Returns
    -------
    dict
        Same as :func:`propose_reinvestment`.
    """
    maturing = search_holdings_maturing(
        product_types=["bond", "bond_fund"],
        within_days=within_days,
        as_of_date=as_of_date,
    )

    seen_clients: set[str] = set()
    targets: list[dict[str, str]] = []
    for row in maturing:
        cid = row["client_id"]
        if cid not in seen_clients:
            seen_clients.add(cid)
            targets.append({
                "client_id": cid,
                "source_product_id": row["product_id"],
            })

    targets = targets[:max_clients]

    LOGGER.info(
        "reinvest_maturing: discovered %d maturing across %d clients, processing %d",
        len(maturing), len(seen_clients), len(targets),
    )

    return propose_reinvestment(
        reinvestment_targets=targets,
        max_candidates_per_product_type=max_candidates_per_product_type,
        max_candidates_per_client=max_candidates_per_client,
        risk_rating_hard_filter=risk_rating_hard_filter,
        response_mode=response_mode,
        output_prompt_to_llm=output_prompt_to_llm,
        market_outlook=market_outlook,
        market_outlook_source=market_outlook_source,
    )


# ---------------------------------------------------------------------------
# Per-target processing — builds in-memory resolver → calls CrewAI → returns result
# ---------------------------------------------------------------------------


def _process_one_target(
    app_config: Any,
    client_id: str,
    source_product_id: str,
    max_candidates_per_product_type: int,
    max_candidates_per_client: int,
    risk_rating_hard_filter: bool,
    response_mode: str,
    output_prompt_to_llm: bool,
    market_outlook: str | None = None,
    market_outlook_source: str | None = None,
) -> dict:
    """Fetch data, build in-memory resolver, invoke CrewAI, return result object."""

    item: dict[str, Any] = {
        "client_id": client_id,
        "source_product_id": source_product_id,
    }

    # Resolve the effective market outlook per the source selection
    # (request → yaml default_source → "request").
    effective_market_outlook = resolve_market_outlook(
        market_outlook,
        market_outlook_source,
        get_input_default_sources(_CONFIG_PATH).get("market_outlook", "request"),
    )

    # Load pipeline config once — exposes input defs including composite
    # `include` flags that drive formatter assembly below.
    pipeline_engine = PipelineEngine(
        app_config, config_path=_CONFIG_PATH, proposal_id="reinvestment"
    ).load()
    include_by_id = {inp.id: inp.include for inp in pipeline_engine.inputs}

    # Data is fetched through the adapter-backed functions below.  With
    # ``get_client_product_from_restapi: false`` these hit DuckDB directly; with
    # ``true`` they use the REST adapter → bank simulator.  Enrichment
    # (derived fields) and candidate selection are computed in-process, so the
    # bank stays a pure data pipe.

    client_profile = search_by_id(client_id)
    if client_profile is None:
        msg = f"Client not found: {client_id}"
        LOGGER.warning(msg)
        raise LookupError(msg)

    source_product = search_by_product_id(source_product_id)
    if source_product is None:
        msg = f"Source product not found: {source_product_id}"
        LOGGER.warning(msg)
        raise LookupError(msg)

    cand_result = search_similar_to_product(
        source_product,
        top_n=max_candidates_per_client,
        max_candidates_per_product_type=max_candidates_per_product_type,
        risk_rating_hard_filter=risk_rating_hard_filter,
    )
    candidates_raw = cand_result.get("results", [])

    candidate_products = []
    for c in candidates_raw:
        pid = c.get("product_id", "")
        prod = search_by_product_id(pid) or {}
        full = dict(prod)
        full["similarity_score"] = c.get("similarity_score")
        candidate_products.append(full)

    item["candidate_products"] = candidate_products

    # ── Compute PFS (only when product_catalog includes it) ──────
    cp_include = include_by_id.get("client_profile", {})
    catalog_include = include_by_id.get("product_catalog", {})
    pfs_scores = None
    semantic_available = None
    if catalog_include.get("product_fitness_scores"):
        pfs_scores, semantic_available = compute_pfs_for_products(
            client_id=client_id,
            suggested_product_id=source_product_id,
            alternative_products=candidate_products,
        )

    # ── Build api_resolver with composite extras per `include` flags ──
    cp = client_profile
    extra: list[str] = []
    if cp_include.get("investor_readiness_score"):
        irs_text = format_irs_section(
            total=cp.get("investor_readiness_score"),
            cash_drag=cp.get("cash_score"),
            concentration=cp.get("concentration_score"),
            active_management=cp.get("active_score"),
            life_stage=cp.get("life_stage_score"),
        )
        if irs_text:
            extra.append(irs_text)
    if cp_include.get("wallet_inflow_event"):
        extra.append(
            "# Wallet Inflow Event\n\n"
            "The following product is maturing:\n"
            f"- Product ID: {source_product_id}\n"
            f"- Product Name: {source_product.get('name', source_product_id)}"
        )

    # Resolve holdings to full product dicts for the catalog.
    holdings_products = resolve_holdings_to_products(cp.get("holdings", []))

    api_resolver = build_proposal_resolver(
        client_content=format_client_and_holdings(cp, extra_sections=extra),
        product_content=format_product_catalog(
            suggested=source_product,
            holdings=holdings_products or None,
            alternatives=candidate_products or None,
            pfs_scores=pfs_scores or None,
            semantic_embedding_available=semantic_available if pfs_scores else None,
        ),
        market_outlook=effective_market_outlook,
    )

    # ── Build runtime reference overrides for the api-backed sections ──
    # File/static sections are loaded by load_planbot_config from pipeline config.
    runtime_overrides: dict[str, list[str]] = {
        "client_profile": [API_CLIENT_PROFILE],
        "product_catalog": [API_PRODUCT_CATALOG],
    }
    if effective_market_outlook is not None:
        runtime_overrides["market_outlook"] = [API_MARKET_OUTLOOK]

    # ── Build client-scoped output filename ────────────────────────────
    output_override = f"runs/reinvestment_proposal/reinvestment_proposal_{client_id}.md"

    # ── Invoke CrewAI with api:// patterns (no temp files on disk) ─────
    crew_result = run_crew_planbot(
        app_config=app_config,
        config_path=str(_CONFIG_PATH),
        proposal_name="reinvestment",
        runtime_reference_overrides=runtime_overrides,
        output_file_override=output_override,
        api_resolver=api_resolver,
    )
    output_filename = str(crew_result.output_path)
    proposal_markdown = crew_result.output_path.read_text()

    if response_mode in ("path", "both"):
        item["output_filename"] = output_filename

    if response_mode in ("markdown", "both"):
        item["proposal_markdown"] = proposal_markdown

    # ── prompt_to_llm (optional, independent of response_mode) ──────
    if output_prompt_to_llm:
        item["prompt_to_llm"] = read_prompt_snapshot(crew_result.prompt_path)

    return item


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ═══════════════════════════════════════════════════════════════════════════
# End of module
# ═══════════════════════════════════════════════════════════════════════════
