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
    API_PRODUCT_CATALOG,
    ReferenceDocument,
)
from src.planbot.pipeline_engine import PipelineEngine
from src.shared.config_loader import load_config
from src.shared.market_outlook_utils import (
    API_MARKET_OUTLOOK,
)
from src.shared.resolver_formatters import (
    build_proposal_resolver,
    format_client_and_holdings,
    format_irs_section,
    format_pfs_table,
    format_product_catalog,
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

        # ── Resolve pipeline inputs and merge into api_resolver ────────
        pipeline_engine = PipelineEngine(
            app_config, config_path=_CONFIG_PATH, proposal_id="product_investor_matching"
        )
        prep = pipeline_engine.prepare(
            client_selection=client_selection,
            product_ids=product_ids,
            market_outlook_text=market_outlook,
        )

        if prep.file_reference_docs:
            _orig = api_resolver
            _dm = {str(d.path): d for d in prep.file_reference_docs}

            def _merged_matcher(path: str) -> ReferenceDocument:
                _nm = path.replace("//", "/")
                if _nm in _dm:
                    return _dm[_nm]
                return _orig(path)

            api_resolver = _merged_matcher

        _sm: dict[str, list[str]] = {
            "proposal_instructions_and_format": [],
            "guidelines": [],
            "client_profiles": [API_CLIENT_PROFILE],
            "product_catalogs": [API_PRODUCT_CATALOG],
            "market_outlook": [],
        }
        for inp in pipeline_engine.inputs:
            pid = inp.id
            if pid in ("proposal_instructions", "section_guides"):
                _sm["proposal_instructions_and_format"].append(f"api://resolved/{pid}")
            elif pid in ("general_guidelines", "financial_needs_guidelines"):
                _sm["guidelines"].append(f"api://resolved/{pid}")
            elif pid == "market_outlook":
                if prep.resolved_inputs.get("market_outlook"):
                    _sm["market_outlook"].append(f"api://resolved/{pid}")

        reference_overrides = {k: v for k, v in _sm.items() if v}
        if market_outlook is not None:
            reference_overrides["market_outlook"] = [API_MARKET_OUTLOOK]

        _section_purposes: dict[str, str] = {}
        for inp in pipeline_engine.inputs:
            if inp.id == "client_profile" and inp.description:
                _section_purposes["client_profiles"] = inp.description
            elif inp.id == "product_catalog" and inp.description:
                _section_purposes["product_catalogs"] = inp.description

        crew_result = run_crew_planbot(
            app_config=app_config,
            config_path=str(_CONFIG_PATH),
            proposal_name="product_investor_matching",
            runtime_reference_overrides=reference_overrides,
            runtime_section_purposes=_section_purposes,
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
            "matching_context": p.get("matching_context", ""),
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
    from datetime import datetime
    return datetime.now().strftime("run-%Y%m%d-%H%M%S")


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

    pairs = _extract_top_pairs_from_summary_table(
        markdown=markdown,
        client_id_re=client_id_re,
        product_id_re=product_id_re,
        amount_re=amount_re,
    )
    if not pairs:
        pairs = _extract_top_pairs_from_narrative_sections(
            markdown=markdown,
            client_id_re=client_id_re,
            product_id_re=product_id_re,
            amount_re=amount_re,
            alt_product_re=alt_product_re,
        )

    if not pairs:
        LOGGER.warning("_extract_top_pairs: no table rows parsed from markdown")
        return []

    # ── 2. Extract alternatives from per-client sections ────────────────
    # Split on ##/### headers; only process sections starting with a client ID
    client_sections = re.split(r"\n(?=#{2,3}\s)", markdown)
    context_score_by_client: dict[str, int] = {}
    for section in client_sections:
        cid_match = client_id_re.search(section)
        if not cid_match:
            continue
        section_cid = cid_match.group(0)

        # Find the pair for this section
        pair = next((p for p in pairs if p["client_id"] == section_cid), None)
        if not pair:
            continue

        section_text = _normalize_matching_context_markers(section.strip())
        section_score = _score_matching_context_section(section_text)
        current_score = context_score_by_client.get(section_cid, -1)
        if section_score >= current_score:
            pair["matching_context"] = section_text
            context_score_by_client[section_cid] = section_score

        # Find #### Alternative suggestion block — stop at next ##/### header or end
        alt_block_match = re.search(
            r"####\s+Alternative\s+suggestion\s*\n(.*?)(?=\n(?:#{2,3})\s|\Z)",
            section, re.DOTALL | re.IGNORECASE,
        )
        alt_ids: list[str] = []
        if alt_block_match:
            alt_ids = alt_product_re.findall(alt_block_match.group(1))
        else:
            inline_alt_match = re.search(
                r"-\s+\*\*Alternative\s+suggestion:\*\*\s*(.*?)(?=\n-\s+\*\*|\Z)",
                section,
                re.DOTALL | re.IGNORECASE,
            )
            if inline_alt_match:
                alt_ids = alt_product_re.findall(inline_alt_match.group(1))

        if not alt_ids:
            continue

        pair["alternative_product_ids"] = list(dict.fromkeys(alt_ids))  # dedupe, preserve order

    pairs.sort(key=lambda x: x.get("buying_score", 0), reverse=True)
    return pairs[:top_n]


def _extract_top_pairs_from_summary_table(
    *,
    markdown: str,
    client_id_re: re.Pattern[str],
    product_id_re: re.Pattern[str],
    amount_re: re.Pattern[str],
) -> list[dict]:
    pairs: list[dict] = []
    in_table = False

    for line in markdown.split("\n"):
        stripped = line.strip()
        if "| Client ID" in stripped and "| Buying Score" in stripped:
            in_table = True
            continue
        if in_table and re.match(r"^\|[-:\s|]+\|$", stripped):
            continue
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

            pid_match = product_id_re.search(cells[2])
            product_id = pid_match.group(0) if pid_match else ""

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
                "matching_context": "",
            })

    return pairs


