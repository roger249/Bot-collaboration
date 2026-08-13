"""Client enrichment — pure Python Logic Layer (no I/O).

Consumes plain ``list[dict]`` from the Data Access Layer and produces
derived fields, scores, and filtered results.  No ``duckdb`` / ``httpx`` here.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from src.planbot.investor_readiness_score import (
    compute_total_scores,
    score_active_manage,
    score_cash_drag,
    score_concentration_risk,
    score_life_stage,
)
from src.shared.product_family import get_product_family


def _compute_age(birthdate: Any, today: date) -> int | None:
    """Compute age in years from an ISO birthdate string (or None)."""
    if not birthdate or str(birthdate).upper() in ("N/A", ""):
        return None
    try:
        parts = str(birthdate).strip().split("-")
        if len(parts) < 3:
            return None
        bd = date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None
    return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))


def compute_derived_fields(
    clients: list[dict],
    holdings: list[dict],
    products: list[dict],
    score_config: dict,
) -> dict[str, dict[str, Any]]:
    """Pure function. No I/O. Returns enriched client dicts keyed by client_id.

    Replaces the old ``_compute_derived_fields(conn)`` — same derived fields,
    same scorecard invocation, but operating on plain dicts.
    """
    product_map = {p["product_id"]: p for p in products}
    today = date.today()

    enriched: dict[str, dict] = {}
    for c in clients:
        cid = c["client_id"]
        cdata = dict(c)
        # Normalize risk_rating to int (may be stored as VARCHAR after migration)
        rr = cdata.get("risk_rating")
        if rr is not None and not isinstance(rr, int):
            try:
                cdata["risk_rating"] = int(rr)
            except (ValueError, TypeError):
                cdata["risk_rating"] = None
        cdata["age"] = _compute_age(cdata.get("birthdate"), today)
        enriched[cid] = cdata

    # has_fund — client holds any product whose product_type != money_market_fund
    has_fund: set[str] = set()
    for h in holdings:
        p = product_map.get(h["product_id"])
        if p is not None and p.get("product_type") != "money_market_fund":
            has_fund.add(h["client_id"])
    for cid in enriched:
        enriched[cid]["has_fund"] = cid in has_fund

    # product_types_in_holdings / product_families_in_holdings
    pt_map: dict[str, set] = {}
    for h in holdings:
        p = product_map.get(h["product_id"])
        if p is not None:
            pt_map.setdefault(h["client_id"], set()).add(p.get("product_type"))
    for cid in enriched:
        pts = pt_map.get(cid, set())
        enriched[cid]["product_types_in_holdings"] = sorted(pts)
        enriched[cid]["product_families_in_holdings"] = sorted(
            {get_product_family(p) for p in pts}
        )

    # cash_pct_computed — max(reported cash_pct, Cash-class MV / aum * 100)
    cash_mv: dict[str, float] = {}
    for h in holdings:
        if h.get("asset_class") == "Cash":
            cash_mv[h["client_id"]] = cash_mv.get(h["client_id"], 0.0) + (h.get("market_value") or 0.0)
    for cid, cdata in enriched.items():
        aum = cdata.get("aum") or 0
        raw_cp = cdata.get("cash_pct")
        mmf = cash_mv.get(cid, 0.0)
        if aum and aum > 0:
            mmf_pct = (mmf / aum) * 100 if mmf else 0
            cdata["cash_pct_computed"] = round(max(raw_cp or 0, mmf_pct), 2)
        else:
            cdata["cash_pct_computed"] = 0.0

    # Attach scores from the scorecard engine
    clients_list = list(enriched.values())
    cash_sc = score_cash_drag(clients_list, holdings, score_config.get("score_cash_drag", {}))
    conc_sc = score_concentration_risk(clients_list, holdings, score_config.get("score_concentration_risk", {}))
    act_sc = score_active_manage(clients_list, holdings, score_config.get("score_active_manage", {}))
    life_sc = score_life_stage(clients_list, score_config.get("score_life_stage", {}))
    total_sc = {
        s.client_id: s.total_score
        for s in compute_total_scores(clients_list, holdings, score_config)
    }

    for cid in enriched:
        enriched[cid]["cash_score"] = cash_sc.get(cid, 0.0)
        enriched[cid]["concentration_score"] = conc_sc.get(cid, 0.0)
        enriched[cid]["active_score"] = act_sc.get(cid, 0.0)
        enriched[cid]["life_stage_score"] = life_sc.get(cid, 0.0)
        enriched[cid]["investor_readiness_score"] = total_sc.get(cid, 0.0)

    return enriched


def _parse_maturity(product: dict) -> date | None:
    """Parse ``type_specific.maturity`` into a date, or None if absent/invalid."""
    ts = product.get("type_specific") or {}
    raw = ts.get("maturity")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip())
    except (ValueError, TypeError):
        return None


def search_holdings_maturing(
    holdings: list[dict],
    products: list[dict],
    product_types: list[str] | None = None,
    within_days: int = 14,
    as_of_date: str | None = None,
) -> list[dict]:
    """Find bonds/FI maturing within a window (pure Logic Layer)."""
    if product_types is None:
        product_types = ["bond"]
    product_map = {p["product_id"]: p for p in products}
    ref = as_of_date or date.today().isoformat()
    ref_date = date.fromisoformat(ref)

    results: list[dict] = []
    for h in holdings:
        p = product_map.get(h["product_id"])
        if p is None:
            continue
        if p.get("product_type") not in product_types:
            continue
        maturity = _parse_maturity(p)
        if maturity is None:
            continue
        days = (maturity - ref_date).days
        if not (0 <= days <= within_days):
            continue
        results.append({
            "client_id": h["client_id"],
            "product_id": h["product_id"],
            "market_value": h.get("market_value"),
            "days_to_mature": days,
        })

    results.sort(key=lambda r: (r["days_to_mature"], -(r["market_value"] or 0)))
    return results


def _match_range(value: Any, criterion: Any) -> bool:
    """Range / exact match helper (pure)."""
    if criterion is None:
        return True
    if value is None:
        return False
    if isinstance(criterion, (list, tuple)) and len(criterion) == 2:
        lo, hi = criterion
        return (lo is None or value >= lo) and (hi is None or value <= hi)
    return value == criterion
