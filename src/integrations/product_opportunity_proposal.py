"""
Product Opportunity Proposal API — Generate investment proposals for client×product pairs.

Implements the contract defined in:
    docs/prod_spec/product_opportunity_proposal.md

Extracted from product_investor_matcher.py step 9.  All client and product data are
retrieved through the integration APIs.  The endpoint composes reference files,
invokes CrewAI, and returns proposal markdown.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from src.integrations.client_api import search_by_id
from src.integrations.product_tool import (
    search_by_product_id,
    search_similar_to_product,
    search_product_by_fitness_score,
)
from src.planbot.crew_workflow import run_crew_planbot
from src.planbot.http_resolver import HttpApiResolver
from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_HOLDINGS,
    API_PRODUCT_CATALOG,
    ReferenceDocument,
)
from src.shared.config_loader import load_config
from src.shared.market_outlook_utils import (
    API_MARKET_OUTLOOK,
    format_market_outlook_section,
)
from src.shared.resolver_formatters import (
    build_api_resolver,
    format_client_profile_markdown,
    format_holdings_bullets,
    format_product_single,
)

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"
_MATCHING_RUNS_DIR = _ROOT_DIR / "runs" / "product_investor_matching"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def propose_product_opportunity(
    client_id: str,
    product_id: str,
    *,
    rationale: str = "",
    run_matcher: bool = False,
    market_outlook: str | None = None,
    alternative_count: int = 3,
) -> dict:
    """Generate a single product opportunity proposal for one client–product pair.

    Parameters
    ----------
    client_id : str
        Client identifier.
    product_id : str
        Primary suggested product ID.
    rationale : str
        Freeform markdown describing why this product fits the client.
        Supplied by the RM or passed through from product_investor_matcher.
    run_matcher : bool
        If True, run product_investor_matcher first to obtain rationale
        and fitness scores.  Default False.
    market_outlook : str | None
        Market narrative for LLM context.
    alternative_count : int
        Number of alternative products to include.  Default 3.

    Returns
    -------
    dict
        Response with client_id, product_id, output_filename, proposal_markdown, metadata.
    """
    # ── Optionally run matcher to get rationale ──────────────────────
    if run_matcher:
        from src.integrations.product_investor_matcher import product_investor_matcher

        matcher_result = product_investor_matcher(
            product_ids=[product_id],
            product_source="request_payload",
            top_n=1,
            market_outlook=market_outlook,
        )
        proposals = matcher_result.get("final_proposals", [])
        if proposals:
            matched = proposals[0]
            rationale = matched.get("rationale", rationale)
        else:
            LOGGER.warning(
                "run_matcher=true but matcher returned no pairs for client=%s product=%s",
                client_id, product_id,
            )

    return _process_one_pair(
        client_id=client_id,
        product_id=product_id,
        rationale=rationale,
        market_outlook=market_outlook,
        alternative_count=alternative_count,
    )


def propose_product_opportunity_automatch(
    product_ids: list[str],
    *,
    product_source: str = "request_payload",
    client_selection: dict | None = None,
    market_outlook: str | None = None,
    readiness_pool_size: int | None = None,
    run_matcher: bool = False,
    max_proposals: int = 3,
) -> dict:
    """Batch endpoint — runs matching, then generates one proposal per pair.

    Parameters
    ----------
    product_ids : list[str]
        Product universe to consider.
    client_selection : dict | None
        Client filter criteria.  If omitted, all clients.
    market_outlook : str | None
        Market narrative for LLM context.
    readiness_pool_size : int | None
        Top-K clients by readiness.  None = use config default.
    run_matcher : bool
        If True, run product_investor_matcher inline.  If False, load
        latest _pairs.json from runs/product_investor_matching/.
    max_proposals : int
        Cap on total proposals.  0 or -1 = unlimited.

    Returns
    -------
    dict
        Response with matcher_run_id, total_clients_matched,
        total_proposals_generated, proposals, errors.
    """
    app_config = load_config(str(_ROOT_DIR / "config" / "config.yaml"))

    # ── 1. Get matching pairs ────────────────────────────────────────
    if run_matcher:
        from src.integrations.product_investor_matcher import product_investor_matcher

        matcher_result = product_investor_matcher(
            product_ids=product_ids,
            product_source=product_source,
            client_selection=client_selection,
            top_n=max_proposals if max_proposals > 0 else 10,
            market_outlook=market_outlook,
        )
        matcher_run_id = matcher_result.get("run_id", "")
        pairs = matcher_result.get("final_proposals", [])
    else:
        matcher_run_id, pairs = _load_latest_matcher_output()
        if not pairs:
            return {
                "matcher_run_id": matcher_run_id,
                "total_clients_matched": 0,
                "total_proposals_generated": 0,
                "proposals": [],
                "errors": [{"code": "MATCHER_OUTPUT_MISSING"}],
            }

    if not product_ids:
        return {
            "matcher_run_id": matcher_run_id,
            "total_clients_matched": len(pairs),
            "total_proposals_generated": 0,
            "proposals": [],
            "errors": [{"code": "EMPTY_PRODUCT_UNIVERSE"}],
        }

    # ── 2. Fan-out per pair ──────────────────────────────────────────
    proposals: list[dict] = []
    errors: list[dict] = []

    for i, pair in enumerate(pairs):
        if max_proposals > 0 and i >= max_proposals:
            break

        cid = pair.get("client_id", "")
        pid = pair.get("product_id", "")
        if not cid or not pid:
            continue

        try:
            result = _process_one_pair(
                client_id=cid,
                product_id=pid,
                rationale=pair.get("rationale", ""),
                market_outlook=market_outlook,
                alternative_count=0,  # use matcher alternatives
                matcher_alternatives=pair.get("alternative_product_ids", []),
            )
            proposals.append(result)
        except Exception as exc:
            LOGGER.error("proposal failed for %s/%s: %s", cid, pid, exc)
            errors.append({
                "client_id": cid,
                "product_id": pid,
                "error": str(exc),
            })

    return {
        "matcher_run_id": matcher_run_id,
        "total_clients_matched": len(pairs),
        "total_proposals_generated": len(proposals),
        "proposals": proposals,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Per-pair processing
# ---------------------------------------------------------------------------


def _process_one_pair(
    client_id: str,
    product_id: str,
    *,
    rationale: str = "",
    market_outlook: str | None = None,
    alternative_count: int = 3,
    matcher_alternatives: list[str] | None = None,
) -> dict:
    """Generate a proposal for a single client×product pair."""
    item: dict[str, Any] = {
        "client_id": client_id,
        "product_id": product_id,
    }

    http_cfg = _read_http_resolver_config()

    if http_cfg is not None:
        # ── Phase B: HTTP resolver ──────────────────────────────────
        planbot_config = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        data_service_url = (planbot_config.get("common") or {}).get(
            "data_service_url", "http://localhost:8000/api/v1",
        )
        base_url = data_service_url.replace("/api/v1", "")

        resolver = HttpApiResolver(
            client_id=client_id,
            source_product_id=product_id,
            base_url=base_url,
            timeout=http_cfg.get("timeout_seconds", 30),
            max_retries=http_cfg.get("max_retries", 3),
            retry_backoff_factor=http_cfg.get("retry_backoff_factor", 0.5),
        )

        try:
            client_profile = resolver.client_profile
            source_product = resolver.source_product
        except Exception as exc:
            raise ConnectionError(
                f"Data service unreachable at {data_service_url}: {exc}"
            ) from exc

        if client_profile is None:
            raise LookupError(f"Client not found via HTTP: {client_id}")

        if source_product is None:
            raise LookupError(f"Product not found via HTTP: {product_id}")

        api_resolver = resolver.as_callable()
    else:
        # ── Phase A: direct calls ───────────────────────────────────
        client_profile = search_by_id(client_id)
        if client_profile is None:
            raise LookupError(f"Client not found: {client_id}")

        source_product = search_by_product_id(product_id)
        if source_product is None:
            raise LookupError(f"Product not found: {product_id}")

        api_resolver = _build_proposal_resolver(
            client_data=client_profile,
            product_data=source_product,
            rationale=rationale,
            market_outlook=market_outlook,
            alternative_count=alternative_count,
            matcher_alternatives=matcher_alternatives,
        )

    # ── Compute fitness scores (when not from matcher) ──────────────
    product_fitness_scores: dict[str, float] = {}
    if matcher_alternatives:
        # Reuse matcher alternatives — compute fitness for those
        all_pids = [product_id] + matcher_alternatives
        pfs_result = search_product_by_fitness_score(
            client_ids=[client_id],
            product_ids=all_pids,
            top_n=len(all_pids),
        )
        for r in pfs_result.get("results", []):
            product_fitness_scores[r["product_id"]] = r["fitness_score"]

    # ── Invoke CrewAI ───────────────────────────────────────────────
    app_config = load_config(str(_ROOT_DIR / "config" / "config.yaml"))
    output_path = (
        f"runs/product_opportunity_proposal/"
        f"product_opportunity_proposal_{client_id}_{product_id}.md"
    )

    fit_result = run_crew_planbot(
        app_config=app_config,
        config_path=str(_CONFIG_PATH),
        proposal_name="product_opportunity_proposal",
        runtime_reference_overrides={
            "client_profiles": [API_CLIENT_PROFILE, API_HOLDINGS],
            "product_catalogs": [API_PRODUCT_CATALOG],
            "market_outlook": [API_MARKET_OUTLOOK],
        },
        output_file_override=output_path,
        api_resolver=api_resolver,
    )
    proposal_markdown = fit_result.output_path.read_text()

    return {
        "client_id": client_id,
        "product_id": product_id,
        "output_filename": str(fit_result.output_path),
        "proposal_markdown": proposal_markdown,
        "metadata": {
            "model": app_config.model if hasattr(app_config, "model") else "deepseek_tool",
            "alternative_products": matcher_alternatives or [],
            "product_fitness_scores": product_fitness_scores,
        },
    }


# ---------------------------------------------------------------------------
# API resolver builder
# ---------------------------------------------------------------------------


def _build_proposal_resolver(
    client_data: dict,
    product_data: dict,
    *,
    rationale: str = "",
    market_outlook: str | None = None,
    alternative_count: int = 3,
    matcher_alternatives: list[str] | None = None,
) -> Callable[[str], ReferenceDocument]:
    """Build a resolver for a single client×product pair."""

    # Resolve alternatives
    alt_products: list[dict] = []
    if matcher_alternatives:
        for alt_id in matcher_alternatives:
            alt = search_by_product_id(alt_id)
            if alt:
                alt_products.append(alt)
    else:
        sim_result = search_similar_to_product(
            product_data,
            top_n=alternative_count,
            diversification=True,
        )
        for r in sim_result.get("results", []):
            alt = search_by_product_id(r["product_id"])
            if alt:
                alt_products.append(alt)

    # ── Build documents ──────────────────────────────────────────
    client_content = format_client_profile_markdown(client_data)
    holdings = client_data.get("holdings", [])
    if holdings:
        client_content += "\n\n" + format_holdings_bullets(holdings)
    if rationale:
        client_content += f"\n\n# Rationale\n\n{rationale}"

    return build_api_resolver({
        API_CLIENT_PROFILE: ReferenceDocument(
            path=Path("api://client_profile"),
            content=client_content,
            source_type="markdown",
        ),
        API_PRODUCT_CATALOG: ReferenceDocument(
            path=Path("api://product_catalog"),
            content=format_product_single(product_data, alternatives=alt_products or None),
            source_type="markdown",
        ),
        API_MARKET_OUTLOOK: ReferenceDocument(
            path=Path(API_MARKET_OUTLOOK),
            content=format_market_outlook_section(market_outlook),
            source_type="markdown",
        ),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_http_resolver_config() -> dict | None:
    """Read HTTP resolver settings from config_planbot.yaml."""
    planbot_config = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    common = planbot_config.get("common") or {}
    if not common.get("get_client_product_from_db"):
        return None
    return common.get("http_resolver")


def _load_latest_matcher_output() -> tuple[str, list[dict]]:
    """Load the latest _pairs.json from runs/product_investor_matching/.

    Returns (run_id, pairs).  If no file found, returns ("", []).
    """
    json_files = sorted(
        _MATCHING_RUNS_DIR.glob("*_pairs.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not json_files:
        LOGGER.warning("No _pairs.json found in %s", _MATCHING_RUNS_DIR)
        return "", []

    latest = json_files[0]
    pairs = json.loads(latest.read_text())
    # Derive run_id from filename: product_investor_matching_run-20260803-155239_pairs.json
    run_id = latest.stem.replace("_pairs", "")
    LOGGER.info("Loaded %d pairs from %s", len(pairs), latest)
    return run_id, pairs
