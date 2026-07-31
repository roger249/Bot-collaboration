"""
Product-Investor Matcher — Full pipeline from client/product data to ranked proposals.

Implements the end-to-end flow defined in:
    docs/prod_spec/product_investor_matcher.md

Sprint 1: Scorecards → LLM ranking → client_product_fit_analysis.
All data flows in-memory — no temp files.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from src.integrations.client_api import (
    search,
    search_by_id,
    search_by_investor_readiness_score,
)
from src.integrations.product_tool import (
    search_by_product_id,
    search_product_by_fitness_score,
)
from src.planbot.crew_workflow import run_crew_planbot
from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_HOLDINGS,
    API_PRODUCT_CATALOG,
    ReferenceDocument,
)
from src.planbot.workflow import build_matcher_llm_payload
from src.shared.config_loader import load_config

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def match_products_to_investors(
    product_ids: list[str] | None = None,
    product_source: str = "default_yaml",
    client_selection: dict | None = None,
    top_n: int = 2,
    market_outlook: str | None = None,
) -> dict:
    """Run the full product-investor matching pipeline.

    Parameters
    ----------
    product_ids : list[str] | None
        Product IDs to consider.  Interpretation depends on *product_source*:
        - ``request_payload`` → literal product IDs only.
        - ``default_yaml`` → may contain group names from ``product_groups``
          in ``config_planbot.yaml``; those are expanded to their member IDs.
        If None and *product_source* is ``default_yaml``, uses the full
        product catalog.
    product_source : str
        ``"default_yaml"`` or ``"request_payload"``.  Default ``"default_yaml"``.
    client_selection : dict | None
        Criteria passed to the client API ``search`` endpoint.
    top_n : int
        Number of top-ranked opportunities to return in the final output.
    market_outlook : str | None
        Market context. When absent, falls back to the market_outlook files
        globbed from config.

    Returns
    -------
    dict
        Response with ``run_id``, ``summary``,
        ``product_investor_matching_markdown``, ``final_proposals``,
        ``warnings``, ``errors``.
    """
    run_id = _generate_run_id()
    warnings: list[str] = []
    errors: list[dict] = []

    LOGGER.info(
        "=== Matcher request %s: product_ids=%s source=%s top_n=%d ===",
        run_id, product_ids, product_source, top_n,
    )

    # ── 1. Load matcher config ──────────────────────────────────────────
    planbot_config = _load_planbot_config()
    matcher_cfg = planbot_config.get("product_investor_matching", {}).get("matcher", {})
    readiness_pool_size = matcher_cfg.get("default_number_of_candidates_from_investor_readiness", 15)
    app_config = load_config(str(_ROOT_DIR / "config" / "config.yaml"))

    # ── 2. Fetch clients ────────────────────────────────────────────────
    client_criteria = client_selection or {}
    try:
        all_clients = search(**client_criteria)
    except Exception as exc:
        LOGGER.error("Client search failed: %s", exc)
        return {
            "run_id": run_id,
            "summary": {"status": "error"},
            "product_investor_matching_markdown": "",
            "final_proposals": [],
            "warnings": [],
            "errors": [{"code": "CLIENT_API_ERROR", "message": str(exc)}],
        }

    if not all_clients:
        return {
            "run_id": run_id,
            "summary": {"status": "warning", "total_clients": 0},
            "product_investor_matching_markdown": "",
            "final_proposals": [],
            "warnings": ["NO_CLIENTS_RETRIEVED"],
            "errors": [],
        }

    LOGGER.info("Retrieved %d clients after client_selection filter", len(all_clients))

    LOGGER.info("Scorecard request: search_by_investor_readiness_score(top_n=%d)", readiness_pool_size)

    # ── 3. Investor readiness → top-K ───────────────────────────────────
    try:
        readiness_scores = search_by_investor_readiness_score(top_n=readiness_pool_size)
    except Exception as exc:
        LOGGER.error("Investor readiness score failed: %s", exc)
        return {
            "run_id": run_id,
            "summary": {"status": "error"},
            "product_investor_matching_markdown": "",
            "final_proposals": [],
            "warnings": [],
            "errors": [{"code": "READINESS_SCORE_ERROR", "message": str(exc)}],
        }

    # Build readiness map: client_id → rank
    readiness_map: dict[str, dict] = {r["client_id"]: r for r in readiness_scores}
    # Filter to clients that exist in both readiness and search results
    search_client_ids = {c.get("client_id") for c in all_clients if c.get("client_id")}
    eligible_client_ids = [
        r["client_id"]
        for r in readiness_scores
        if r["client_id"] in search_client_ids
    ]

    LOGGER.info(
        "Readiness scorecard: %d clients scored, %d eligible (top-%d)",
        len(readiness_scores), len(eligible_client_ids), readiness_pool_size,
    )
    LOGGER.debug(
        "Readiness scorecard API response (first 5):\n%s",
        json.dumps(readiness_scores[:5], indent=2, default=str),
    )

    if not eligible_client_ids:
        return {
            "run_id": run_id,
            "summary": {"status": "warning", "total_clients": len(all_clients)},
            "product_investor_matching_markdown": "",
            "final_proposals": [],
            "warnings": ["NO_ELIGIBLE_CLIENTS"],
            "errors": [],
        }

    LOGGER.info(
        "Readiness filter: %d → top-%d clients passed",
        len(all_clients), len(eligible_client_ids),
    )

    # ── 4. Determine product universe ───────────────────────────────────
    if product_ids:
        if product_source == "request_payload":
            # Literal IDs only — never expand as group names
            product_universe = list(dict.fromkeys(product_ids))  # dedup, order preserved
        else:
            product_universe = _resolve_product_ids(product_ids, planbot_config)

        # Fitness scoring only runs on the requested products, not on
        # existing holdings.  Snapshot before enrichment.
        fitness_product_ids = list(product_universe)

        # Enrich with products the eligible clients already hold so the
        # LLM sees existing holdings in the product catalog for comparison.
        n_before = len(product_universe)
        holdings_pids = _get_holdings_product_ids(eligible_client_ids)
        existing = set(product_universe)
        for pid in holdings_pids:
            if pid not in existing:
                existing.add(pid)
                product_universe.append(pid)
        LOGGER.info(
            "Product universe: %d from request + %d from holdings = %d total",
            n_before, len(product_universe) - n_before, len(product_universe),
        )
    else:
        # Default: use all products from the catalog
        from src.test_data.product_catalog import get_conn as _pcat_conn
        try:
            conn = _pcat_conn(read_only=True)
            all_prod_ids = [
                r[0] for r in conn.execute(
                    "SELECT product_id FROM products ORDER BY product_id"
                ).fetchall()
            ]
            conn.close()
            product_universe = all_prod_ids
        except Exception as exc:
            LOGGER.warning("Cannot load product catalog from DB: %s", exc)
            product_universe = []
        fitness_product_ids = list(product_universe)  # full catalog = all scorable
        LOGGER.info("Using full product universe: %d products", len(product_universe))

    # ── 5. Product fitness score per client ─────────────────────────────
    LOGGER.info(
        "Scorecard request: search_product_by_fitness_score(%d clients × %d products, top_n=%d)",
        len(eligible_client_ids), len(fitness_product_ids), top_n * 3,
    )
    fitness_results: dict[str, list[dict]] = {}
    try:
        for cid in eligible_client_ids:
            fit = search_product_by_fitness_score(
                client_ids=[cid],
                product_ids=fitness_product_ids,
                top_n=top_n * 3,  # wider pool for LLM to rank
                risk_rating_hard_filter=False,  # PFS already handles risk gate
            )
            fitness_results[cid] = fit.get("results", [])
    except Exception as exc:
        LOGGER.error("Product fitness scoring failed: %s", exc)
        return {
            "run_id": run_id,
            "summary": {"status": "error"},
            "product_investor_matching_markdown": "",
            "final_proposals": [],
            "warnings": [],
            "errors": [{"code": "FITNESS_SCORE_ERROR", "message": str(exc)}],
        }

    LOGGER.info(
        "Fitness scorecard: %d clients scored against %d products",
        len(fitness_results), len(fitness_product_ids),
    )
    LOGGER.debug(
        "Fitness scorecard API response (first 3 clients, top 3 each):\n%s",
        json.dumps(
            {k: v[:3] for k, v in list(fitness_results.items())[:3]},
            indent=2, default=str,
        ),
    )

    # ── 5b. Trim LLM input to top_n clients only ──────────────────────
    # The fitness scorecard runs on the full readiness pool, but the LLM
    # only sees the top_n clients.  This keeps the LLM call fast and
    # focused — no truncation, no wasted tokens on discarded clients.
    llm_client_ids = eligible_client_ids[:top_n]
    LOGGER.info(
        "LLM input: %d clients trimmed from readiness pool of %d (top_n=%d)",
        len(llm_client_ids), len(eligible_client_ids), top_n,
    )

    # ── 6. Build in-memory API resolver ─────────────────────────────────
    api_resolver = _build_matcher_api_resolver(
        eligible_client_ids=llm_client_ids,
        product_universe=product_universe,
        readiness_map=readiness_map,
        fitness_results=fitness_results,
        market_outlook=market_outlook,
    )

    # ── 7. Run product_investor_matching via CrewAI ─────────────────────
    try:
        matching_output_path = f"runs/product_investor_matching/product_investor_matching_{run_id}.md"
        crew_result = run_crew_planbot(
            app_config=app_config,
            config_path=str(_CONFIG_PATH),
            proposal_name="product_investor_matching",
            runtime_reference_overrides={
                "client_profiles": [API_CLIENT_PROFILE, API_HOLDINGS],
                "product_catalogs": [API_PRODUCT_CATALOG],
            },
            output_file_override=matching_output_path,
            api_resolver=api_resolver,
        )
        matching_markdown = crew_result.output_path.read_text()
    except Exception as exc:
        LOGGER.error("product_investor_matching CrewAI failed: %s", exc)
        return {
            "run_id": run_id,
            "summary": {"status": "error"},
            "product_investor_matching_markdown": "",
            "final_proposals": [],
            "warnings": [],
            "errors": [{"code": "LLM_GENERATION_ERROR", "message": str(exc)}],
        }

    LOGGER.info("product_investor_matching generated successfully")

    # ── 8. Extract top-N pairs from matching output ─────────────────────
    top_pairs = _extract_top_pairs(matching_markdown, top_n)

    # ── 9. Run client_product_fit_analysis per pair ─────────────────────
    final_proposals: list[dict] = []
    for pair in top_pairs:
        cid = pair["client_id"]
        pid = pair["product_id"]
        try:
            client_data = search_by_id(cid)
            product_data = search_by_product_id(pid)

            if client_data is None or product_data is None:
                warnings.append(f"CLIENT_OR_PRODUCT_NOT_FOUND:{cid}/{pid}")
                continue

            # Build per-client resolver
            fit_resolver = _build_fit_analysis_resolver(
                client_data=client_data,
                product_data=product_data,
                matching_markdown=matching_markdown,
                market_outlook=market_outlook,
            )

            fit_output_path = (
                f"runs/client_product_fit_analysis/"
                f"client_product_fit_analysis_{cid}_{pid}_{run_id}.md"
            )
            fit_result = run_crew_planbot(
                app_config=app_config,
                config_path=str(_CONFIG_PATH),
                proposal_name="client_product_fit_analysis",
                runtime_reference_overrides={
                    "client_profiles": [API_CLIENT_PROFILE, API_HOLDINGS],
                    "product_catalogs": [API_PRODUCT_CATALOG],
                },
                output_file_override=fit_output_path,
                api_resolver=fit_resolver,
            )
            fit_markdown = fit_result.output_path.read_text()

            final_proposals.append({
                "client_id": cid,
                "product_id": pid,
                "investment_amount": pair.get("investment_amount", ""),
                "funding_source": pair.get("funding_source", ""),
                "buying_score": pair.get("buying_score", 0),
                "rationale": pair.get("rationale", ""),
                "proposal_markdown": fit_markdown,
            })

        except Exception as exc:
            LOGGER.error("fit analysis for %s/%s failed: %s", cid, pid, exc)
            warnings.append(f"FIT_ANALYSIS_FAILED:{cid}/{pid}")
            final_proposals.append({
                "client_id": cid,
                "product_id": pid,
                "investment_amount": pair.get("investment_amount", ""),
                "funding_source": pair.get("funding_source", ""),
                "buying_score": pair.get("buying_score", 0),
                "rationale": pair.get("rationale", ""),
                "error": str(exc),
            })

    # ── 10. Assemble response ───────────────────────────────────────────
    return {
        "run_id": run_id,
        "summary": {
            "status": "success",
            "total_clients_retrieved": len(all_clients),
            "clients_after_readiness": len(eligible_client_ids),
            "top_n_returned": len(final_proposals),
        },
        "product_investor_matching_markdown": matching_markdown,
        "final_proposals": final_proposals,
        "warnings": warnings,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_run_id() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")


def _get_holdings_product_ids(client_ids: list[str]) -> list[str]:
    """Return distinct product_ids from *client_ids* holdings that exist
    in the products table — so the LLM sees what clients already own."""
    if not client_ids:
        return []
    from src.test_data.product_catalog import get_conn as _pcat_conn
    conn = _pcat_conn(read_only=True)
    try:
        placeholders = ",".join("?" for _ in client_ids)
        rows = conn.execute(
            f"SELECT DISTINCT h.product_id "
            f"FROM holdings h "
            f"INNER JOIN products p ON h.product_id = p.product_id "
            f"WHERE h.client_id IN ({placeholders})",
            client_ids,
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _load_planbot_config() -> dict:
    return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _resolve_product_ids(product_ids: list[str], planbot_config: dict) -> list[str]:
    """Expand product-group names in *product_ids* to literal product IDs.

    Any entry in *product_ids* that matches a key under
    ``product_groups`` in *planbot_config* is replaced by the group's
    ``product_ids`` list.  Literal product IDs pass through unchanged.
    The result is deduplicated while preserving insertion order.
    """
    groups: dict[str, dict] = planbot_config.get("product_groups", {}) or {}
    resolved: list[str] = []
    seen: set[str] = set()
    for pid in product_ids:
        if pid in groups:
            group_ids = groups[pid].get("product_ids", [])
            LOGGER.info(
                "Expanding product group '%s' → %d products: %s",
                pid, len(group_ids), group_ids,
            )
            for gid in group_ids:
                if gid not in seen:
                    seen.add(gid)
                    resolved.append(gid)
        else:
            if pid not in seen:
                seen.add(pid)
                resolved.append(pid)
    return resolved


def _extract_top_pairs(markdown: str, top_n: int) -> list[dict]:
    """Extract client pairs from the matching markdown output.

    Handles two output formats:
    1. Table-based (current prompt): a summary table with columns
       Rank, Client ID, Suggested Product, Buying Score, Rationale,
       followed by ``## Client: PB-HK-XXXXXXX (Name)`` sections.
    2. Header-based: ``## Rank N – Client X — Buying Score: Y``
    """
    pairs: list[dict] = []

    # ── Try table-based parsing first ──────────────────────────────────
    table_row = re.compile(
        r"^\|\s*(\d+)\s*\|\s*"
        r"([A-Z]{2}-[A-Z]{2}-\d{6,7}-\d)\s*\|\s*"
        r"[^|]*\|\s*"
        r"([^|]+?)\s*\|\s*"
        r"(\d+(?:\.\d+)?)\s*\|\s*"
        r"([^|]*)",
        re.MULTILINE,
    )

    table_pairs: dict[str, dict] = {}
    for m in table_row.finditer(markdown):
        client_id = m.group(2).strip()
        product_raw = m.group(3).strip()
        buying_score = float(m.group(4).strip())
        rationale = m.group(5).strip()

        prod_id_match = re.match(r"([A-Za-z]+[-.]?[\w.-]+)", product_raw)
        product_id = prod_id_match.group(1) if prod_id_match else product_raw

        table_pairs[client_id] = {
            "client_id": client_id,
            "product_id": product_id,
            "buying_score": buying_score,
            "rationale": rationale,
            "investment_amount": "",
            "funding_source": "",
        }

    # ── Client-section enrichment (only when table data exists) ─────────
    if table_pairs:
        sections = re.split(r"\n(?=#{1,3}\s)", markdown)
        for section in sections:
            client_match = re.search(
                r"Client[:\s]+"
                r"(?P<client_id>[A-Z]{2}-[A-Z]{2}-\d{6,7}-\d)",
                section, re.IGNORECASE,
            )
            if not client_match:
                continue
            client_id = client_match.group("client_id")
            if client_id not in table_pairs:
                continue

            pair = table_pairs[client_id]
            clean = re.sub(r"\*{1,2}", "", section)

            amt_match = re.search(
                r"(?:Investment\s*)?Amount[:\s]+\$?"
                r"(?P<amount>[\d,]+(?:\.\d+)?)",
                clean, re.IGNORECASE,
            )
            if amt_match:
                pair["investment_amount"] = amt_match.group("amount")

            fund_match = re.search(
                r"(?:Funding\s*)?Source[:\s]+(?P<funding>[^\n*]+)",
                clean, re.IGNORECASE,
            )
            if fund_match:
                pair["funding_source"] = fund_match.group("funding").strip()

        pairs = sorted(table_pairs.values(), key=lambda x: x.get("buying_score", 0), reverse=True)

    # ── Fallback: header-based format ──────────────────────────────────
    if not pairs:
        sections = re.split(r"\n(?=#{1,3}\s)", markdown)
        section_pattern = re.compile(
            r"^#{1,3}\s*(?:Rank\s*\d+\s*[–\-—]+\s*)?Client\s+"
            r"(?P<client_id>[A-Z]{2}-[A-Z]{2}-\d{6,7}-\d)"
            r"(?:.*?Buying\s*Score[\s:]*(?P<buying_score>\d+(?:\.\d+)?))?",
            re.MULTILINE | re.IGNORECASE,
        )
        for section in sections:
            m = section_pattern.search(section)
            if not m:
                continue
            cid = m.group("client_id")
            bs = float(m.group("buying_score")) if m.group("buying_score") else 0
            clean = re.sub(r"\*{1,2}", "", section)
            pm = re.search(r"(?:Recommended\s*)?Product\s*ID[:\s]+(?P<p>[A-Za-z]+[-.]?[\w.-]+)", clean, re.I)
            am = re.search(r"(?:Investment\s*)?Amount[:\s]+\$?(?P<a>[\d,]+(?:\.\d+)?)", clean, re.I)
            fm = re.search(r"(?:Funding\s*)?Source[:\s]+(?P<f>[^\n*]+)", clean, re.I)
            rm = re.search(r"Rationale[:\s]+(?P<r>[^\n]+)", clean, re.I)
            pairs.append({
                "client_id": cid,
                "product_id": pm.group("p") if pm else "",
                "buying_score": bs,
                "investment_amount": am.group("a") if am else "",
                "funding_source": fm.group("f").strip() if fm else "",
                "rationale": rm.group("r").strip() if rm else "",
            })

    pairs.sort(key=lambda x: x.get("buying_score", 0), reverse=True)
    return pairs[:top_n]


# ---------------------------------------------------------------------------
# In-memory API resolver for product_investor_matching
# ---------------------------------------------------------------------------


def _build_matcher_api_resolver(
    eligible_client_ids: list[str],
    product_universe: list[str],
    readiness_map: dict[str, dict],
    fitness_results: dict[str, list[dict]],
    market_outlook: str | None,
) -> Callable[[str], ReferenceDocument]:
    """Build an API resolver that returns ReferenceDocuments from pre-fetched data.

    Serves: ``client_profile``, ``holdings``, ``product_catalog`` api:// paths.
    """
    # Pre-fetch client data
    clients_data: dict[str, dict] = {}
    for cid in eligible_client_ids:
        cp = search_by_id(cid)
        if cp:
            clients_data[cid] = cp

    # Pre-fetch product data
    products_data: dict[str, dict] = {}
    for pid in product_universe:
        prod = search_by_product_id(pid)
        if prod:
            products_data[pid] = prod

    def _format_client_profile(cid: str) -> str:
        cp = clients_data.get(cid, {})
        readiness = readiness_map.get(cid, {})
        lines = [
            "# Client Profile",
            "",
            f"- Client ID: {cp.get('client_id', cid)}",
            f"- Name: {cp.get('name', 'N/A')}",
            f"- Age: {cp.get('age', 'N/A')}",
            f"- Occupation: {cp.get('occupation', 'N/A')}",
            f"- Risk Rating (1-5): {cp.get('risk_rating', 'N/A')}",
            f"- Region: {cp.get('region', 'N/A')}",
            f"- AUM: ${cp.get('aum', 0):,.0f}" if cp.get('aum') else "- AUM: N/A",
            f"- Cash %: {cp.get('cash_pct', 'N/A')}",
            f"- Investment Objective: {cp.get('investment_objective', 'N/A')}",
            f"- Liquidity Need: {cp.get('liquidity_need', 'N/A')}",
            "",
            "## Investor Readiness Score",
            f"Rank: {eligible_client_ids.index(cid) + 1 if cid in eligible_client_ids else 'N/A'}/{len(eligible_client_ids)}",
            f"Total Score: {readiness.get('total_score', 'N/A')}",
            f"  - Cash Drag: {readiness.get('s_cash', 'N/A')}",
            f"  - Concentration: {readiness.get('s_concentration', 'N/A')}",
            f"  - Active Management: {readiness.get('s_active', 'N/A')}",
            f"  - Life Stage: {readiness.get('s_lifestage', 'N/A')}",
        ]
        qp = cp.get("qualitative_profile")
        if qp:
            lines += ["", "## RM Notes", "", qp]
        return "\n".join(lines)

    def _format_holdings(cid: str) -> str:
        cp = clients_data.get(cid, {})
        holdings = cp.get("holdings", [])
        if not holdings:
            return "# Holdings\n\n(No holdings data available)"
        lines = ["# Holdings", ""]
        lines.append("| # | Product ID | Name | Asset Class | Market Value | Yield % | Risk |")
        lines.append("|---|---|---|---|---|---|---|")
        for i, h in enumerate(holdings, 1):
            lines.append(
                f"| {i} | {h.get('product_id', '')} | {h.get('instrument_name', '')} | "
                f"{h.get('asset_class', '')} | ${h.get('market_value', 0):,.0f} | "
                f"{h.get('yield_pct', '')} | {h.get('risk_bucket', '')} |"
            )
        return "\n".join(lines)

    def _format_product_catalog() -> str:
        lines = ["# Product Catalog", ""]
        for pid in product_universe:
            p = products_data.get(pid, {})
            lines.append(f"## {pid} — {p.get('name', 'N/A')}")
            lines.append(f"- Type: {p.get('product_type', 'N/A')}")
            lines.append(f"- Risk Rating: {p.get('risk_rating', 'N/A')}")
            lines.append(f"- Expected Return: {p.get('expected_return', 'N/A')}%")
            lines.append(f"- Region: {p.get('region', 'N/A')}")
            lines.append(f"- Sector: {p.get('sector', 'N/A')}")
            note = p.get("investment_note")
            if note:
                lines.append(f"- Investment Note: {note}")
            lines.append("")

        # ── Append fitness score summary per client ─────────────────
        lines.append("## Product Fitness Scores (per client)")
        lines.append("")
        for cid in eligible_client_ids:
            fit = fitness_results.get(cid, [])
            if not fit:
                continue
            cp = clients_data.get(cid, {})
            lines.append(f"### {cid} — {cp.get('name', 'N/A')} (RR={cp.get('risk_rating', 'N/A')})")
            lines.append("")
            lines.append("| Rank | Product ID | Name | Fitness Score | Risk Match | Concentration | Experience | Better Product |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for i, f in enumerate(fit[:10], 1):
                comp = f.get("component_scores", {})
                p_name = f.get("product_name", "")
                lines.append(
                    f"| {i} | {f.get('product_id', '')} | {p_name[:40]} | "
                    f"{f.get('fitness_score', ''):.2f} | "
                    f"{comp.get('risk_rating_match_score', ''):.1f} | "
                    f"{comp.get('concentration_score', ''):.1f} | "
                    f"{comp.get('has_similar_investment_experience_score', ''):.1f} | "
                    f"{comp.get('better_product_score', ''):.1f} |"
                )
            lines.append("")
        return "\n".join(lines)

    # ── Resolver ────────────────────────────────────────────────────────
    def resolve(api_path: str) -> ReferenceDocument:
        if api_path == API_CLIENT_PROFILE:
            content_parts = [_format_client_profile(cid) for cid in eligible_client_ids]
            content = "\n\n---\n\n".join(content_parts)
            return ReferenceDocument(
                path=Path("api://client_profile"),
                content=content,
                source_type="markdown",
            )
        elif api_path == API_HOLDINGS:
            content_parts = [_format_holdings(cid) for cid in eligible_client_ids]
            content = "\n\n---\n\n".join(content_parts)
            return ReferenceDocument(
                path=Path("api://holdings"),
                content=content,
                source_type="markdown",
            )
        elif api_path == API_PRODUCT_CATALOG:
            return ReferenceDocument(
                path=Path("api://product_catalog"),
                content=_format_product_catalog(),
                source_type="markdown",
            )
        else:
            return ReferenceDocument(
                path=Path(api_path),
                content="",
                source_type="markdown",
            )

    return resolve


# ---------------------------------------------------------------------------
# In-memory API resolver for client_product_fit_analysis (per-pair)
# ---------------------------------------------------------------------------


def _build_fit_analysis_resolver(
    client_data: dict,
    product_data: dict,
    matching_markdown: str,
    market_outlook: str | None,
) -> Callable[[str], ReferenceDocument]:
    """Build a resolver for a single client×product pair."""

    def _format_single_client_profile() -> str:
        cp = client_data
        lines = [
            "# Client Profile",
            "",
            f"- Client ID: {cp.get('client_id', 'N/A')}",
            f"- Name: {cp.get('name', 'N/A')}",
            f"- Age: {cp.get('age', 'N/A')}",
            f"- Occupation: {cp.get('occupation', 'N/A')}",
            f"- Risk Rating (1-5): {cp.get('risk_rating', 'N/A')}",
            f"- Region: {cp.get('region', 'N/A')}",
            f"- AUM: ${cp.get('aum', 0):,.0f}" if cp.get('aum') else "- AUM: N/A",
            f"- Investment Objective: {cp.get('investment_objective', 'N/A')}",
            f"- Liquidity Need: {cp.get('liquidity_need', 'N/A')}",
        ]
        qp = cp.get("qualitative_profile")
        if qp:
            lines += ["", "## RM Notes", "", qp]
        return "\n".join(lines)

    def _format_single_product() -> str:
        p = product_data
        lines = [
            "# Recommended Product",
            "",
            f"- Product ID: {p.get('product_id', 'N/A')}",
            f"- Name: {p.get('name', 'N/A')}",
            f"- Type: {p.get('product_type', 'N/A')}",
            f"- Risk Rating: {p.get('risk_rating', 'N/A')}",
            f"- Expected Return: {p.get('expected_return', 'N/A')}%",
        ]
        note = p.get("investment_note")
        if note:
            lines += ["", "## Investment Note", "", note]
        return "\n".join(lines)

    def resolve(api_path: str) -> ReferenceDocument:
        if api_path == API_CLIENT_PROFILE:
            return ReferenceDocument(
                path=Path("api://client_profile"),
                content=_format_single_client_profile(),
                source_type="markdown",
            )
        elif api_path == API_PRODUCT_CATALOG:
            return ReferenceDocument(
                path=Path("api://product_catalog"),
                content=_format_single_product(),
                source_type="markdown",
            )
        else:
            return ReferenceDocument(
                path=Path(api_path),
                content="",
                source_type="markdown",
            )

    return resolve
