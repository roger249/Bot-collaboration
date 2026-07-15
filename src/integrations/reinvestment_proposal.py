"""
Reinvestment Proposal API — Full pipeline from API data to LLM-generated proposal.

Implements the contract defined in:
    docs/prod_spec/reinvestment_proposal_api.md

All client and product data are retrieved through the integration APIs.
The endpoint composes reference files, invokes CrewAI, and returns output paths.
"""

from __future__ import annotations

import csv
import json
import logging
from io import StringIO
from pathlib import Path
from typing import Any

from src.integrations.client_api import search_by_id
from src.integrations.product_tool import (
    search_by_product_id,
    search_reinvestment_candidates,
)
from src.planbot.crew_workflow import run_crew_planbot
from src.shared.config_loader import load_config

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_reinvestment_proposal(
    reinvestment_targets: list[dict[str, str]],
    max_per_product_type: int = 2,
    top_n_per_client: int = 10,
    risk_rating_hard_filter: bool = True,
    response_mode: str = "path",
    include_llm_input: bool = False,
    include_market_outlook: bool = True,
    include_candidate_explanations: bool = True,
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
    include_candidate_explanations : bool
        Whether to attach scoring and shortlist rationale.
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

    for target in reinvestment_targets:
        client_id = target.get("client_id")
        source_product_id = target.get("source_product_id")

        if not client_id or not source_product_id:
            LOGGER.warning(
                "Skipping target with missing client_id or source_product_id: %s",
                target,
            )
            continue

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
            include_candidate_explanations=include_candidate_explanations,
            include_debug_scores=include_debug_scores,
        )
        results.append(result)

    return {"status": "success", "results_by_client": results}


# ---------------------------------------------------------------------------
# Per-target processing — builds temp files → calls CrewAI → returns result
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
    include_candidate_explanations: bool,
    include_debug_scores: bool,
) -> dict:
    """Fetch data, build reference files, invoke CrewAI, return result object."""

    item: dict[str, Any] = {
        "client_id": client_id,
        "source_product_id": source_product_id,
    }

    # 1 ─ Fetch client profile and holdings ──────────────────────────────
    client_profile = search_by_id(client_id)
    if client_profile is None:
        LOGGER.warning("Client not found: %s", client_id)
        item["candidate_products"] = []
        item["output_path"] = ""
        return item

    # 2 ─ Fetch source product ───────────────────────────────────────────
    source_product = search_by_product_id(source_product_id)
    if source_product is None:
        LOGGER.warning("Source product not found: %s", source_product_id)
        item["candidate_products"] = []
        item["output_path"] = ""
        return item

    # 3 ─ Fetch reinvestment candidates ──────────────────────────────────
    cand_result = search_reinvestment_candidates(
        client_ids=[client_id],
        source_product_id=source_product_id,
        max_per_product_type=max_per_product_type,
        top_n_per_client=top_n_per_client,
        risk_rating_hard_filter=risk_rating_hard_filter,
    )
    candidates_raw = cand_result.get("results_by_client", {}).get(client_id, [])

    candidate_products: list[dict] = []
    for c in candidates_raw:
        pid = c.get("product_id", "")
        prod = search_by_product_id(pid) or {}
        candidate_products.append({
            "product_id": pid,
            "name": prod.get("name", ""),
            "product_type": prod.get("product_type", ""),
            "risk_rating": prod.get("risk_rating"),
            "expected_return": prod.get("expected_return"),
            "similarity_score": c.get("similarity_score"),
        })

    item["candidate_products"] = candidate_products

    # 4 ─ Build reference files from API data ────────────────────────────
    profile_md_abs, holdings_csv_abs = _build_client_reference_files(
        client_id, client_profile, source_product, source_product_id
    )
    catalog_md_abs, catalog_csv_abs = _build_product_catalog_files(
        client_id, source_product, candidate_products
    )

    # 5 ─ Invoke CrewAI with overrides pointing to generated files ───────
    try:
        crew_result = run_crew_planbot(
            app_config=app_config,
            config_path=str(_CONFIG_PATH),
            proposal_name="reinvestment_proposal",
            runtime_reference_overrides={
                "client_profiles": [profile_md_abs, holdings_csv_abs],
                "product_catalogs": [catalog_md_abs, catalog_csv_abs],
            },
        )
        output_path = str(crew_result.output_path)
        markdown_output = crew_result.output_path.read_text()
    finally:
        # Clean up temp reference files
        _cleanup_temp_files(profile_md_abs, holdings_csv_abs, catalog_md_abs, catalog_csv_abs)

    if response_mode in ("path", "both"):
        item["output_path"] = output_path

    if response_mode in ("markdown", "both"):
        item["markdown_output"] = markdown_output

    # 6 ─ llm_input (optional) ──────────────────────────────────────────
    if include_llm_input:
        item["llm_input"] = _build_llm_input(
            client_profile=client_profile,
            source_product=source_product,
            candidate_products=candidate_products,
            include_market_outlook=include_market_outlook,
            include_candidate_explanations=include_candidate_explanations,
        )

    # 7 ─ Debug scores (optional) ───────────────────────────────────────
    if include_debug_scores:
        item["debug_scores"] = _build_debug_scores(
            client_profile=client_profile,
            candidate_products=candidate_products,
        )

    return item


