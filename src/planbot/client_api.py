"""
Client API — Python methods for querying client data from the unified DuckDB.

Implements the four methods defined in:
    docs/prompts/prod_spec/tool/client_tool.md

All data lives in a single DuckDB: data/planbot/db/planbot.duckdb
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import yaml

from src.planbot.investor_readiness_score import (
    score_cash_drag,
    score_concentration_risk,
    score_active_manage,
    score_life_stage,
    compute_total_scores,
    run_score_card,
)

LOGGER = logging.getLogger(__name__)

DB_PATH = Path("data/planbot/db/planbot.duckdb")
CONFIG_PATH = Path("config/config_planbot.yaml")

# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------


def _get_conn(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Shared DuckDB not found at {DB_PATH}. "
            "Run investor_readiness_score.py and product_catalog_seed.py first."
        )
    conn = duckdb.connect(str(DB_PATH), read_only=read_only)
    conn.execute("PRAGMA enable_progress_bar=false;")
    return conn


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _load_score_config() -> dict:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return raw.get("investor_readiness_score", {})


_CATEGORY_MAP: dict[str, str] = {
    "bond": "bond",
    "bond_fund": "bond",
    "equity_fund": "equity",
    "stock": "equity",
    "money_market_fund": "cash",
    "balanced_fund": "balanced",
}


# ---------------------------------------------------------------------------
# Derived field computation
# ---------------------------------------------------------------------------


def _compute_derived_fields(conn: duckdb.DuckDBPyConnection) -> dict[str, dict[str, Any]]:
    """Pre-compute all derived fields for every client."""
    score_config = _load_score_config()

    rows = conn.execute("""
        SELECT c.client_id, c.name, c.aum, c.cash_pct, c.region,
               p.birthdate, p.occupation, p.risk_rating, p.marital_status,
               p.children_info
        FROM clients c
        LEFT JOIN profiles p ON c.name = p.client_name
    """).fetchall()

    cols = ["client_id", "name", "aum", "cash_pct", "region",
            "birthdate", "occupation", "risk_rating", "marital_status", "children_info"]
    clients: dict[str, dict] = {row[0]: dict(zip(cols, row)) for row in rows}

    today = date.today()
    for c in clients.values():
        bd = c.get("birthdate")
        if not bd or str(bd).upper() in ("N/A", ""):
            c["age"] = None
        else:
            try:
                parts = str(bd).strip().split("-")
                bdate = date(int(parts[0]), int(parts[1]), int(parts[2]))
                c["age"] = today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
            except (ValueError, IndexError):
                c["age"] = None

    # has_fund
    hf = conn.execute("""
        SELECT DISTINCT h.client_id
        FROM holdings h JOIN products p ON h.product_id = p.product_id
        WHERE p.product_type != 'money_market_fund'
    """).fetchall()
    hf_set = {r[0] for r in hf}
    for cid, c in clients.items():
        c["has_fund"] = cid in hf_set

    # product_types_in_holdings
    ptr = conn.execute("""
        SELECT h.client_id, p.product_type
        FROM holdings h JOIN products p ON h.product_id = p.product_id
    """).fetchall()
    pt_map: dict[str, set] = {}
    for cid, pt in ptr:
        pt_map.setdefault(cid, set()).add(pt)
    for cid, c in clients.items():
        pts = pt_map.get(cid, set())
        c["product_types_in_holdings"] = sorted(pts)
        c["product_types_in_holdings_categories"] = sorted({_CATEGORY_MAP.get(p, p) for p in pts})

    # cash_pct
    cpr = conn.execute("""
        SELECT c.client_id, c.cash_pct,
               COALESCE(SUM(CASE WHEN h.asset_class='Cash' THEN h.market_value ELSE 0 END),0)
        FROM clients c LEFT JOIN holdings h ON c.client_id = h.client_id
        GROUP BY c.client_id, c.aum, c.cash_pct
    """).fetchall()
    for cid, raw_cp, mmf in cpr:
        aum = clients.get(cid, {}).get("aum", 0)
        if aum and aum > 0:
            mmf_pct = (mmf / aum) * 100 if mmf else 0
            clients[cid]["cash_pct_computed"] = round(max(raw_cp or 0, mmf_pct), 2)
        else:
            clients[cid]["cash_pct_computed"] = 0.0

    # Scores from investor_readiness_score module
    cash_sc = score_cash_drag(conn, score_config.get("score_cash_drag", {}))
    conc_sc = score_concentration_risk(conn, score_config.get("score_concentration_risk", {}))
    act_sc = score_active_manage(conn, score_config.get("score_active_manage", {}))
    life_sc = score_life_stage(conn, score_config.get("score_life_stage", {}))
    total_sc = {s.client_id: s.total_score for s in compute_total_scores(conn, score_config)}

    for cid in clients:
        clients[cid]["cash_score"] = cash_sc.get(cid, 0.0)
        clients[cid]["concentration_score"] = conc_sc.get(cid, 0.0)
        clients[cid]["active_score"] = act_sc.get(cid, 0.0)
        clients[cid]["life_stage_score"] = life_sc.get(cid, 0.0)
        clients[cid]["investor_readiness_score"] = total_sc.get(cid, 0.0)

    return clients


def _enrich_holdings(conn: duckdb.DuckDBPyConnection, client_id: str) -> list[dict]:
    rows = conn.execute("""
        SELECT holding_idx, holding_id, product_id, instrument_name, symbol,
               asset_class, region, currency, quantity, book_cost, market_value,
               unrealized_pl, unrealized_pl_pct, yield_pct, risk_bucket, esg_score, liquidity
        FROM holdings WHERE client_id = ? ORDER BY holding_idx
    """, [client_id]).fetchall()

    return [
        {
            "holding_idx": r[0], "holding_id": r[1], "product_id": r[2],
            "instrument_name": r[3], "symbol": r[4], "asset_class": r[5],
            "region": r[6], "currency": r[7], "quantity": r[8],
            "book_cost": r[9], "market_value": r[10], "unrealized_pl": r[11],
            "unrealized_pl_pct": r[12], "yield_pct": r[13],
            "risk_bucket": r[14], "esg_score": r[15], "liquidity": r[16],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# API Methods
# ---------------------------------------------------------------------------


def search_by_id(client_id: str) -> dict | None:
    """Return full client profile with nested holdings."""
    conn = _get_conn(read_only=True)
    try:
        row = conn.execute("""
            SELECT c.client_id, c.name, c.aum, c.cash_pct, c.region,
                   p.birthdate, p.occupation, p.risk_rating, p.marital_status,
                   p.children_info
            FROM clients c LEFT JOIN profiles p ON c.name = p.client_name
            WHERE c.client_id = ?
        """, [client_id]).fetchone()
        if row is None:
            return None

        cols = ["client_id", "name", "aum", "cash_pct", "region",
                "birthdate", "occupation", "risk_rating", "marital_status", "children_info"]
        client = dict(zip(cols, row))

        derived = _compute_derived_fields(conn)
        cid = client["client_id"]
        if cid in derived:
            for k, v in derived[cid].items():
                if k not in client:
                    client[k] = v

        client["holdings"] = _enrich_holdings(conn, cid)
        return client
    finally:
        conn.close()


def search(**criteria: Any) -> list[dict]:
    """Filter clients by demographic and portfolio criteria.

    Parameters (all optional except risk_rating):
        risk_rating: int or [min, max]
        age: int or [min, max]
        product_types_in_holdings: str or [str] — category values
        concentration_score: float or [min, max]
        cash_score: float or [min, max]
    """
    conn = _get_conn(read_only=True)
    try:
        all_clients = _compute_derived_fields(conn)

        results = []
        for cid, c in all_clients.items():
            if not _match_range(c.get("risk_rating"), criteria.get("risk_rating")):
                continue
            if "age" in criteria and criteria["age"] is not None:
                if not _match_range(c.get("age"), criteria["age"]):
                    continue
            if "product_types_in_holdings" in criteria and criteria["product_types_in_holdings"] is not None:
                cats = set(c.get("product_types_in_holdings_categories", []))
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
        return results
    finally:
        conn.close()


def search_holdings_maturing(
    product_types: list[str] | None = None,
    within_days: int = 14,
    as_of_date: str | None = None,
) -> list[dict]:
    """Find bonds/FI maturing within a given window.

    Joins holdings → products, extracts $.maturity from type_specific JSON.
    """
    conn = _get_conn(read_only=True)
    try:
        if product_types is None:
            product_types = ["bond"]
        ref = as_of_date or date.today().isoformat()
        ph = ",".join("?" for _ in product_types)

        query = f"""
            SELECT h.client_id, h.product_id, h.market_value,
                   DATEDIFF('day', CAST(? AS DATE),
                     CAST(json_extract_string(p.type_specific, '$.maturity') AS DATE))
            FROM holdings h JOIN products p ON h.product_id = p.product_id
            WHERE p.product_type IN ({ph})
              AND json_extract_string(p.type_specific, '$.maturity') IS NOT NULL
              AND CAST(json_extract_string(p.type_specific, '$.maturity') AS DATE)
                  BETWEEN CAST(? AS DATE) AND CAST(? AS DATE) + INTERVAL ? DAY
            ORDER BY 4 ASC
        """
        params = [ref] + list(product_types) + [ref, ref, within_days]
        rows = conn.execute(query, params).fetchall()

        return [{"client_id": r[0], "product_id": r[1], "notional": r[2], "days_to_mature": r[3]} for r in rows]
    finally:
        conn.close()


def search_by_investor_readiness_score(top_n: int | None = None) -> list[dict]:
    """Return clients ranked by investor readiness score."""
    scores = run_score_card()
    if top_n is not None and top_n > 0:
        scores = scores[:top_n]

    return [
        {
            "rank": i, "client_id": s.client_id, "name": s.name,
            "total_score": s.total_score, "s_cash": s.s_cash,
            "s_concentration": s.s_concentration, "s_active": s.s_active,
            "s_lifestage": s.s_lifestage,
        }
        for i, s in enumerate(scores, 1)
    ]


def _match_range(value: Any, criterion: Any) -> bool:
    if criterion is None:
        return True
    if value is None:
        return False
    if isinstance(criterion, (list, tuple)) and len(criterion) == 2:
        lo, hi = criterion
        return (lo is None or value >= lo) and (hi is None or value <= hi)
    return value == criterion