def _extract_top_pairs_from_narrative_sections(
    *,
    markdown: str,
    client_id_re: re.Pattern[str],
    product_id_re: re.Pattern[str],
    amount_re: re.Pattern[str],
    alt_product_re: re.Pattern[str],
) -> list[dict]:
    pairs: list[dict] = []
    section_pattern = re.compile(
        r"(?ms)^(?:###\s+Client ID:|#\s+Reinvestment Analysis:\s+Client ID:).*?(?=^(?:###\s+Client ID:|#\s+Reinvestment Analysis:\s+Client ID:)|\Z)",
    )

    for match in section_pattern.finditer(markdown):
        section = match.group(0)

        cid_match = client_id_re.search(section)
        if not cid_match:
            continue
        client_id = cid_match.group(0)

        product_match = re.search(
            r"Recommended Product:\s*([A-Za-z0-9._-]+)",
            section,
            re.IGNORECASE,
        )
        if not product_match:
            product_match = product_id_re.search(section)
        product_id = product_match.group(1) if product_match and product_match.groups() else (product_match.group(0) if product_match else "")

        buying_score = 0.0
        score_match = re.search(r"\|\s*Buying Score\s*\|\s*([0-9]+(?:\.[0-9]+)?)(?:/5)?\s*\|", section, re.IGNORECASE)
        if not score_match:
            score_match = re.search(r"Buying Score[:\s]*([0-9]+(?:\.[0-9]+)?)(?:/5)?", section, re.IGNORECASE)
        if score_match:
            try:
                buying_score = float(score_match.group(1))
            except (ValueError, TypeError):
                buying_score = 0.0

        amount_match = amount_re.search(section)
        investment_amount = amount_match.group(1) if amount_match else ""

        funding_match = re.search(
            r"Funding Source\s*\|\s*(.*?)\s*\|",
            section,
            re.IGNORECASE | re.DOTALL,
        )
        funding_source = funding_match.group(1).strip() if funding_match else ""

        rationale_match = re.search(
            r"\*\*Detailed justification:\*\*\s*(.*?)(?=\n###\s|\n---\s|\Z)",
            section,
            re.IGNORECASE | re.DOTALL,
        )
        if not rationale_match:
            rationale_match = re.search(
                r"\*\*Detailed justification\*\*\s*(.*?)(?=\n###\s|\n---\s|\Z)",
                section,
                re.IGNORECASE | re.DOTALL,
            )
        rationale = rationale_match.group(1).strip() if rationale_match else section.strip()

        alt_block_match = re.search(
            r"####\s+(?:Alternative\s+Products?\s+to\s+Consider|Alternative\s+suggestion)\s*\n(.*?)(?=\n(?:#{2,3})\s|\Z)",
            section,
            re.DOTALL | re.IGNORECASE,
        )
        alt_ids: list[str] = []
        if alt_block_match:
            alt_ids = alt_product_re.findall(alt_block_match.group(1))

        pairs.append({
            "client_id": client_id,
            "product_id": product_id,
            "buying_score": buying_score,
            "rationale": rationale,
            "investment_amount": investment_amount,
            "funding_source": funding_source,
            "alternative_product_ids": list(dict.fromkeys(alt_ids)),
            "matching_context": section.strip(),
        })

    return pairs


