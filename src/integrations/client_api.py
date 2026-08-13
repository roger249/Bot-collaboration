"""
Client API — thin orchestrator (Logic Layer, no I/O).

Implements the four methods defined in:
    docs/prompts/prod_spec/tool/client_tool.md

All data is retrieved through the Data Access Layer adapters.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.adapters.data_adapter import DataAdapter, build_data_adapters
from src.planbot.client_enrichment import (
    _match_range,
    compute_derived_fields,
    search_holdings_maturing as _pure_search_holdings_maturing,
)

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"


# ---------------------------------------------------------------------------
# Config + adapter (loaded once per process)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_planbot_config() -> dict:
    return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _get_adapters() -> tuple[DataAdapter, DataAdapter]:
    return build_data_adapters(_load_planbot_config())


def _score_config() -> dict:
    return _load_planbot_config().get("investor_readiness_score", {})


# ---------------------------------------------------------------------------
# Holding formatting
# ---------------------------------------------------------------------------

_HOLDING_FIELDS = [
    "holding_idx", "holding_id", "product_id", "instrument_name", "symbol",
    "asset_class", "region", "currency", "quantity", "book_cost", "market_value",
    "unrealized_pl", "unrealized_pl_pct", "yield_pct", "risk_bucket", "esg_score", "liquidity",
]


def _format_holdings(holdings: list[dict]) -> list[dict]:
    """Order and trim raw holding dicts to the nested-holding shape."""
    ordered = sorted(holdings, key=lambda h: h.get("holding_idx") or 0)
    return [{k: h.get(k) for k in _HOLDING_FIELDS} for h in ordered]


# ---------------------------------------------------------------------------
# API Methods
# ---------------------------------------------------------------------------


def search_by_id(client_id: str) -> dict | None:
    """Return full client profile with nested holdings."""
    LOGGER.debug("search_by_id input: client_id=%s", client_id)
    client_adapter, product_adapter = _get_adapters()
    clients = client_adapter.fetch_clients([client_id])
    holdings = client_adapter.fetch_holdings([client_id])
    products = product_adapter.fetch_products()

    enriched = compute_derived_fields(clients, holdings, products, _score_config())
    client = enriched.get(client_id)
    if client is None:
        LOGGER.debug("search_by_id output: client_id=%s found=False", client_id)
        return None

    client["holdings"] = _format_holdings(holdings)
    LOGGER.debug("search_by_id output: %s", client)
    return client


def search(**criteria: Any) -> list[dict]:
    """Filter clients by demographic and portfolio criteria.

    Parameters (all optional except risk_rating):
        risk_rating: int or [min, max]
        age: int or [min, max]
        product_types_in_holdings: str or [str] — product_family values
        concentration_score: float or [min, max]
        cash_score: float or [min, max]
    """
    LOGGER.debug("search input: criteria=%s", criteria)
    client_adapter, product_adapter = _get_adapters()
    clients = client_adapter.fetch_clients()
    holdings = client_adapter.fetch_holdings()
    products = product_adapter.fetch_products()

    all_clients = compute_derived_fields(clients, holdings, products, _score_config())

    results = []
    for cid, c in all_clients.items():
        if not _match_range(c.get("risk_rating"), criteria.get("risk_rating")):
            continue
        if "age" in criteria and criteria["age"] is not None:
            if not _match_range(c.get("age"), criteria["age"]):
                continue
        if "product_types_in_holdings" in criteria and criteria["product_types_in_holdings"] is not None:
            cats = set(c.get("product_families_in_holdings", []))
            req = criteria["product_types_in_holdings"]
            if isinstance(req, str):
                req = [req]
            if not cats.intersection(req):
                continue
        if "concentration_score" in criteria and criteria["concentration_score"] is not None:
            if not _match_range(c.get("concentration_score"), criteria["concentration_score"]):
                continue
        if "cash_score" in criteria and criteria["cash_score"] is not None:
            if not _match_range(c.get("cash_score"), criteria["cash_score"]):
                continue
        results.append(c)

    results.sort(key=lambda x: x.get("investor_readiness_score", 0), reverse=True)
    LOGGER.debug("search output: %s", results)
    return results


def search_holdings_maturing(
    product_types: list[str] | None = None,
    within_days: int = 14,
    as_of_date: str | None = None,
) -> list[dict]:
    """Find bonds/FI maturing within a given window (pure Logic Layer)."""
    LOGGER.debug("search_holdings_maturing input: product_types=%s within_days=%s as_of_date=%s", product_types, within_days, as_of_date)
    client_adapter, product_adapter = _get_adapters()
    holdings = client_adapter.fetch_holdings()
    products = product_adapter.fetch_products()
    result = _pure_search_holdings_maturing(holdings, products, product_types, within_days, as_of_date)
    LOGGER.debug("search_holdings_maturing output: %s", result)
    return result


def search_by_investor_readiness_score(top_n: int | None = None) -> list[dict]:
    """Return clients ranked by investor readiness score."""
    LOGGER.debug("search_by_investor_readiness_score input: top_n=%s", top_n)
    client_adapter, product_adapter = _get_adapters()
    clients = client_adapter.fetch_clients()
    holdings = client_adapter.fetch_holdings()
    products = product_adapter.fetch_products()

    enriched = compute_derived_fields(clients, holdings, products, _score_config())
    ranked = sorted(
        enriched.values(),
        key=lambda c: c.get("investor_readiness_score", 0),
        reverse=True,
    )
    if top_n is not None and top_n > 0:
        ranked = ranked[:top_n]

    result = [
        {
            "rank": i,
            "client_id": c["client_id"],
            "name": c.get("name"),
            "total_score": c.get("investor_readiness_score", 0),
            "s_cash": c.get("cash_score", 0),
            "s_concentration": c.get("concentration_score", 0),
            "s_active": c.get("active_score", 0),
            "s_lifestage": c.get("life_stage_score", 0),
        }
        for i, c in enumerate(ranked, 1)
    ]
    LOGGER.info("IRS: %d clients scored (top_n=%s)", len(result), top_n)
    LOGGER.debug("search_by_investor_readiness_score output: %s", result)
    return result