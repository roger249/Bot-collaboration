"""
Product-Investor Matcher — Full pipeline from client/product data to ranked proposals.

Implements the end-to-end flow defined in:
    docs/prod_spec/product_investor_matcher.md

Sprint 1: Scorecards → LLM ranking → product_opportunity_proposal.
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
from src.shared.market_outlook_utils import (
    API_MARKET_OUTLOOK,
    format_market_outlook_section,
)
from src.shared.resolver_formatters import (
    build_api_resolver,
    format_client_profile_markdown,
    format_holdings_table,
    format_product_multi,
    format_product_single_recommended,
)

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def product_investor_matcher(
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
    readiness_pool_size = matcher_cfg.get("readiness_pool_size", 15)
    llm_client_pool_size = matcher_cfg.get("llm_client_pool_size", 5)
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
    fitness_top_n = max(3, len(fitness_product_ids) // 2) or 1
    LOGGER.info(
        "Scorecard request: search_product_by_fitness_score(%d clients × %d products, top_n=%d)",
        len(eligible_client_ids), len(fitness_product_ids), fitness_top_n,
    )
    fitness_results: dict[str, list[dict]] = {}
    try:
        for cid in eligible_client_ids:
            fit = search_product_by_fitness_score(
                client_ids=[cid],
                product_ids=fitness_product_ids,
                top_n=fitness_top_n,
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

    # ── 5b. Trim LLM input to llm_client_pool_size clients ──────────
    # The fitness scorecard runs on the full readiness pool, but the LLM
    # only sees the llm_client_pool_size clients.  This keeps the LLM call
    # fast and focused — no truncation, no wasted tokens on discarded clients.
    llm_client_ids = eligible_client_ids[:llm_client_pool_size]
    LOGGER.info(
        "LLM input: %d clients trimmed from readiness pool of %d (llm_client_pool_size=%d)",
        len(llm_client_ids), len(eligible_client_ids), llm_client_pool_size,
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
        reference_overrides: dict[str, list[str]] = {
            "client_profiles": [API_CLIENT_PROFILE, API_HOLDINGS],
            "product_catalogs": [API_PRODUCT_CATALOG],
        }
        if market_outlook is not None:
            reference_overrides["market_outlook"] = [API_MARKET_OUTLOOK]

        crew_result = run_crew_planbot(
            app_config=app_config,
            config_path=str(_CONFIG_PATH),
            proposal_name="product_investor_matching",
            runtime_reference_overrides=reference_overrides,
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

    # ── 8a. Write JSON sidecar for downstream consumers ────────────────
    sidecar_path = Path(str(Path(matching_output_path).with_suffix("")) + "_pairs.json")
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(json.dumps(top_pairs, indent=2, ensure_ascii=False))
    LOGGER.info("JSON sidecar written: %s (%d pairs)", sidecar_path, len(top_pairs))

    # ── 9. Assemble response (proposal generation moved to product_opportunity_proposal.py) ──
    final_proposals = [
        {
            "client_id": p["client_id"],
            "product_id": p["product_id"],
            "investment_amount": p.get("investment_amount", ""),
            "funding_source": p.get("funding_source", ""),
            "buying_score": p.get("buying_score", 0),
            "rationale": p.get("rationale", ""),
            "alternative_product_ids": p.get("alternative_product_ids", []),
        }
        for p in top_pairs
    ]

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
    """Extract client pairs and alternatives from the matching markdown output.

    Parses the 8-column summary table:
    | Client ID (Name) | Buying Score | Suggested Product & Position |
    Funding Source | Fitness Score | ER Suggested | ER Source | Key Rationale |

    Also extracts alternative products from per-client
    ``#### Alternative suggestion`` bullet sections.
    """
    cfg = _load_matcher_extract_config()
    client_id_re = re.compile(cfg.get("client_id_re", r"[A-Z]{2}-[A-Z]{2}-\d{6,7}-\d"))
    product_id_re = re.compile(cfg.get("product_id_re", r"[A-Za-z]+[-.]?[\w.-]+"))
    amount_re = re.compile(cfg.get("amount_re", r"USD\s+\$?([\d,]+(?:\.\d+)?)"))
    alt_product_re = re.compile(
        cfg.get("alternative_product_re", r"-\s+([A-Za-z]+[-.]?[\w.-]+)\s"),
    )

    # ── 1. Parse the 8-column summary table ────────────────────────────
    pairs: list[dict] = []
    in_table = False

    for line in markdown.split("\n"):
        stripped = line.strip()
        # Detect table start: 8-column header
        if "| Client ID" in stripped and "| Buying Score" in stripped:
            in_table = True
            continue
        # Skip separator row
        if in_table and re.match(r"^\|[-:\s|]+\|$", stripped):
            continue
        # End of table
        if in_table and not stripped.startswith("|"):
            in_table = False
            continue

        if in_table and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) < 8:
                continue

            cid_match = client_id_re.search(cells[0])
            if not cid_match:
                continue
            client_id = cid_match.group(0)

            try:
                buying_score = float(cells[1].strip())
            except (ValueError, TypeError):
                buying_score = 0.0

            # Extract product_id from col 3 (first token)
            pid_match = product_id_re.search(cells[2])
            product_id = pid_match.group(0) if pid_match else ""

            # Extract investment amount from col 3
            amt_match = amount_re.search(cells[2])
            investment_amount = amt_match.group(1) if amt_match else ""

            funding_source = cells[3]
            rationale = cells[7] if len(cells) > 7 else ""

            pairs.append({
                "client_id": client_id,
                "product_id": product_id,
                "buying_score": buying_score,
                "rationale": rationale.strip(),
                "investment_amount": investment_amount,
                "funding_source": funding_source,
                "alternative_product_ids": [],
            })

    if not pairs:
        LOGGER.warning("_extract_top_pairs: no table rows parsed from markdown")
        return []

    # ── 2. Extract alternatives from per-client sections ────────────────
    # Split on ##/### headers; only process sections starting with a client ID
    client_sections = re.split(r"\n(?=#{2,3}\s)", markdown)
    for section in client_sections:
        cid_match = client_id_re.search(section)
        if not cid_match:
            continue
        section_cid = cid_match.group(0)

        # Find the pair for this section
        pair = next((p for p in pairs if p["client_id"] == section_cid), None)
        if not pair:
            continue

        # Find #### Alternative suggestion block — stop at next ##/### header or end
        alt_block_match = re.search(
            r"####\s+Alternative\s+suggestion\s*\n(.*?)(?=\n(?:#{2,3})\s|\Z)",
            section, re.DOTALL | re.IGNORECASE,
        )
        if not alt_block_match:
            continue

        alt_ids = alt_product_re.findall(alt_block_match.group(1))
        pair["alternative_product_ids"] = list(dict.fromkeys(alt_ids))  # dedupe, preserve order

    pairs.sort(key=lambda x: x.get("buying_score", 0), reverse=True)
    return pairs[:top_n]


def _load_matcher_extract_config() -> dict[str, str]:
    """Load extract_patterns from config_planbot.yaml."""
    planbot_config = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    matcher_cfg = planbot_config.get("product_investor_matching", {}).get("matcher", {})
    return matcher_cfg.get("extract_patterns", {})


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
        base = format_client_profile_markdown(cp)
        extra = [
            "",
            f"- Cash %: {cp.get('cash_pct', 'N/A')}",
            "",
            "## Investor Readiness Score",
            f"Rank: {eligible_client_ids.index(cid) + 1 if cid in eligible_client_ids else 'N/A'}/{len(eligible_client_ids)}",
            f"Total Score: {readiness.get('total_score', 'N/A')}",
            f"  - Cash Drag: {readiness.get('s_cash', 'N/A')}",
            f"  - Concentration: {readiness.get('s_concentration', 'N/A')}",
            f"  - Active Management: {readiness.get('s_active', 'N/A')}",
            f"  - Life Stage: {readiness.get('s_lifestage', 'N/A')}",
        ]
        return base + "\n".join(extra)

    def _format_product_catalog() -> str:
        products = [products_data[pid] for pid in product_universe if pid in products_data]
        content = format_product_multi(products)
        # Append fitness score summary per client
        lines = [content, "", "## Product Fitness Scores (per client)", ""]
        for cid in eligible_client_ids:
            fit = fitness_results.get(cid, [])
            if not fit:
                continue
            cp = clients_data.get(cid, {})
            lines.append(f"### {cid} — {cp.get('name', 'N/A')} (RR={cp.get('risk_rating', 'N/A')})")
            lines.append("")
            lines.append("| Rank | Product ID | Name | Fitness Score | Risk Match | Concentration | Experience | Better Product |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for i, f_item in enumerate(fit[:10], 1):
                comp = f_item.get("component_scores", {})
                p_name = f_item.get("product_name", "")
                lines.append(
                    f"| {i} | {f_item.get('product_id', '')} | {p_name[:40]} | "
                    f"{f_item.get('fitness_score', ''):.2f} | "
                    f"{comp.get('risk_rating_match_score', ''):.1f} | "
                    f"{comp.get('concentration_score', ''):.1f} | "
                    f"{comp.get('has_similar_investment_experience_score', ''):.1f} | "
                    f"{comp.get('better_product_score', ''):.1f} |"
                )
            lines.append("")
        return "\n".join(lines)

    client_profile_content = "\n\n---\n\n".join(
        _format_client_profile(cid) for cid in eligible_client_ids
    )
    holdings_content = "\n\n---\n\n".join(
        format_holdings_table(clients_data.get(cid, {}).get("holdings", []))
        for cid in eligible_client_ids
    )

    docs = {
        API_CLIENT_PROFILE: ReferenceDocument(
            path=Path("api://client_profile"),
            content=client_profile_content,
            source_type="markdown",
        ),
        API_HOLDINGS: ReferenceDocument(
            path=Path("api://holdings"),
            content=holdings_content,
            source_type="markdown",
        ),
        API_PRODUCT_CATALOG: ReferenceDocument(
            path=Path("api://product_catalog"),
            content=_format_product_catalog(),
            source_type="markdown",
        ),
    }
    if market_outlook is not None:
        docs[API_MARKET_OUTLOOK] = ReferenceDocument(
            path=Path(API_MARKET_OUTLOOK),
            content=format_market_outlook_section(market_outlook),
            source_type="markdown",
        )

    return build_api_resolver(docs)


# ---------------------------------------------------------------------------
# In-memory API resolver for product_opportunity_proposal (per-pair)
# ---------------------------------------------------------------------------


def _build_fit_analysis_resolver(
    client_data: dict,
    product_data: dict,
    matching_markdown: str,
    market_outlook: str | None,
) -> Callable[[str], ReferenceDocument]:
    """Build a resolver for a single client×product pair."""
    return build_api_resolver({
        API_CLIENT_PROFILE: ReferenceDocument(
            path=Path("api://client_profile"),
            content=format_client_profile_markdown(client_data),
            source_type="markdown",
        ),
        API_PRODUCT_CATALOG: ReferenceDocument(
            path=Path("api://product_catalog"),
            content=format_product_single_recommended(product_data),
            source_type="markdown",
        ),
        API_MARKET_OUTLOOK: ReferenceDocument(
            path=Path(API_MARKET_OUTLOOK),
            content=format_market_outlook_section(market_outlook),
            source_type="markdown",
        ),
    })