# ---------------------------------------------------------------------------
# Reference file builder
# ---------------------------------------------------------------------------

_TEMP_DIR: Path | None = None  # kept alive for the lifetime of one request
_RUNS_DIR = _ROOT_DIR / "runs" / "reinvestment_proposal" / "_generated"


def _build_client_reference_files(
    client_id: str,
    client_profile: dict,
    source_product: dict,
    source_product_id: str,
) -> tuple[str, str]:
    """Create profile markdown + holdings CSV under runs/_generated/.

    Returns paths relative to project root (required by CrewAI reference loader).
    """
    root = _RUNS_DIR / client_id
    root.mkdir(parents=True, exist_ok=True)

    # ── Profile markdown ───────────────────────────────────────────────
    risk = client_profile.get("risk_rating", "N/A")
    name = client_profile.get("name", client_id)
    age = client_profile.get("age", "N/A")
    occupation = client_profile.get("occupation", "N/A")
    aum = client_profile.get("aum")
    aum_str = f"- AUM: ${aum:,.0f}" if aum else ""

    profile_lines = [
        "# Client Profile",
        "",
        f"- Name: {name}",
        f"- Age: {age}",
        f"- Occupation: {occupation}",
        f"- Risk tolerance: {risk}",
    ]
    if aum_str:
        profile_lines.append(aum_str)
    profile_lines += [
        "",
        "# Wallet inflow Event",
        "",
        "The following product is maturing:",
        f"- Product ID: {source_product_id}",
        f"- Product Name: {source_product.get('name', source_product_id)}",
    ]
    profile_md = root / f"{client_id}_profile.md"
    profile_md.write_text("\n".join(profile_lines) + "\n")

    # ── Holdings CSV ───────────────────────────────────────────────────
    holdings = client_profile.get("holdings", [])
    csv_buf = StringIO()
    writer = csv.DictWriter(
        csv_buf,
        fieldnames=[
            "client_id", "holding_id", "product_id",
            "instrument_name", "market_value", "asset_class",
        ],
    )
    writer.writeheader()
    for h in holdings:
        writer.writerow({
            "client_id": client_id,
            "holding_id": h.get("holding_id", ""),
            "product_id": h.get("product_id", ""),
            "instrument_name": h.get("instrument_name", ""),
            "market_value": h.get("market_value", 0),
            "asset_class": h.get("asset_class", ""),
        })
    holdings_csv = root / f"{client_id}_holdings.csv"
    holdings_csv.write_text(csv_buf.getvalue())

    # Return paths relative to project root (CrewAI glob requires relative)
    return (
        str(profile_md.resolve().relative_to(_ROOT_DIR)),
        str(holdings_csv.resolve().relative_to(_ROOT_DIR)),
    )


def _cleanup_temp_files(*paths: str) -> None:
    """Remove generated reference files after proposal generation."""
    for p in paths:
        try:
            (_ROOT_DIR / p).unlink(missing_ok=True)
        except OSError:
            pass


