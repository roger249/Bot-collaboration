"""Product scoring — pure Python Logic Layer (no I/O).

Similarity, fitness, and concentration scoring operate on plain dicts.
No ``duckdb`` / ``httpx`` here.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

from src.shared.product_family import get_product_family

_TIME_UNIT_TO_DAYS: dict[str, float] = {
    "d": 1.0,
    "w": 7.0,
    "m": 30.4375,  # 365.25 / 12
    "y": 365.25,
}

_ASSET_CLASS_MAP: dict[str, str] = {
    "bond": "fixed_income",
    "bond_fund": "fixed_income",
    "equity_fund": "equity",
    "stock": "equity",
    "money_market_fund": "cash",
    "balanced_fund": "balanced",
}


def _parse_time_to_maturity(raw: str) -> float | None:
    """Parse '2y', '30d', '6m' → days as float."""
    m = re.match(r"^([\d.]+)\s*([dwmy])$", raw.strip().lower())
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2)
    return value * _TIME_UNIT_TO_DAYS.get(unit, 365.25)


def _extract_time_to_maturity_days(product: dict, trade_date: str) -> float | None:
    """Extract time-to-maturity in days from a product dict."""
    ts = product.get("type_specific") or {}
    product_type = product.get("product_type", "")

    if product_type == "bond":
        maturity_str = ts.get("maturity")
        if maturity_str:
            try:
                maturity_date = date.fromisoformat(str(maturity_str))
                ref = date.fromisoformat(trade_date)
                return float((maturity_date - ref).days)
            except (ValueError, TypeError):
                return None
    elif product_type == "bond_fund":
        duration = ts.get("effective_duration")
        if duration is not None:
            try:
                return float(duration) * 365.0
            except (ValueError, TypeError):
                return None
    return None


def _extract_coupon(product: dict) -> float | None:
    """Extract coupon/dividend yield from type_specific JSON."""
    product_type = product.get("product_type", "")
    ts = product.get("type_specific") or {}

    if product_type == "bond":
        val = ts.get("coupon_rate")
        return float(val) if val is not None else None
    elif product_type == "bond_fund":
        val = ts.get("ytm")
        return float(val) if val is not None else None
    elif product_type in ("equity_fund", "stock", "balanced_fund"):
        val = ts.get("dividend_yield")
        return float(val) if val is not None else None
    elif product_type == "money_market_fund":
        val = ts.get("yield_type")
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
    return None


def _derive_asset_class(product_type: str) -> str:
    return _ASSET_CLASS_MAP.get(product_type, product_type)


def _linear_interpolate(x: float, pivot: dict[float, float]) -> float:
    """Linear interpolate (or extrapolate flat) x against pivot dict."""
    if not pivot:
        return 0.0
    sorted_keys = sorted(pivot.keys())
    if x <= sorted_keys[0]:
        return pivot[sorted_keys[0]]
    if x >= sorted_keys[-1]:
        return pivot[sorted_keys[-1]]
    for i in range(len(sorted_keys) - 1):
        x0, x1 = sorted_keys[i], sorted_keys[i + 1]
        if x0 <= x <= x1:
            y0, y1 = pivot[x0], pivot[x1]
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return 0.0


def compute_similarity_score(
    product: dict,
    query: dict,
    sigmas: dict[str, float],
    weights: dict[str, float],
    *,
    risk_rating_hard_filter: bool = True,
    trade_date: str = "",
) -> float:
    """Compute similarity score for a single product against the query."""
    score = 0.0
    total_weight = 0.0

    # --- numeric dimensions ---
    for dim in ("risk_rating", "expected_return"):
        q_val = query.get(dim)
        if q_val is None:
            continue
        p_val = product.get(dim)
        if p_val is None:
            continue
        sigma = sigmas.get(dim, 1.0)
        s_i = 1.0 - min(abs(p_val - q_val) / sigma, 1.0)
        w = weights.get(dim, 0.0)
        score += w * s_i
        total_weight += w

    # --- categorical dimensions ---
    for dim in ("product_type", "asset_class", "region", "sector"):
        q_val = query.get(dim)
        if q_val is None:
            continue
        if dim == "asset_class":
            p_val = _derive_asset_class(product.get("product_type", ""))
        else:
            p_val = product.get(dim)
        s_i = 1.0 if str(p_val or "").lower() == str(q_val or "").lower() else 0.0
        w = weights.get(dim, 0.0)
        score += w * s_i
        total_weight += w

    # --- time_to_maturity ---
    q_ttm = query.get("time_to_maturity")
    if q_ttm is not None:
        p_days = _extract_time_to_maturity_days(product, trade_date)
        if p_days is not None:
            q_days = _parse_time_to_maturity(str(q_ttm))
            if q_days is not None:
                sigma = sigmas.get("time_to_maturity", 730.0)
                s_i = 1.0 - min(abs(p_days - q_days) / sigma, 1.0)
                w = weights.get("time_to_maturity", 0.0)
                score += w * s_i
                total_weight += w

    # --- coupon ---
    q_coupon = query.get("coupon")
    if q_coupon is not None:
        p_coupon = _extract_coupon(product)
        if p_coupon is not None:
            sigma = sigmas.get("coupon", 2.0)
            s_i = 1.0 - min(abs(p_coupon - float(q_coupon)) / sigma, 1.0)
            w = weights.get("coupon", 0.0)
            score += w * s_i
            total_weight += w

    if total_weight == 0:
        return 0.0
    return score / total_weight  # renormalized by included dimensions


def compute_concentration_risk(
    client_id: str,
    candidate_product: dict,
    hold_details: list[dict],
    aum: float,
    test_notional: float,
    conc_config: dict,
    existing_concentration_score: float,
) -> float:
    """Compute hypothetical concentration risk after adding candidate product.

    Takes the existing concentration score and adjusts for the candidate's
    impact on single-holding, region, and asset-class exposures.
    """
    if aum <= 0:
        return existing_concentration_score

    single_pivot = {
        float(k): float(v)
        for k, v in conc_config.get("s_single_holding", {"0.2": 0, "1.0": 10}).items()
    }
    region_pivot = {
        float(k): float(v)
        for k, v in conc_config.get("s_region_exposure", {"0.4": 0, "1.0": 10}).items()
    }
    asset_pivot = {
        float(k): float(v)
        for k, v in conc_config.get("s_asset_class_exposure", {"0.6": 0, "1.0": 10}).items()
    }

    existing_single_max = max((h["market_value"] for h in hold_details), default=0)
    new_single_max = max(existing_single_max, test_notional)
    new_single_pct = new_single_max / aum
    s_single = _linear_interpolate(new_single_pct, single_pivot)

    candidate_region = candidate_product.get("region", "")
    region_totals: dict[str, float] = {}
    for h in hold_details:
        reg = h.get("region", "")
        if reg:
            region_totals[reg] = region_totals.get(reg, 0) + h["market_value"]
    if candidate_region:
        region_totals[candidate_region] = region_totals.get(candidate_region, 0) + test_notional
    max_region_pct = max(v / aum for v in region_totals.values()) if region_totals else 0
    s_region = _linear_interpolate(max_region_pct, region_pivot)

    candidate_ac = candidate_product.get("asset_class", "") or _derive_asset_class(
        candidate_product.get("product_type", "")
    )
    ac_totals: dict[str, float] = {}
    for h in hold_details:
        ac = h.get("asset_class", "")
        if ac:
            ac_totals[ac] = ac_totals.get(ac, 0) + h["market_value"]
    if candidate_ac:
        ac_totals[candidate_ac] = ac_totals.get(candidate_ac, 0) + test_notional
    max_ac_pct = max(v / aum for v in ac_totals.values()) if ac_totals else 0
    s_asset = _linear_interpolate(max_ac_pct, asset_pivot)

    return max(s_single, s_region, s_asset)


def _build_similarity_query_from_product(product: dict) -> dict:
    """Build a search_similar query dict from a product's attributes."""
    query: dict[str, Any] = {
        "risk_rating": product["risk_rating"],
        "expected_return": product["expected_return"],
        "product_type": product["product_type"],
        "region": product["region"],
        "sector": product["sector"],
    }
    query["asset_class"] = _derive_asset_class(product["product_type"])

    pt = product.get("product_type", "")
    if pt in ("bond", "bond_fund"):
        ts = product.get("type_specific") or {}
        if pt == "bond":
            query["time_to_maturity"] = "2y"
        else:
            dur = ts.get("effective_duration")
            if dur:
                query["time_to_maturity"] = f"{float(dur)}y"

    return query


def _get_product_expected_return(product_id: str, products_map: dict[str, dict]) -> float | None:
    """Look up expected_return from the products map (no DB fallback)."""
    return products_map.get(product_id, {}).get("expected_return")
