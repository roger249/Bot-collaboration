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
from datetime import datetime
from pathlib import Path
from typing import Any

from src.integrations.client_api import search_by_id
from src.integrations.product_tool import (
    search_by_product_id,
    search_similar_to_product,
    search_product_by_fitness_score,
)
from src.planbot.crew_workflow import run_crew_planbot
from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_PRODUCT_CATALOG,
    API_SUGGESTED_PRODUCTS_AND_RATIONALE,
    ReferenceDocument,
)
from src.planbot.pipeline_engine import PipelineEngine
from src.shared.config_loader import load_config
from src.shared.market_outlook_utils import (
    API_MARKET_OUTLOOK,
)
from src.shared.resolver_formatters import (
    build_proposal_resolver,
    compute_pfs_for_products,
    format_client_and_holdings,
    format_product_catalog,
    resolve_holdings_to_products,
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
    suggested_products_and_rationale: str = "",
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
    suggested_products_and_rationale : str
        Raw markdown from the matcher's per-client detail section (fitness scores,
        funding source, client needs analysis, concentration impact, alternatives).
        Passed to the LLM via the ``api://suggested_products_and_rationale`` path.
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
    # ── Optionally run matcher to get rationale + alternatives ──────
    matcher_alternatives: list[str] | None = None
    if run_matcher:
        from src.integrations.product_investor_matcher import product_investor_matcher

        matcher_result = product_investor_matcher(
            product_ids=[product_id],
            product_source="request_payload",
            top_n=10,  # more pairs for better chance of matching this client
            market_outlook=market_outlook,
        )
        # Find the pair for this specific client
        proposals = matcher_result.get("final_proposals", [])
        matched = next(
            (p for p in proposals
             if p.get("client_id") == client_id and p.get("product_id") == product_id),
            None,
        )
        if matched:
            rationale = matched.get("rationale", rationale)
            matcher_alternatives = matched.get("alternative_product_ids", [])
            # If caller didn't supply suggested_products_and_rationale, use the matcher's per-client block
            if not suggested_products_and_rationale:
                suggested_products_and_rationale = matched.get("matching_context", "")
        else:
            LOGGER.warning(
                "run_matcher=true but matcher returned no pair for client=%s product=%s",
                client_id, product_id,
            )

    return _process_one_pair(
        client_id=client_id,
        product_id=product_id,
        rationale=rationale,
        suggested_products_and_rationale=suggested_products_and_rationale,
        market_outlook=market_outlook,
        alternative_count=alternative_count,
        matcher_alternatives=matcher_alternatives,
    )


