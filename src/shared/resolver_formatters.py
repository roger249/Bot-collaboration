"""Shared API resolver and content formatters for all proposals.

Every proposal type (reinvestment, product opportunity, product-investor
matching) needs to serve ``api://client_profile``, ``api://holdings``,
``api://product_catalog``, and ``api://market_outlook`` to the LLM via
CrewAI's ``load_references`` → ``api_resolver`` contract.

This module provides:

* ``build_api_resolver(documents)`` — maps ``api://`` paths onto
  pre-built ``ReferenceDocument`` content.

* ``build_proposal_resolver(client_content, product_content, …)`` —
  one-stop builder for the standard 3-document resolver that all
  proposals share.  Add ``extra_docs`` for proposal-specific paths
  (e.g. ``api://suggested_products_and_rationale``).

* ``format_client_and_holdings(cp, …)`` — unified client + holdings
  markdown for all proposals.

* ``format_product_catalog(…)`` — unified product catalog (suggested /
  holdings / alternatives) for all proposals.

Adding a new proposal type should need *no code change* here unless
a new ``api://`` path is introduced.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml

from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_PRODUCT_CATALOG,
    ReferenceDocument,
)
from src.shared.market_outlook_utils import (
    API_MARKET_OUTLOOK,
    format_market_outlook_section,
)

# ═══════════════════════════════════════════════════════════════════════════
# Shared HTTP resolver config reader (used by all proposal integrations)
# ═══════════════════════════════════════════════════════════════════════════


def read_http_resolver_config(config_path: Path) -> dict | None:
    """Read HTTP resolver settings from config_planbot.yaml common section.

    Returns None if the section is absent (Phase A / local-import fallback).
    """
    planbot_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    common = planbot_config.get("common") or {}
    if not common.get("get_client_product_from_db"):
        return None
    return common.get("http_resolver")  # None if not configured → Phase A


# ═══════════════════════════════════════════════════════════════════════════
# Routing resolver — the single function all proposals share
# ═══════════════════════════════════════════════════════════════════════════


def build_api_resolver(
    documents: dict[str, ReferenceDocument],
) -> Callable[[str], ReferenceDocument]:
    """Build a resolver that maps ``api://`` paths to pre-built documents.

    Parameters
    ----------
    documents : dict[str, ReferenceDocument]
        Mapping of ``api://`` path → ``ReferenceDocument``.  Keys may
        include ``API_CLIENT_PROFILE``,
        ``API_PRODUCT_CATALOG``, ``API_MARKET_OUTLOOK``, or any custom
        path added by a specific proposal type.

    Returns
    -------
    Callable[[str], ReferenceDocument]
        Resolver compatible with ``load_references(api_resolver=…)``.
    """

    def resolve(api_path: str) -> ReferenceDocument:
        doc = documents.get(api_path)
        if doc is not None:
            return doc
        return ReferenceDocument(
            path=Path(api_path),
            content="",
            source_type="markdown",
        )

    return resolve


def build_proposal_resolver(
    client_content: str,
    product_content: str,
    *,
    market_outlook: str | None = None,
    extra_docs: dict[str, ReferenceDocument] | None = None,
) -> Callable[[str], ReferenceDocument]:
    """One-stop builder for the resolver that ALL proposals share.

    Every proposal types needs at least ``API_CLIENT_PROFILE`` and
    ``API_PRODUCT_CATALOG``.  ``API_MARKET_OUTLOOK`` is added when
    ``market_outlook`` is explicitly provided; otherwise the file glob
    from ``config_planbot.yaml`` loads it.

    Parameters
    ----------
    client_content : str
        Formatted client + holdings markdown (from ``format_client_and_holdings``).
    product_content : str
        Formatted product catalog markdown (from ``format_product_catalog``).
    market_outlook : str | None
        Explicit market outlook text.  When None, omitted — let the YAML
        file glob handle it.
    extra_docs : dict[str, ReferenceDocument] | None
        Proposal-specific extra documents (e.g. ``API_SUGGESTED_PRODUCTS_AND_RATIONALE``).

    Returns
    -------
    Callable[[str], ReferenceDocument]
        Resolver compatible with ``load_references(api_resolver=…)``.
    """
    docs: dict[str, ReferenceDocument] = {
        API_CLIENT_PROFILE: ReferenceDocument(
            path=Path(API_CLIENT_PROFILE),
            content=client_content,
            source_type="markdown",
        ),
        API_PRODUCT_CATALOG: ReferenceDocument(
            path=Path(API_PRODUCT_CATALOG),
            content=product_content,
            source_type="markdown",
        ),
    }
    if market_outlook is not None:
        docs[API_MARKET_OUTLOOK] = ReferenceDocument(
            path=Path(API_MARKET_OUTLOOK),
            content=format_market_outlook_section(market_outlook),
            source_type="markdown",
        )
    if extra_docs:
        docs.update(extra_docs)
    return build_api_resolver(docs)


def _doc(
    api_path: str,
    content: str,
    source_type: str = "markdown",
) -> ReferenceDocument:
    return ReferenceDocument(
        path=Path(api_path),
        content=content,
        source_type=source_type,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Client profile — standard fields shared by all proposals
# ═══════════════════════════════════════════════════════════════════════════


def format_client_profile_markdown(cp: dict) -> str:
    """Standard client-profile markdown used across all proposals.

    Fields rendered (all optional — ``N/A`` if missing):
        client_id, name, age, occupation, risk_rating, region,
        aum, investment_objective, liquidity_need,
        qualitative_profile → RM Notes.

    For extra sections beyond the standard fields, use
    ``format_client_and_holdings()`` instead.
    """
    lines = [
        "# Client Profile",
        "",
        f"- Client ID: {cp.get('client_id', 'N/A')}",
        f"- Name: {cp.get('name', 'N/A')}",
        f"- Age: {cp.get('age', 'N/A')}",
        f"- Occupation: {cp.get('occupation', 'N/A')}",
        f"- Risk Rating (1-5): {cp.get('risk_rating', 'N/A')}",
        f"- Region: {cp.get('region', 'N/A')}",
    ]
    aum = cp.get("aum")
    lines.append(f"- AUM: ${aum:,.0f}" if aum else "- AUM: N/A")
    lines += [
        f"- Investment Objective: {cp.get('investment_objective', 'N/A')}",
        f"- Liquidity Need: {cp.get('liquidity_need', 'N/A')}",
    ]
    qp = cp.get("qualitative_profile")
    if qp:
        lines += ["", "## RM Notes", "", qp]
    return "\n".join(lines)


def format_client_and_holdings(
    cp: dict,
    *,
    extra_sections: list[str] | None = None,
) -> str:
    """Unified client-profile + holdings for ALL proposal types.

    This is the single routine used by product_opportunity_proposal,
    reinvestment_proposal, and product_investor_matcher.  All three
    get the same client format and the same holdings table.

    Parameters
    ----------
    cp : dict
        Client dict from ``search_by_id()``.  Must include ``holdings``.
    extra_sections : list[str] | None
        Additional markdown blocks appended after the standard profile
        fields (e.g. investor readiness score, wallet inflow event).

    Returns
    -------
    str
        ``# Client Profile`` + extra sections + ``# Holdings`` table.
    """
    parts = [format_client_profile_markdown(cp)]
    if extra_sections:
        parts.extend(extra_sections)
    holdings = cp.get("holdings", [])
    if holdings:
        parts.append(format_holdings_table(holdings))
    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Holdings — three formats
# ═══════════════════════════════════════════════════════════════════════════


_HOLDINGS_FIELDNAMES = [
    "product_id", "instrument_name", "asset_class",
    "market_value", "yield_pct", "risk_bucket",
]


def format_holdings_table(holdings: list[dict]) -> str:
    """Markdown table of holdings."""
    if not holdings:
        return "# Holdings\n\n(No holdings data available)"
    lines = ["# Holdings", ""]
    lines.append(
        "| # | Product ID | Name | Asset Class | Market Value | Yield % | Risk |",
    )
    lines.append("|---|---|---|---|---|---|---|")
    for i, h in enumerate(holdings, 1):
        lines.append(
            f"| {i} | {h.get('product_id', '')} | {h.get('instrument_name', '')} | "
            f"{h.get('asset_class', '')} | ${h.get('market_value', 0):,.0f} | "
            f"{h.get('yield_pct', '')} | {h.get('risk_bucket', '')} |"
        )
    return "\n".join(lines)


def format_holdings_bullets(holdings: list[dict]) -> str:
    """Bullet-list summary of holdings (compact)."""
    if not holdings:
        return ""
    lines = ["## Holdings", ""]
    for h in holdings:
        lines.append(
            f"- {h.get('product_id', '')} {h.get('instrument_name', '')}: "
            f"${h.get('market_value', 0):,.0f} "
            f"({h.get('asset_class', '')}, {h.get('yield_pct', '')}%)"
        )
    return "\n".join(lines)


def format_holdings_csv(holdings: list[dict]) -> str:
    """CSV representation of holdings."""
    fieldnames = [
        "client_id", "holding_id", "product_id", "instrument_name",
        "symbol", "asset_class", "region", "currency", "quantity",
        "book_cost", "market_value", "unrealized_pl", "unrealized_pl_pct",
        "yield_pct", "risk_bucket", "esg_score", "liquidity",
    ]
    lines: list[str] = [",".join(fieldnames)]
    for h in holdings:
        row = ",".join(str(h.get(f, "")) for f in fieldnames)
        lines.append(row)
    return "\n".join(lines) + "\n"


# ═══════════════════════════════════════════════════════════════════════════
# Product catalog — single-product and multi-product views
# ═══════════════════════════════════════════════════════════════════════════


def _product_header(p: dict) -> list[str]:
    note = p.get("investment_note")
    header = [
        f"- Product ID: {p.get('product_id', 'N/A')}",
        f"- Name: {p.get('name', 'N/A')}",
        f"- Type: {p.get('product_type', 'N/A')}",
        f"- Risk Rating: {p.get('risk_rating', 'N/A')}",
        f"- Expected Return: {p.get('expected_return', 'N/A')}%",
    ]
    if note:
        header += ["", "## Investment Note", "", note]
    return header


def format_product_catalog(
    *,
    suggested: dict | None = None,
    holdings: list[dict] | None = None,
    alternatives: list[dict] | None = None,
    pfs_scores: dict[str, dict] | None = None,
) -> str:
    """Unified product catalog for ALL proposal types.

    This is the single routine used by product_opportunity_proposal,
    reinvestment_proposal, and product_investor_matcher.  The only
    differences across proposals are whether *alternatives* and
    *pfs_scores* are present.

    Parameters
    ----------
    suggested : dict | None
        The single recommended product (for single-product proposals).
        Passed as a full product dict from search_by_product_id().
    holdings : list[dict] | None
        Client's existing holdings, resolved to full product dicts.
    alternatives : list[dict] | None
        Alternative products, resolved to full product dicts.
    pfs_scores : dict[str, dict] | None
        Product Fitness Scores for suggested + alternatives only
        (holdings are NOT scored).  Maps product_id → component_scores dict
        with keys: fitness_score, risk_rating_match_score,
        concentration_score, has_similar_investment_experience_score,
        better_product_score.  When present, a ## Product Fitness Scores
        table is appended after the alternatives section.

    Returns
    -------
    str
        Markdown with sections: Suggested Product, Client Holdings,
        Alternative Products, Product Fitness Scores (if pfs_scores).
    """
    lines = ["# Product Catalog", ""]

    # ── 1. Suggested Product ───────────────────────────────────────
    if suggested:
        lines += _product_header_suggested(suggested)
    else:
        lines.append("*(no suggested product)*")

    # ── 2. Client Holdings ─────────────────────────────────────────
    if holdings:
        lines += ["", "## Client Holdings", ""]
        for i, h in enumerate(holdings, 1):
            lines.append(
                f"{i}. {h.get('product_id', '')} — {h.get('name', 'N/A')} "
                f"(risk={h.get('risk_rating', 'N/A')}, "
                f"expected_return={h.get('expected_return', 'N/A')}%, "
                f"type={h.get('product_type', 'N/A')})"
            )
    else:
        lines += ["", "## Client Holdings", "", "*(no holdings data)*"]

    # ── 3. Alternative Products ────────────────────────────────────
    if alternatives:
        lines += ["", "## Alternative Products", ""]
        for i, alt in enumerate(alternatives, 1):
            lines.append(
                f"{i}. {alt.get('product_id', '')} — {alt.get('name', '')} "
                f"(risk={alt.get('risk_rating', 'N/A')}, "
                f"expected_return={alt.get('expected_return', 'N/A')}%)"
            )
    else:
        lines += ["", "## Alternative Products", "", "*(none)*"]

    # ── 4. Product Fitness Scores (suggested + alternatives only) ──
    if pfs_scores:
        lines.append("")
        lines.append("## Product Fitness Scores")
        lines.append("")
        lines += format_pfs_table(pfs_scores)

    return "\n".join(lines)


def _product_header_suggested(p: dict) -> list[str]:
    note = p.get("investment_note")
    header = [
        "## Suggested Product",
        "",
        f"- Product ID: {p.get('product_id', 'N/A')}",
        f"- Name: {p.get('name', 'N/A')}",
        f"- Type: {p.get('product_type', 'N/A')}",
        f"- Risk Rating: {p.get('risk_rating', 'N/A')}",
        f"- Expected Return: {p.get('expected_return', 'N/A')}%",
    ]
    if note:
        header += ["", "### Investment Note", "", note]
    return header


def format_product_single(
    product: dict,
    *,
    alternatives: list[dict] | None = None,
    holdings: list[dict] | None = None,
) -> str:
    """DEPRECATED: Use format_product_catalog() instead."""
    return format_product_catalog(
        suggested=product,
        holdings=holdings,
        alternatives=alternatives,
    )


def format_product_single_recommended(product: dict) -> str:
    """Single product as 'Recommended Product' heading (matcher per-pair)."""
    lines = ["# Recommended Product", ""] + _product_header(product)
    return "\n".join(lines)


def format_product_multi(products: list[dict]) -> str:
    """Multi-product catalog listing."""
    lines = ["# Product Catalog", ""]
    for p in products:
        lines.append(f"## {p.get('product_id', '')} — {p.get('name', 'N/A')}")
        lines.append(f"- Type: {p.get('product_type', 'N/A')}")
        lines.append(f"- Risk Rating: {p.get('risk_rating', 'N/A')}")
        lines.append(f"- Expected Return: {p.get('expected_return', 'N/A')}%")
        lines.append(f"- Region: {p.get('region', 'N/A')}")
        lines.append(f"- Sector: {p.get('sector', 'N/A')}")
        note = p.get("investment_note")
        if note:
            lines.append(f"- Investment Note: {note}")
        lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Shared IRS section — used by all proposals
# ═══════════════════════════════════════════════════════════════════════════


def format_irs_section(*, total=None, rank=None, cash_drag=None, concentration=None, active_management=None, life_stage=None):
    """Render IRS section. All fields optional — omitted when None. Returns "" when all None."""
    lines = ["## Investor Readiness Score", ""]
    if rank is not None: lines.append(f"Rank: {rank}")
    if total is not None: lines.append(f"Total Score: {total}")
    for label, val in [("Cash Drag", cash_drag), ("Concentration", concentration), ("Active Management", active_management), ("Life Stage", life_stage)]:
        if val is not None: lines.append(f"  - {label}: {val}")
    return "\n".join(lines) if len(lines) > 2 else ""


# ═══════════════════════════════════════════════════════════════════════════
# Shared PFS table rendering — used by all proposals
# ═══════════════════════════════════════════════════════════════════════════


def format_pfs_table(
    pfs_scores: dict[str, dict],
    *,
    include_name: bool = False,
) -> list[str]:
    """Render a PFS component-score table from a product_id → scores dict.

    Parameters
    ----------
    pfs_scores : dict[str, dict]
        Mapping of product_id → component_scores dict.  May be a single
        client's suggested+alternatives (reinvestment, product-opp) or
        all products in the universe (matcher).
    include_name : bool
        If True, adds a ``Name`` column after Product ID (used by matcher
        which doesn't hardcode product names in the catalog listing).

    Returns
    -------
    list[str]
        Markdown lines — the table header, separator, and one row per
        product.  Does NOT include the section heading (caller adds it).
    """
    if not pfs_scores:
        return []

    if include_name:
        header = "| # | Product ID | Name | Fitness Score | Risk Match | Concentration | Experience | Better Product |"
        sep   = "|---|---|---|---|---|---|---|---|"
    else:
        header = "| # | Product ID | Fitness Score | Risk Match | Concentration | Experience | Better Product |"
        sep   = "|---|---|---|---|---|---|---|"

    lines = [header, sep]
    for i, (pid, comp) in enumerate(pfs_scores.items(), 1):
        row = f"| {i} | {pid} |"
        if include_name:
            row += f" {comp.get('product_name', '')[:40]} |"
        row += (
            f" {comp.get('fitness_score', ''):.2f} |"
            f" {comp.get('risk_rating_match_score', ''):.1f} |"
            f" {comp.get('concentration_score', ''):.1f} |"
            f" {comp.get('has_similar_investment_experience_score', ''):.1f} |"
            f" {comp.get('better_product_score', ''):.1f} |"
        )
        lines.append(row)
    return lines


# ═══════════════════════════════════════════════════════════════════════════
# Shared PFS helper (used by all proposal integrations)
# ═══════════════════════════════════════════════════════════════════════════


def compute_pfs_for_products(
    client_id: str,
    suggested_product_id: str,
    alternative_products: list[dict],
) -> dict[str, dict]:
    """Compute PFS component scores for suggested + alternative products.

    Only the suggested product and its alternatives are scored — holdings
    are not included (they are portfolio context only).

    Returns a dict mapping product_id → component_scores.
    """
    import logging
    from src.integrations.product_tool import search_product_by_fitness_score

    LOGGER = logging.getLogger(__name__)

    all_pids = [suggested_product_id] + [
        p["product_id"] for p in alternative_products if p.get("product_id")
    ]
    if not all_pids:
        return {}

    try:
        pfs_result = search_product_by_fitness_score(
            client_ids=[client_id],
            product_ids=all_pids,
            top_n=len(all_pids),
        )
    except Exception:
        LOGGER.warning("PFS computation failed for client %s", client_id, exc_info=True)
        return {}

    scores: dict[str, dict] = {}
    for r in pfs_result.get("results", []):
        pid = r.get("product_id", "")
        scores[pid] = {
            "fitness_score": r.get("fitness_score", 0),
            "risk_rating_match_score": r.get("component_scores", {}).get("risk_rating_match_score", 0),
            "concentration_score": r.get("component_scores", {}).get("concentration_score", 0),
            "has_similar_investment_experience_score": r.get("component_scores", {}).get("has_similar_investment_experience_score", 0),
            "better_product_score": r.get("component_scores", {}).get("better_product_score", 0),
        }
    return scores