def _build_product_catalog_files(
    client_id: str,
    source_product: dict,
    candidate_products: list[dict],
) -> tuple[str, str]:
    """Generate API-backed product catalog Markdown + CSV in the _generated dir.

    Returns paths relative to project root.
    """
    root = _RUNS_DIR / client_id
    root.mkdir(parents=True, exist_ok=True)

    # ── Catalog markdown ───────────────────────────────────────────────
    lines = [
        "# Product Catalog (API)",
        "",
        "The following products are the only investable candidates for this reinvestment proposal.",
        "Do not recommend any product not listed below.",
        "",
        "## Source (Maturing) Product",
        "",
        f"- Product ID: {source_product.get('product_id', '')}",
        f"- Name: {source_product.get('name', '')}",
        f"- Product Type: {source_product.get('product_type', '')}",
        f"- Risk Rating: {source_product.get('risk_rating', '')}",
        f"- Expected Return: {source_product.get('expected_return', '')}%",
        "",
        "## Candidate Products",
        "",
    ]
    for i, cp in enumerate(candidate_products, 1):
        lines += [
            f"### {i}. {cp.get('name', cp.get('product_id', ''))}",
            "",
            f"- Product ID: {cp.get('product_id', '')}",
            f"- Product Type: {cp.get('product_type', '')}",
            f"- Risk Rating: {cp.get('risk_rating', '')}",
            f"- Expected Return: {cp.get('expected_return', '')}%",
            f"- Similarity Score: {cp.get('similarity_score', '')}",
            "",
        ]

    catalog_md = root / f"{client_id}_catalog.md"
    catalog_md.write_text("\n".join(lines) + "\n")

    # ── Catalog CSV ────────────────────────────────────────────────────
    csv_buf = StringIO()
    writer = csv.DictWriter(
        csv_buf,
        fieldnames=[
            "product_id", "name", "product_type",
            "risk_rating", "expected_return", "similarity_score",
        ],
    )
    writer.writeheader()
    for cp in candidate_products:
        writer.writerow({
            "product_id": cp.get("product_id", ""),
            "name": cp.get("name", ""),
            "product_type": cp.get("product_type", ""),
            "risk_rating": cp.get("risk_rating", ""),
            "expected_return": cp.get("expected_return", ""),
            "similarity_score": cp.get("similarity_score", ""),
        })

    catalog_csv = root / f"{client_id}_catalog.csv"
    catalog_csv.write_text(csv_buf.getvalue())

    return (
        str(catalog_md.resolve().relative_to(_ROOT_DIR)),
        str(catalog_csv.resolve().relative_to(_ROOT_DIR)),
    )


# ---------------------------------------------------------------------------
# llm_input builder
# ---------------------------------------------------------------------------


def _build_llm_input(
    client_profile: dict,
    source_product: dict,
    candidate_products: list[dict],
    include_market_outlook: bool,
    include_candidate_explanations: bool,
) -> dict:
    """Assemble the structured ``llm_input`` payload for the LLM."""
    payload: dict[str, Any] = {
        "client_profile": {
            "client_id": client_profile.get("client_id"),
            "name": client_profile.get("name"),
            "risk_rating": client_profile.get("risk_rating"),
            "age": client_profile.get("age"),
            "aum": client_profile.get("aum"),
            "cash_score": client_profile.get("cash_score"),
            "concentration_score": client_profile.get("concentration_score"),
            "investor_readiness_score": client_profile.get("investor_readiness_score"),
        },
        "holdings": _summarize_holdings(client_profile.get("holdings", [])),
        "source_product": {
            "product_id": source_product.get("product_id"),
            "name": source_product.get("name"),
            "product_type": source_product.get("product_type"),
            "risk_rating": source_product.get("risk_rating"),
            "expected_return": source_product.get("expected_return"),
            "region": source_product.get("region"),
        },
        "candidate_products": candidate_products,
        "output_instructions": {
            "sections": [
                "executive summary",
                "recommended product",
                "risk characteristics",
                "detailed justification",
                "portfolio tables",
                "scenario analysis",
                "risk disclosures",
            ],
            "tone": "professional advisory",
            "format": "markdown",
        },
    }

    if include_market_outlook:
        payload["market_outlook"] = {"note": "market outlook not yet configured"}

    if include_candidate_explanations:
        payload["candidate_rationale"] = "Candidate rationales not yet assembled."

    return payload


def _summarize_holdings(holdings: list[dict]) -> list[dict]:
    """Create a minimal holdings summary for the llm_input."""
    return [
        {
            "product_id": h.get("product_id"),
            "instrument_name": h.get("instrument_name"),
            "asset_class": h.get("asset_class"),
            "market_value": h.get("market_value"),
            "yield_pct": h.get("yield_pct"),
            "risk_bucket": h.get("risk_bucket"),
        }
        for h in holdings
    ]


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
