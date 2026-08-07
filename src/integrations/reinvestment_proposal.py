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

import yaml

from src.integrations.client_api import search_by_id, search_holdings_maturing
from src.integrations.product_tool import (
    search_by_product_id,
    search_similar_to_product,
)
from src.planbot.crew_workflow import run_crew_planbot
from src.planbot.http_resolver import HttpApiResolver
from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_PRODUCT_CATALOG,
    ReferenceDocument,
)
from src.planbot.workflow import build_llm_input
from src.shared.config_loader import load_config
from src.shared.resolver_formatters import (
    build_proposal_resolver,
    compute_pfs_for_products,
    format_client_and_holdings,
    format_irs_section,
    format_product_catalog,
    read_http_resolver_config,
)

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def propose_reinvestment(
    reinvestment_targets: list[dict[str, str]],
    max_per_product_type: int = 2,
    top_n_per_client: int = 10,
    risk_rating_hard_filter: bool = True,
    response_mode: str = "path",
    include_llm_input: bool = False,
    include_market_outlook: bool = True,
    include_debug_scores: bool = False,
) -> dict:
    """Generate reinvestment proposals for one or more target pairs.

    Parameters
    ----------
    reinvestment_targets : list[dict]
        Each dict must contain ``client_id`` and ``source_product_id``.
    max_per_product_type : int
        Diversification cap for candidate selection.
    top_n_per_client : int
        Maximum number of candidate products passed to the LLM.
    risk_rating_hard_filter : bool
        Whether to enforce the hard risk filter in the product API.
    response_mode : str
        One of ``path``, ``markdown``, ``both``.
    include_llm_input : bool
        Whether to include the assembled LLM input block in API output.
    include_market_outlook : bool
        Whether to attach market outlook references.
    include_debug_scores : bool
        Whether to return intermediate score-card output.

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
                max_per_product_type=max_per_product_type,
                top_n_per_client=top_n_per_client,
                risk_rating_hard_filter=risk_rating_hard_filter,
                response_mode=response_mode,
                include_llm_input=include_llm_input,
                include_market_outlook=include_market_outlook,
                include_debug_scores=include_debug_scores,
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
    max_per_product_type: int = 2,
    top_n_per_client: int = 10,
    risk_rating_hard_filter: bool = True,
    response_mode: str = "path",
    include_llm_input: bool = False,
    include_market_outlook: bool = True,
    include_debug_scores: bool = False,
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
    max_per_product_type : int
        Passed to :func:`propose_reinvestment`.
    top_n_per_client : int
        Passed to :func:`propose_reinvestment`.
    risk_rating_hard_filter : bool
        Passed to :func:`propose_reinvestment`.
    response_mode : str
        Passed to :func:`propose_reinvestment`.
    include_llm_input : bool
        Passed to :func:`propose_reinvestment`.
    include_market_outlook : bool
        Passed to :func:`propose_reinvestment`.
    include_debug_scores : bool
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
        max_per_product_type=max_per_product_type,
        top_n_per_client=top_n_per_client,
        risk_rating_hard_filter=risk_rating_hard_filter,
        response_mode=response_mode,
        include_llm_input=include_llm_input,
        include_market_outlook=include_market_outlook,
        include_debug_scores=include_debug_scores,
    )


# ---------------------------------------------------------------------------
# Per-target processing — builds in-memory resolver → calls CrewAI → returns result
# ---------------------------------------------------------------------------


def _process_one_target(
    app_config: Any,
    client_id: str,
    source_product_id: str,
    max_per_product_type: int,
    top_n_per_client: int,
    risk_rating_hard_filter: bool,
    response_mode: str,
    include_llm_input: bool,
    include_market_outlook: bool,
    include_debug_scores: bool,
) -> dict:
    """Fetch data, build in-memory resolver, invoke CrewAI, return result object."""

    item: dict[str, Any] = {
        "client_id": client_id,
        "source_product_id": source_product_id,
    }

    http_cfg = read_http_resolver_config(_CONFIG_PATH)

    if http_cfg is not None:
        # ── Phase B: HTTP resolver ──────────────────────────────────
        planbot_config = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        data_service_url: str = (planbot_config.get("common") or {}).get("data_service_url", "http://localhost:8000/api/v1")
        # Strip /api/v1 if present — HttpApiResolver appends paths.
        base_url = data_service_url.replace("/api/v1", "")

        resolver = HttpApiResolver(
            client_id=client_id,
            source_product_id=source_product_id,
            base_url=base_url,
            timeout=http_cfg.get("timeout_seconds", 30),
            max_retries=http_cfg.get("max_retries", 3),
            retry_backoff_factor=http_cfg.get("retry_backoff_factor", 0.5),
        )

        # Access resolver properties to trigger HTTP calls.
        # Wrap in try/except so network errors include the failing URL.
        try:
            _client_ok = resolver.client_profile
            _product_ok = resolver.source_product
        except Exception as exc:
            msg = (
                f"Data service unreachable at {data_service_url}: {exc}. "
                f"Is the data server running?"
            )
            LOGGER.error(msg)
            raise ConnectionError(msg) from exc

        # Early-exit checks — surface data errors as structured failures
        if _client_ok is None:
            msg = (
                f"Client not found via HTTP: {client_id} "
                f"(data_service_url={data_service_url})"
            )
            LOGGER.warning(msg)
            raise LookupError(msg)

        if _product_ok is None:
            msg = (
                f"Source product not found via HTTP: {source_product_id} "
                f"(data_service_url={data_service_url})"
            )
            LOGGER.warning(msg)
            raise LookupError(msg)

        candidate_products = resolver.candidate_products
        item["candidate_products"] = candidate_products

        api_resolver = resolver.as_callable()

        # For llm_input / debug_scores, use the cached raw data
        client_profile = resolver.client_profile
        source_product = resolver.source_product
    else:
        # ── Phase A: local imports (fallback) ──────────────────────
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
            top_n=top_n_per_client,
            max_per_product_type=max_per_product_type,
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

        # ── Compute PFS for suggested + alternatives ──────────────
        pfs_scores = compute_pfs_for_products(
            client_id=client_id,
            suggested_product_id=source_product_id,
            alternative_products=candidate_products,
        )

        api_resolver = _build_api_resolver(
            client_id, client_profile, source_product, source_product_id,
            candidate_products, pfs_scores=pfs_scores,
        )

    # 5 ─ Build client-scoped output filename ────────────────────────────
    output_override = f"runs/reinvestment_proposal/reinvestment_proposal_{client_id}.md"

    # 6 ─ Invoke CrewAI with api:// patterns (no temp files on disk) ─────
    crew_result = run_crew_planbot(
        app_config=app_config,
        config_path=str(_CONFIG_PATH),
        proposal_name="reinvestment_proposal",
        runtime_reference_overrides={
            "client_profiles": [API_CLIENT_PROFILE],
            "product_catalogs": [API_PRODUCT_CATALOG],
        },
        output_file_override=output_override,
        api_resolver=api_resolver,
    )
    output_path = str(crew_result.output_path)
    markdown_output = crew_result.output_path.read_text()

    if response_mode in ("path", "both"):
        item["output_path"] = output_path

    if response_mode in ("markdown", "both"):
        item["markdown_output"] = markdown_output

    # 7 ─ llm_input (optional) ──────────────────────────────────────────
    if include_llm_input:
        item["llm_input"] = build_llm_input(
            client_profile=client_profile,
            source_product=source_product,
            candidate_products=candidate_products,
            include_market_outlook=include_market_outlook,
        )

    # 8 ─ Debug scores (optional) ───────────────────────────────────────
    if include_debug_scores:
        item["debug_scores"] = _build_debug_scores(
            client_profile=client_profile,
            candidate_products=candidate_products,
        )

    return item


# ---------------------------------------------------------------------------
# In-memory API resolver (replaces temp-file approach)
# ---------------------------------------------------------------------------


def _build_api_resolver(
    client_id: str,
    client_profile: dict,
    source_product: dict,
    source_product_id: str,
    candidate_products: list[dict],
    pfs_scores: dict[str, dict] | None = None,
) -> Callable[[str], ReferenceDocument]:
    """Build a resolver closure for reinvestment proposals.

    Uses the shared ``build_proposal_resolver`` — only the client-content
    extra sections and product catalog differ per proposal.
    """

    cp = client_profile
    extra: list[str] = []
    irs_text = format_irs_section(
        total=cp.get("investor_readiness_score"),
        cash_drag=cp.get("cash_score"),
        concentration=cp.get("concentration_score"),
        active_management=cp.get("active_score"),
        life_stage=cp.get("life_stage_score"),
    )
    if irs_text:
        extra.append(irs_text)

    extra.append(
        "# Wallet Inflow Event\n\n"
        "The following product is maturing:\n"
        f"- Product ID: {source_product_id}\n"
        f"- Product Name: {source_product.get('name', source_product_id)}"
    )

    return build_proposal_resolver(
        client_content=format_client_and_holdings(cp, extra_sections=extra),
        product_content=format_product_catalog(
            suggested=source_product,
            holdings=cp.get("holdings", []),
            alternatives=candidate_products or None,
            pfs_scores=pfs_scores or None,
        ),
    )


# ---------------------------------------------------------------------------
# debug_scores builder
# ---------------------------------------------------------------------------


def _build_debug_scores(
    client_profile: dict,
    candidate_products: list[dict],
) -> dict:
    """Build debug score-card output for migration testing."""
    return {
        "investor_readiness_score": {
            "client_id": client_profile.get("client_id"),
            "total_score": client_profile.get("investor_readiness_score"),
            "component_scores": {
                "cash_score": client_profile.get("cash_score"),
                "concentration_score": client_profile.get("concentration_score"),
                "active_score": client_profile.get("active_score"),
                "life_stage_score": client_profile.get("life_stage_score"),
            },
        },
        "product_fitness_scores": [
            {
                "client_id": client_profile.get("client_id"),
                "product_id": c.get("product_id"),
                "fitness_score": c.get("similarity_score"),
            }
            for c in candidate_products
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ═══════════════════════════════════════════════════════════════════════════
# End of module
# ═══════════════════════════════════════════════════════════════════════════
