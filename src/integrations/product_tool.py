"""
Product Tool API — thin orchestrator (Logic Layer, no I/O).

Implements the four methods defined in:
    docs/prompts/prod_spec/tool/product_tool.md

All product data is retrieved through the Data Access Layer adapters.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.shared.product_family import get_product_family
from src.planbot.investor_readiness_score import score_concentration_risk
from src.planbot.product_scoring import (
    _build_similarity_query_from_product,
    _derive_asset_class,
    _extract_coupon,
    _extract_time_to_maturity_days,
    _get_product_expected_return,
    _parse_time_to_maturity,
    compute_concentration_risk,
    compute_similarity_score,
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


def _get_adapters():
    from src.adapters.data_adapter import build_data_adapters

    return build_data_adapters(_load_planbot_config())


def _product_scoring_config() -> dict:
    return _load_planbot_config().get("product_fitness_score", {})


# ---------------------------------------------------------------------------
# Product row helpers (kept for backward-compatible imports)
# ---------------------------------------------------------------------------

COLUMNS = [
    "product_id", "name", "ticker", "risk_rating", "expected_return",
    "product_type", "vehicle", "trading_currency", "region", "sector",
    "investment_note", "type_specific", "performance_history",
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
    LOGGER.debug("search_by_product_id input: product_id=%s", product_id)
    rows = search_by_product_ids([product_id])
    if not rows:
        LOGGER.debug("search_by_product_id output: product_id=%s found=False", product_id)
        return None
    result = rows[0]
    LOGGER.debug("search_by_product_id output: %s", result)
    return result


def search_by_product_ids(product_ids: list[str]) -> list[dict]:
    """Batch look up products by ``product_id`` in a single query.

    Returns full product dicts in the order requested (missing IDs omitted).
    """
    if not product_ids:
        return []
    _, product_adapter = _get_adapters()
    rows = product_adapter.fetch_products(list(product_ids))
    by_id = {r["product_id"]: r for r in rows}
    return [by_id[pid] for pid in product_ids if pid in by_id]


# ── 2. search_similar ─────────────────────────────────────────────────────


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
    config = _product_scoring_config()
    weights = config.get("search_similar_weights", {})
    sigmas_yaml = config.get("search_similar_sigmas", {})

    query = query or {}
    trade_date_str = query.get("trade_date", date.today().isoformat())

    LOGGER.debug("search_similar input: top_n=%s risk_rating_hard_filter=%s diversification=%s max_per_product_type=%s exclude=%s query=%s",
                 top_n, risk_rating_hard_filter, diversification, max_per_product_type, exclude_product_ids, query)

    _, product_adapter = _get_adapters()
    products = product_adapter.fetch_products()

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
        score = compute_similarity_score(
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
    response = {
        "results": [
            {
                "product_id": p["product_id"],
                "name": p["name"],
                "product_type": p["product_type"],
                "risk_rating": p["risk_rating"],
                "expected_return": p["expected_return"],
                "investment_note": p.get("investment_note"),
                "similarity_score": p["similarity_score"],
            }
            for p in result
        ],
    }
    LOGGER.debug("search_similar output: %s", response)
    return response


# ── 3. search_reinvestment_candidates ─────────────────────────────────────


def search_similar_to_product(
    product: dict,
    *,
    top_n: int = 3,
    diversification: bool = True,
    max_per_product_type: int = 2,
    risk_rating_hard_filter: bool = True,
    exclude_product_ids: list[str] | None = None,
) -> dict:
    """Find products similar to *product*, automatically excluding the anchor.

    Composes :func:`_build_similarity_query_from_product` with
    :func:`search_similar`, auto-excluding the anchor product ID.
    """
    exclude = list(exclude_product_ids or [])
    exclude.append(product["product_id"])
    return search_similar(
        query=_build_similarity_query_from_product(product),
        top_n=top_n,
        diversification=diversification,
        max_per_product_type=max_per_product_type,
        risk_rating_hard_filter=risk_rating_hard_filter,
        exclude_product_ids=exclude,
    )


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
    LOGGER.debug("search_reinvestment_candidates input: client_ids=%s source_product_id=%s max_per_product_type=%s top_n_per_client=%s risk_rating_hard_filter=%s exclude=%s",
                 client_ids, source_product_id, max_per_product_type, top_n_per_client, risk_rating_hard_filter, exclude_product_ids)
    source = search_by_product_id(source_product_id)
    if source is None:
        raise ValueError(f"Source product not found: {source_product_id}")

    results: dict[str, list] = {}
    for cid in client_ids:
        sim_result = search_similar_to_product(
            source,
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
                "name": r.get("name"),
                "product_type": r.get("product_type"),
                "investment_note": r.get("investment_note"),
                "similarity_score": r["similarity_score"],
            }
            for r in client_results
        ]

    response = {"results_by_client": results}
    LOGGER.debug("search_reinvestment_candidates output: %s", response)
    return response


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
    config = _product_scoring_config()
    weights = config.get("product_fitness_weights", {})
    params = config.get("product_fitness_params", {})

    exclude = set(exclude_dimensions or [])

    LOGGER.info(
        "PFS request: %d clients × %d products, top_n=%d, hard_filter=%s, exclude=%s",
        len(client_ids), len(product_ids), top_n, risk_rating_hard_filter,
        sorted(exclude) if exclude else "none",
    )

    client_adapter, product_adapter = _get_adapters()
    clients = client_adapter.fetch_clients(client_ids)
    products = product_adapter.fetch_products(product_ids)
    holdings = client_adapter.fetch_holdings(client_ids)

    clients_map: dict[str, dict] = {c["client_id"]: c for c in clients}
    products_map: dict[str, dict] = {p["product_id"]: p for p in products}

    # Group + normalize holdings by client, enriching with product_type
    holdings_by_client: dict[str, list[dict]] = {}
    for h in holdings:
        hh = dict(h)
        hh["market_value"] = hh.get("market_value") or 0
        hh["region"] = hh.get("region") or ""
        hh["asset_class"] = hh.get("asset_class") or ""
        p = products_map.get(hh.get("product_id"))
        hh["product_type"] = p.get("product_type", "") if p else ""
        holdings_by_client.setdefault(hh["client_id"], []).append(hh)

    # Concentration config
    conc_config = (
        _load_planbot_config().get("investor_readiness_score", {}).get(
            "score_concentration_risk", {}
        )
    )

    # Pre-compute concentration scores for all clients
    concentration_scores = score_concentration_risk(clients, holdings, conc_config) if conc_config else {}

    # --- Score every pair ---
    results: list[dict] = []

    for cid in client_ids:
        client = clients_map.get(cid)
        if client is None:
            continue

        client_rr = client.get("risk_rating")
        client_aum = float(client.get("aum") or 0)

        holdings_cid = holdings_by_client.get(cid, [])
        held_product_types = {h["product_type"] for h in holdings_cid if h["product_type"]}
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

                hypo_risk = compute_concentration_risk(
                    cid, product, holdings_cid,
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
                comparable = [h for h in holdings_cid if h["product_type"] == prod_type]

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
                "product_name": products_map.get(pid, {}).get("name"),
                "investment_note": products_map.get(pid, {}).get("investment_note"),
                "fitness_score": round(fitness, 4),
                "component_scores": comp_scores,
            })

    # Sort: descending fitness, then expected_return desc, then product_id asc
    results.sort(key=lambda x: (
        -x["fitness_score"],
        -(products_map.get(x["product_id"], {}).get("expected_return") or 0),
        x["product_id"],
    ))

    # Log per-client fitness score summary
    total_scored = len(results)
    clients_scored = len({r["client_id"] for r in results})
    LOGGER.info(
        "PFS: %d pairs scored across %d clients, top_n=%d returned",
        total_scored, clients_scored, min(top_n, total_scored),
    )
    for cid in client_ids:
        client_results = [r for r in results if r["client_id"] == cid]
        if client_results:
            top3 = client_results[:3]
            lines = [
                f"  {r['product_id']:12s} → fitness={r['fitness_score']:.2f}  "
                f"components={json.dumps(r['component_scores'])}"
                for r in top3
            ]
            LOGGER.debug("PFS client %s (top %d of %d):\n%s",
                         cid, len(top3), len(client_results), "\n".join(lines))

    results = results[:top_n]

    return {"results": results}