def _score_matching_context_section(section: str) -> int:
    """Return a heuristic score for selecting the best per-client context block.

    Detailed analysis sections include recommendation bullets such as
    ``Suggestion``, ``Financial-need fit``, and ``Key factors`` and should win
    over summary-table or alternatives-only sections.
    """
    lowered = section.lower()
    score = 0

    # Prefer explicit per-client markdown blocks over generic summary chunks.
    if section.startswith("### "):
        score += 2

    for marker in (
        "**suggestion:**",
        "**financial-need fit:**",
        "**key factors:**",
        "**return comparison:**",
        "**concentration impact:**",
    ):
        if marker in lowered:
            score += 2

    # Penalize alternatives-only client sections that appear later in reports.
    if "alternative products to consider" in lowered and "**suggestion:**" not in lowered:
        score -= 2

    return score


def _normalize_matching_context_markers(section: str) -> str:
    """Normalize common LLM label variants to stable matcher-context headings.

    The proposal pipeline expects consistent marker names for prompt assembly
    and regression checks. Different LLM runs may emit semantically equivalent
    headings (e.g. Recommendation, Financial need, Why this fits). This helper
    rewrites those variants to canonical labels.
    """
    normalized = section

    replacements: list[tuple[str, str]] = [
        (r"\*\*Recommendation:\*\*", "**Suggestion:**"),
        (r"\*\*Financial needs?:\*\*", "**Financial-need fit:**"),
        (r"\*\*Why this fits:\*\*", "**Financial-need fit:**"),
    ]
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

    return normalized


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
        rank_str = f"{eligible_client_ids.index(cid) + 1}/{len(eligible_client_ids)}" if cid in eligible_client_ids else None
        irs_text = format_irs_section(
            total=readiness.get("total_score"),
            rank=rank_str,
            cash_drag=readiness.get("s_cash"),
            concentration=readiness.get("s_concentration"),
            active_management=readiness.get("s_active"),
            life_stage=readiness.get("s_lifestage"),
        )
        return format_client_and_holdings(cp, extra_sections=[irs_text] if irs_text else [])

    def _format_product_catalog() -> str:
        products = [products_data[pid] for pid in product_universe if pid in products_data]
        content = format_product_catalog(
            alternatives=products,
            include_suggested_section=False,
            include_holdings_section=False,
        )
        # Append fitness score summary per client (uses shared format_pfs_table)
        lines = [content, "", "## Product Fitness Scores (per client)", ""]
        for cid in eligible_client_ids:
            fit = fitness_results.get(cid, [])
            if not fit:
                continue
            cp = clients_data.get(cid, {})
            lines.append(f"### {cid} — {cp.get('name', 'N/A')} (RR={cp.get('risk_rating', 'N/A')})")
            lines.append("")
            # Build pfs_scores dict for this client
            pfs_for_client: dict[str, dict] = {}
            for f_item in fit[:10]:
                pid = f_item.get("product_id", "")
                comp = dict(f_item.get("component_scores", {}))
                comp["fitness_score"] = f_item.get("fitness_score", 0)
                comp["product_name"] = f_item.get("product_name", "")
                pfs_for_client[pid] = comp
            lines += format_pfs_table(pfs_for_client, include_name=True)
            lines.append("")
        return "\n".join(lines)

    client_profile_content = "\n\n---\n\n".join(
        _format_client_profile(cid) for cid in eligible_client_ids
    )

    return build_proposal_resolver(
        client_content=client_profile_content,
        product_content=_format_product_catalog(),
        market_outlook=market_outlook,
    )


# ═══════════════════════════════════════════════════════════════════════════
# End of resolver helpers
# ═══════════════════════════════════════════════════════════════════════════