def propose_product_opportunity_automatch(
    product_ids: list[str],
    *,
    product_source: str = "request_payload",
    client_selection: dict | None = None,
    market_outlook: str | None = None,
    readiness_pool_size: int | None = None,
    run_matcher: bool = False,
    max_proposals: int = 10,
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

    errors: list[dict] = []

    # ── 1. Get matching pairs ────────────────────────────────────────
    if run_matcher:
        try:
            from src.integrations.product_investor_matcher import product_investor_matcher

            matcher_result = product_investor_matcher(
                product_ids=product_ids,
                product_source=product_source,
                client_selection=client_selection,
                top_n=max_proposals if max_proposals > 0 else 10,
                market_outlook=market_outlook,
            )
        except Exception as exc:
            LOGGER.exception("Matcher invocation failed: %s", exc)
            return {
                "matcher_run_id": "",
                "total_clients_matched": 0,
                "total_proposals_generated": 0,
                "proposals": [],
                "errors": [{"code": "MATCHER_ERROR", "message": str(exc)}],
            }

        matcher_run_id = matcher_result.get("run_id", "")
        pairs = matcher_result.get("final_proposals", [])
        # Surface any matcher-level errors/warnings in the response.
        matcher_errors = matcher_result.get("errors", [])
        if matcher_errors:
            errors.extend(matcher_errors)
        if not pairs:
            return {
                "matcher_run_id": matcher_run_id,
                "total_clients_matched": 0,
                "total_proposals_generated": 0,
                "proposals": [],
                "errors": errors,
            }
    else:
        try:
            matcher_run_id, pairs = _load_latest_matcher_output()
        except Exception as exc:
            LOGGER.exception("Failed to load latest matcher output: %s", exc)
            return {
                "matcher_run_id": "",
                "total_clients_matched": 0,
                "total_proposals_generated": 0,
                "proposals": [],
                "errors": [{"code": "MATCHER_OUTPUT_LOAD_ERROR", "message": str(exc)}],
            }
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
                suggested_products_and_rationale=pair.get("matching_context", ""),
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
    suggested_products_and_rationale: str = "",
    market_outlook: str | None = None,
    alternative_count: int = 3,
    matcher_alternatives: list[str] | None = None,
) -> dict:
    """Generate a proposal for a single client×product pair."""
    item: dict[str, Any] = {
        "client_id": client_id,
        "product_id": product_id,
    }

    # Data is fetched through the adapter-backed functions below.  With
    # ``get_client_product_from_restapi: false`` these hit DuckDB directly; with
    # ``true`` they use the REST adapter → bank simulator.  Enrichment and
    # alternative selection are computed in-process.

    client_profile = search_by_id(client_id)
    if client_profile is None:
        raise LookupError(f"Client not found: {client_id}")

    source_product = search_by_product_id(product_id)
    if source_product is None:
        raise LookupError(f"Product not found: {product_id}")

    client_data = client_profile
    product_data = source_product

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

    # Resolve holdings to full product dicts for the catalog
    holdings_products = resolve_holdings_to_products(client_data.get("holdings", []))

    # Compute PFS (suggested + alternatives) for the LLM prompt
    pfs_scores = compute_pfs_for_products(
        client_id=str(client_data.get("client_id", "")),
        suggested_product_id=str(product_data.get("product_id", "")),
        alternative_products=alt_products,
    )

    # Build rationale/context document
    rationale_content = ""
    if suggested_products_and_rationale:
        rationale_content += suggested_products_and_rationale
    if rationale:
        if rationale_content:
            rationale_content += "\n\n"
        rationale_content += f"## Rationale\n\n{rationale}\n"

    extra_docs: dict[str, ReferenceDocument] = {}
    if rationale_content:
        extra_docs[API_SUGGESTED_PRODUCTS_AND_RATIONALE] = ReferenceDocument(
            path=Path(API_SUGGESTED_PRODUCTS_AND_RATIONALE),
            content=rationale_content,
            source_type="markdown",
        )

    api_resolver = build_proposal_resolver(
        client_content=format_client_and_holdings(client_data),
        product_content=format_product_catalog(
            suggested=product_data,
            holdings=holdings_products or None,
            alternatives=alt_products or None,
            include_alternatives_section=(alternative_count > 0) or bool(matcher_alternatives),
            pfs_scores=pfs_scores or None,
        ),
        market_outlook=market_outlook,
        extra_docs=extra_docs or None,
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
        f"product_opportunity_{datetime.now().strftime('%H%M%S')}_{client_id}.md"
    )

    # ── Resolve pipeline inputs and merge into api_resolver ───────────
    pipeline_engine = PipelineEngine(
        app_config, config_path=_CONFIG_PATH, proposal_id="product_opportunity"
    )
    prep = pipeline_engine.prepare(
        client_id=client_id,
        product_id=product_id,
        market_outlook_text=market_outlook,
        suggested_products_and_rationale=suggested_products_and_rationale,
    )

    # Merge pre-resolved file docs into api_resolver
    if prep.file_reference_docs:
        _original_po = api_resolver
        _doc_map_po = {str(d.path): d for d in prep.file_reference_docs}

        def _merged_resolver_po(path: str) -> ReferenceDocument:
            _n = path.replace("//", "/")
            if _n in _doc_map_po:
                return _doc_map_po[_n]
            return _original_po(path)

        api_resolver = _merged_resolver_po

    # Build runtime overrides: map pipeline inputs → legacy sections
        _section_map_po: dict[str, list[str]] = {
            "proposal_instructions_and_format": [],
            "guidelines": [],
            "client_profiles": [],
            "product_catalogs": [],
            "market_outlook": [],
            "suggested_products_and_rationale": [],
        }
        _section_purposes_po: dict[str, str] = {}
        for inp in pipeline_engine.inputs:
            pid = inp.id
            if pid in ("proposal_instructions", "section_guides"):
                _section_map_po["proposal_instructions_and_format"].append(f"api://resolved/{pid}")
            elif pid in ("general_guidelines", "financial_needs_guidelines"):
                _section_map_po["guidelines"].append(f"api://resolved/{pid}")
            elif pid == "market_outlook":
                if prep.resolved_inputs.get("market_outlook"):
                    _section_map_po["market_outlook"].append(f"api://resolved/{pid}")
            elif pid == "suggested_products_and_rationale":
                if prep.resolved_inputs.get("suggested_products_and_rationale"):
                    _section_map_po["suggested_products_and_rationale"].append(f"api://resolved/{pid}")
            elif pid == "client_profile":
                _section_map_po["client_profiles"].append(API_CLIENT_PROFILE)
                if inp.description:
                    _section_purposes_po["client_profiles"] = inp.description
            elif pid == "product_catalog":
                _section_map_po["product_catalogs"].append(API_PRODUCT_CATALOG)
                if inp.description:
                    _section_purposes_po["product_catalogs"] = inp.description

        overrides = {k: v for k, v in _section_map_po.items() if v}
        LOGGER.info(
            "Pipeline resolved: %d pre-resolved files, %d API inputs. "
            "Runtime override sections: %s",
            len(prep.file_reference_docs), len(prep.api_input_ids),
            list(overrides.keys()),
        )

    fit_result = run_crew_planbot(
        app_config=app_config,
        config_path=str(_CONFIG_PATH),
        proposal_name="product_opportunity_proposal",
        runtime_reference_overrides=overrides,
        runtime_section_purposes=_section_purposes_po,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
