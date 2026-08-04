"""Shared API resolver and content formatters for all proposals.

Every proposal type (reinvestment, product opportunity, product-investor
matching) needs to serve ``api://client_profile``, ``api://holdings``,
``api://product_catalog``, and ``api://market_outlook`` to the LLM via
CrewAI's ``load_references`` → ``api_resolver`` contract.

This module provides:

* ``build_api_resolver(documents)`` — the single routing function that
  all proposals share.  It maps ``api://`` paths onto pre-built
  ``ReferenceDocument`` content.

* ``format_client_profile_markdown(cp)`` — standard client-profile
  fields (common to all proposals).

* ``format_holdings_*`` — three output formats (table, bullets, CSV).

* ``format_product_multi`` / ``format_product_single`` — product-catalog
  formatting for batch and single-product views.

Adding a new proposal type should need *no code change* here unless
a new ``api://`` path is introduced.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_HOLDINGS,
    API_PRODUCT_CATALOG,
    ReferenceDocument,
)
from src.shared.market_outlook_utils import (
    API_MARKET_OUTLOOK,
    format_market_outlook_section,
)

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
        include ``API_CLIENT_PROFILE``, ``API_HOLDINGS``,
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

    Callers that need extra fields (cash_pct, investor_readiness_score,
    wallet-inflow events, etc.) should append them to the returned string.
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


def format_product_single(
    product: dict,
    *,
    alternatives: list[dict] | None = None,
) -> str:
    """Single product with optional alternatives."""
    lines = ["# Suggested Product", ""] + _product_header(product)
    if alternatives:
        lines += ["", "## Alternative Products", ""]
        for i, alt in enumerate(alternatives, 1):
            lines.append(
                f"{i}. {alt.get('product_id', '')} — {alt.get('name', '')} "
                f"(risk={alt.get('risk_rating', 'N/A')}, "
                f"expected_return={alt.get('expected_return', 'N/A')}%)"
            )
    return "\n".join(lines)


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
