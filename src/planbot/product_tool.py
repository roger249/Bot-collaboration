"""
Product Tool API — Python methods for querying products from DuckDB.

Implements the four methods defined in:
    docs/prompts/prod_spec/tool/product_tool.md

All product data lives in: data/planbot/db/planbot.duckdb
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import yaml

from src.shared.product_family import get_product_family
from src.planbot.investor_readiness_score import score_concentration_risk

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


def _load_product_scoring_config() -> dict:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return raw.get("product_fitness_score", {})


# ---------------------------------------------------------------------------
# Time-to-maturity helpers
# ---------------------------------------------------------------------------

_TIME_UNIT_TO_DAYS: dict[str, float] = {
    "d": 1.0,
    "w": 7.0,
    "m": 30.4375,  # 365.25 / 12
    "y": 365.25,
}


def _parse_time_to_maturity(raw: str) -> float | None:
    """Parse '2y', '30d', '6m' → days as float."""
    m = re.match(r"^([\d.]+)\s*([dwmy])$", raw.strip().lower())
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2)
    return value * _TIME_UNIT_TO_DAYS.get(unit, 365.25)


def _extract_time_to_maturity_days(
    product: dict, trade_date: str
) -> float | None:
    """Extract time-to-maturity in days from a product dict."""
    ts = product.get("type_specific") or {}
    product_type = product.get("product_type", "")

    if product_type == "bond":
        maturity_str = ts.get("maturity")
        if maturity_str:
            try:
                maturity_date = date.fromisoformat(maturity_str)
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


# ---------------------------------------------------------------------------
# Coupon extraction helpers
# ---------------------------------------------------------------------------

_COUPON_JSON_PATHS: dict[str, str] = {
    "bond": "$.coupon_rate",
    "bond_fund": "$.ytm",
    "equity_fund": "$.dividend_yield",
    "stock": "$.dividend_yield",
    "balanced_fund": "$.dividend_yield",
    "money_market_fund": "$.yield_type",
}


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


# ---------------------------------------------------------------------------
# Asset class derivation
# ---------------------------------------------------------------------------

_ASSET_CLASS_MAP: dict[str, str] = {
    "bond": "fixed_income",
    "bond_fund": "fixed_income",
    "equity_fund": "equity",
    "stock": "equity",
    "money_market_fund": "cash",
    "balanced_fund": "balanced",
}


def _derive_asset_class(product_type: str) -> str:
    return _ASSET_CLASS_MAP.get(product_type, product_type)


# ---------------------------------------------------------------------------
# Linear interpolation (copied from investor_readiness_score for self-contained use)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Product row helpers
# ---------------------------------------------------------------------------

COLUMNS = [
    "product_id", "name", "ticker", "risk_rating", "expected_return",
    "product_type", "vehicle", "trading_currency", "region", "sector",
    "type_specific", "performance_history",
]


def _row_to_dict(row: tuple, cols: list[str] = COLUMNS) -> dict:
    record = dict(zip(cols, row))
    for json_col in ("type_specific", "performance_history"):
        raw = record.get(json_col)
        record[json_col] = (
            json.loads(raw) if isinstance(raw, str) else (raw or {})
        )
    for k, v in record.items():
        if isinstance(v, float):
            record[k] = round(v, 4) if v is not None else None
    return record


# ═══════════════════════════════════════════════════════════════════════════
# API Methods
# ═══════════════════════════════════════════════════════════════════════════


# ── 1. search_by_product_id ────────────────────────────────────────────────


def search_by_product_id(product_id: str) -> dict | None:
    """Look up a single product by its ``product_id``."""
    conn = _get_conn(read_only=True)
    try:
        sql = f"SELECT {', '.join(COLUMNS)} FROM products WHERE product_id = ?"
        row = conn.execute(sql, [product_id]).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


# ── 2. search_similar ─────────────────────────────────────────────────────


def _compute_similarity_score(
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


def search_similar(
    query: dict | None = None,
    *,
    top_n: int = 3,
    risk_rating_hard_filter: bool = True,
    diversification: bool = True,
    max_per_product_type: int = 2,
    exclude_product_ids: list[str] | None = None,
) -> dict:
    """Proximity search returning products ranked by similarity.

    Parameters
    ----------
    query : dict
        Query attributes: risk_rating, expected_return, product_type,
        asset_class, region, sector, time_to_maturity, coupon, trade_date.
    top_n : int
        Maximum products to return (default 3).
    risk_rating_hard_filter : bool
        If True, enforce product.risk_rating <= query.risk_rating.
    diversification : bool
        If True, group by product_type and select top max_per_product_type per group.
    max_per_product_type : int
        Max products per product_type group when diversification=True.
    exclude_product_ids : list[str] | None
        Product IDs to exclude.
    """
    config = _load_product_scoring_config()
    weights = config.get("search_similar_weights", {})
    sigmas_yaml = config.get("search_similar_sigmas", {})

    query = query or {}
    trade_date_str = query.get("trade_date", date.today().isoformat())

    conn = _get_conn(read_only=True)
    try:
        # Fetch all products
        sql = f"SELECT {', '.join(COLUMNS)} FROM products"
        rows = conn.execute(sql).fetchall()
    finally:
        conn.close()

    products = [_row_to_dict(r) for r in rows]

    # Exclude
    exclude = set(exclude_product_ids or [])
    products = [p for p in products if p["product_id"] not in exclude]

    # Hard filter
    if risk_rating_hard_filter and query.get("risk_rating") is not None:
        q_rr = query["risk_rating"]
        products = [p for p in products if (p["risk_rating"] or 999) <= q_rr]

    # Compute sigmas — YAML first, fallback to population std dev
    sigmas: dict[str, float] = {}
    for dim in ("risk_rating", "expected_return", "time_to_maturity", "coupon"):
        if dim in sigmas_yaml:
            sigmas[dim] = float(sigmas_yaml[dim])
        else:
            if dim == "time_to_maturity":
                values = [
                    _extract_time_to_maturity_days(p, trade_date_str)
                    for p in products
                ]
            elif dim == "coupon":
                values = [_extract_coupon(p) for p in products]
            else:
                values = [p.get(dim) for p in products]
            values = [v for v in values if v is not None]
            if len(values) >= 2:
                mean = sum(values) / len(values)
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                sigmas[dim] = math.sqrt(variance) if variance > 0 else 1.0
            else:
                sigmas[dim] = 1.0

    # Score all products
    scored = []
    for p in products:
        score = _compute_similarity_score(
            p, query, sigmas, weights,
            risk_rating_hard_filter=False,  # already handled above
            trade_date=trade_date_str,
        )
        p["similarity_score"] = round(score, 4)
        scored.append(p)

    scored.sort(key=lambda x: x["similarity_score"], reverse=True)

    # Diversification
    if diversification:
        grouped: dict[str, list] = {}
        for p in scored:
            pt = p.get("product_type", "")
            grouped.setdefault(pt, []).append(p)
        result = []
        for pt, items in grouped.items():
            result.extend(items[:max_per_product_type])
        result.sort(key=lambda x: x["similarity_score"], reverse=True)
        result = result[:top_n]
    else:
        result = scored[:top_n]

    # Build response — minimal fields
    return {
        "results": [
            {
                "product_id": p["product_id"],
                "name": p["name"],
                "product_type": p["product_type"],
                "risk_rating": p["risk_rating"],
                "expected_return": p["expected_return"],
                "similarity_score": p["similarity_score"],
            }
            for p in result
        ],
    }


# ── 3. search_reinvestment_candidates ─────────────────────────────────────


def search_reinvestment_candidates(
    client_ids: list[str],
    source_product_id: str,
    *,
    max_per_product_type: int = 2,
    top_n_per_client: int | None = None,
    risk_rating_hard_filter: bool = True,
    exclude_product_ids: list[str] | None = None,
) -> dict:
    """Find reinvestment candidates per client using search_similar.

    Parameters
    ----------
    client_ids : list[str]
        Client IDs to generate candidates for.
    source_product_id : str
        Product ID whose attributes are used as the similarity query.
    max_per_product_type : int
        Max products per product_type group (diversification).
    top_n_per_client : int | None
        Max results per client. None = return all.
    risk_rating_hard_filter : bool
        Passed through to search_similar.
    exclude_product_ids : list[str] | None
        Passed through to search_similar.
    """
    source = search_by_product_id(source_product_id)
    if source is None:
        raise ValueError(f"Source product not found: {source_product_id}")

    # Build query from source product attributes
    query = {
        "risk_rating": source["risk_rating"],
        "expected_return": source["expected_return"],
        "product_type": source["product_type"],
        "region": source["region"],
        "sector": source["sector"],
    }
    # derive asset_class
    query["asset_class"] = _derive_asset_class(source["product_type"])

    # For bonds/bond_funds, include maturity and coupon
    pt = source.get("product_type", "")
    if pt in ("bond", "bond_fund"):
        ts = source.get("type_specific") or {}
        if pt == "bond":
            query["time_to_maturity"] = "2y"  # default; actual from client context
        else:
            dur = ts.get("effective_duration")
            if dur:
                query["time_to_maturity"] = f"{float(dur)}y"

    results: dict[str, list] = {}
    for cid in client_ids:
        # search_similar for this client with diversification already built in
        sim_result = search_similar(
            query=query,
            top_n=top_n_per_client or 9999,  # large, diversification + limit after
            risk_rating_hard_filter=risk_rating_hard_filter,
            diversification=True,
            max_per_product_type=max_per_product_type,
            exclude_product_ids=exclude_product_ids,
        )
        client_results = sim_result.get("results", [])
        if top_n_per_client:
            client_results = client_results[:top_n_per_client]
        results[cid] = [
            {
                "product_id": r["product_id"],
                "product_type": r["product_type"],
                "similarity_score": r["similarity_score"],
            }
            for r in client_results
        ]

    return {"results_by_client": results}


# ── 4. search_product_by_fitness_score ────────────────────────────────────


def search_product_by_fitness_score(
    client_ids: list[str],
    product_ids: list[str],
    *,
    top_n: int = 10,
    risk_rating_hard_filter: bool = True,
    exclude_dimensions: list[str] | None = None,
) -> dict:
    """Compute product fitness score for client×product pairs.

    Parameters
    ----------
    client_ids : list[str]
    product_ids : list[str]
    top_n : int
    risk_rating_hard_filter : bool
        Default True — enforce product.risk_rating <= client.risk_rating.
    exclude_dimensions : list[str] | None
        Dimensions to exclude. None = all 4 included.
    """
    config = _load_product_scoring_config()
    weights = config.get("product_fitness_weights", {})
    params = config.get("product_fitness_params", {})

    exclude = set(exclude_dimensions or [])

    # --- Load clients, holdings, products ---
    conn = _get_conn(read_only=True)
    try:
        # Clients
        client_rows = conn.execute(
            "SELECT client_id, name, aum, risk_rating FROM clients WHERE client_id IN ("
            + ",".join("?" for _ in client_ids) + ")",
            client_ids,
        ).fetchall()

        client_cols = ["client_id", "name", "aum", "risk_rating"]
        clients_map: dict[str, dict] = {
            r[0]: dict(zip(client_cols, r)) for r in client_rows
        }

        # Products
        prod_rows = conn.execute(
            "SELECT " + ", ".join(COLUMNS) + " FROM products WHERE product_id IN ("
            + ",".join("?" for _ in product_ids) + ")",
            product_ids,
        ).fetchall()
        products_map: dict[str, dict] = {r[0]: _row_to_dict(r) for r in prod_rows}

        # Holdings — all for these clients
        hold_rows = conn.execute(
            "SELECT client_id, product_id, market_value FROM holdings WHERE client_id IN ("
            + ",".join("?" for _ in client_ids) + ")",
            client_ids,
        ).fetchall()
        holdings_by_client: dict[str, list[dict]] = {}
        for cid, pid, mv in hold_rows:
            holdings_by_client.setdefault(cid, []).append({
                "product_id": pid,
                "market_value": mv or 0,
            })

        # Enrich holdings with product_type from products table
        all_hold_prod_ids = list({h["product_id"] for hh in holdings_by_client.values() for h in hh})
        if all_hold_prod_ids:
            prod_type_rows = conn.execute(
                "SELECT product_id, product_type FROM products WHERE product_id IN ("
                + ",".join("?" for _ in all_hold_prod_ids) + ")",
                all_hold_prod_ids,
            ).fetchall()
            prod_type_map = {r[0]: r[1] for r in prod_type_rows}
        else:
            prod_type_map = {}

        for cid in holdings_by_client:
            for h in holdings_by_client[cid]:
                h["product_type"] = prod_type_map.get(h["product_id"], "")

        # --- Concentration config ---
        conc_config_raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        conc_config = conc_config_raw.get("investor_readiness_score", {}).get(
            "score_concentration_risk", {}
        )

        # Pre-compute concentration scores for all clients (connection still open)
        concentration_scores = score_concentration_risk(conn, conc_config) if conc_config else {}

        # Also fetch holdings with asset_class/region for hypothetical calc
        hold_detail_rows = conn.execute(
            "SELECT h.client_id, h.product_id, h.market_value, h.region, h.asset_class "
            "FROM holdings h WHERE h.client_id IN ("
            + ",".join("?" for _ in client_ids) + ")",
            client_ids,
        ).fetchall()
        hold_details: dict[str, list[dict]] = {}
        for row in hold_detail_rows:
            cid, pid, mv, reg, ac = row
            hold_details.setdefault(cid, []).append({
                "product_id": pid,
                "market_value": mv or 0,
                "region": reg or "",
                "asset_class": ac or "",
            })

    finally:
        conn.close()

    # --- Score every pair ---
    results: list[dict] = []

    for cid in client_ids:
        client = clients_map.get(cid)
        if client is None:
            continue

        client_rr = client.get("risk_rating")
        client_aum = float(client.get("aum") or 0)

        holdings = holdings_by_client.get(cid, [])
        held_product_types = {h["product_type"] for h in holdings if h["product_type"]}
        held_product_families = {get_product_family(pt) for pt in held_product_types}

        for pid in product_ids:
            product = products_map.get(pid)
            if product is None:
                continue

            # Determine included dimensions
            dims = {
                "risk_rating_match_score": "risk_rating_match_score" not in exclude,
                "concentration_score": "concentration_score" not in exclude,
                "has_similar_investment_experience_score": "has_similar_investment_experience_score" not in exclude,
                "better_product_score": "better_product_score" not in exclude,
            }
            if not any(dims.values()):
                continue

            # --- Hard risk gate ---
            if risk_rating_hard_filter:
                prod_rr = product.get("risk_rating") or 99
                if client_rr is not None and prod_rr > client_rr:
                    continue  # score = 0, ranked bottom — skip

            comp_scores: dict[str, float] = {}

            # 1) risk_rating_match_score
            if dims["risk_rating_match_score"]:
                if client_rr is not None and product.get("risk_rating") is not None:
                    diff = abs(client_rr - product["risk_rating"])
                    rr_score = 10.0 * (1.0 - diff / 4.0)
                    comp_scores["risk_rating_match_score"] = round(max(0.0, min(10.0, rr_score)), 2)
                else:
                    comp_scores["risk_rating_match_score"] = 5.0  # neutral if unknown

            # 2) concentration_score
            if dims["concentration_score"]:
                conc_test_pct = float(params.get("concentration_test_position_pct_aum", 0.10))
                test_notional = conc_test_pct * client_aum

                hypo_risk = _compute_hypothetical_concentration_risk(
                    cid, product, hold_details.get(cid, []),
                    client_aum, test_notional, conc_config,
                    concentration_scores.get(cid, 5.0),
                )
                comp_scores["concentration_score"] = round(max(0.0, min(10.0, 10.0 - hypo_risk)), 2)

            # 3) has_similar_investment_experience_score
            if dims["has_similar_investment_experience_score"]:
                prod_type = product.get("product_type", "")
                prod_family = get_product_family(prod_type)

                if prod_type in held_product_types:
                    exp_score = float(params.get("experience_score_same_type", 10.0))
                elif prod_family in held_product_families:
                    exp_score = float(params.get("experience_score_same_family", 6.0))
                else:
                    exp_score = float(params.get("experience_score_none", 0.0))
                comp_scores["has_similar_investment_experience_score"] = round(exp_score, 2)

            # 4) better_product_score
            if dims["better_product_score"]:
                prod_type = product.get("product_type", "")
                candidate_er = product.get("expected_return")
                comparable = [h for h in holdings if h["product_type"] == prod_type]

                if comparable and candidate_er is not None:
                    total_mv = sum(h["market_value"] for h in comparable)
                    if total_mv > 0:
                        scale = float(params.get("better_product_score_scale", 10))
                        cap = float(params.get("better_product_score_uplift_cap", 0.30))
                        eps = float(params.get("better_product_score_eps", 0.01))

                        weighted_uplift = 0.0
                        for h in comparable:
                            weight_h = h["market_value"] / total_mv
                            er_h = _get_product_expected_return(h["product_id"], products_map)
                            if er_h is not None:
                                uplift = max((candidate_er - er_h) / max(abs(er_h), eps), 0.0)
                                weighted_uplift += weight_h * uplift

                        bp_score = scale * min(weighted_uplift / cap, 1.0)
                        comp_scores["better_product_score"] = round(max(0.0, min(10.0, bp_score)), 2)
                    else:
                        comp_scores["better_product_score"] = 0.0
                else:
                    comp_scores["better_product_score"] = 0.0

            # --- Final weighted score ---
            included_dims = [k for k, v in dims.items() if v]
            total_w = sum(weights.get(k, 0.0) for k in included_dims)
            fitness = 0.0
            if total_w > 0:
                for k in included_dims:
                    w = weights.get(k, 0.0) / total_w
                    fitness += w * comp_scores.get(k, 0.0)

            results.append({
                "client_id": cid,
                "product_id": pid,
                "fitness_score": round(fitness, 4),
                "component_scores": comp_scores,
            })

    # Sort: descending fitness, then expected_return desc, then product_id asc
    results.sort(key=lambda x: (
        -x["fitness_score"],
        -(products_map.get(x["product_id"], {}).get("expected_return") or 0),
        x["product_id"],
    ))

    results = results[:top_n]

    return {"results": results}


# ---------------------------------------------------------------------------
# Concentration helper for PFS
# ---------------------------------------------------------------------------


def _compute_hypothetical_concentration_risk(
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

    # Existing exposures
    existing_single_max = max((h["market_value"] for h in hold_details), default=0)
    new_single_max = max(existing_single_max, test_notional)
    new_single_pct = new_single_max / aum
    s_single = _linear_interpolate(new_single_pct, single_pivot)

    # Region exposure
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

    # Asset class exposure
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


def _get_product_expected_return(
    product_id: str, products_map: dict[str, dict]
) -> float | None:
    """Helper to get expected_return, checking both the products_map cache and DB."""
    if product_id in products_map:
        return products_map[product_id].get("expected_return")
    # fallback: try DB
    prod = search_by_product_id(product_id)
    if prod:
        products_map[product_id] = prod
        return prod.get("expected_return")
    return None
