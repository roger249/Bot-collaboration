"""
Investor Readiness Score Card

Screens the entire client pool to rank clients who most urgently need a transaction
due to structural portfolio anomalies (cash drag, concentration, etc.).

Usage:
    .venv/bin/python -m src.planbot.investor_readiness_score

Config is read from config/config_planbot.yaml → investor_readiness_score section.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import yaml

from src.test_data.client_seed import (
    CLIENT_DB_PATH,
    get_client_db_conn,
    init_client_db,
)

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score interpolation helper
# ---------------------------------------------------------------------------


def _linear_interpolate(x: float, pivot: dict[float, float]) -> float:
    """Linearly interpolate x against pivot points {k: v}. Flat extrapolation."""
    sorted_keys = sorted(pivot.keys())
    if not sorted_keys:
        return 0.0

    if x <= sorted_keys[0]:
        return float(pivot[sorted_keys[0]])
    if x >= sorted_keys[-1]:
        return float(pivot[sorted_keys[-1]])

    for i in range(len(sorted_keys) - 1):
        k0, k1 = sorted_keys[i], sorted_keys[i + 1]
        if k0 <= x <= k1:
            v0, v1 = float(pivot[k0]), float(pivot[k1])
            if k1 - k0 == 0:
                return v0
            return v0 + (v1 - v0) * (x - k0) / (k1 - k0)

    return 0.0


# ---------------------------------------------------------------------------
# Dimension scoring
# ---------------------------------------------------------------------------


def score_cash_drag(
    clients: list[dict], holdings: list[dict], config: dict
) -> dict[str, float]:
    """Score each client on cash drag.

    k_cash = (cash_pct + MMF pct) / 100, then interpolated through pivot.
    MMF holdings are those in Cash asset class (Money Market Funds).
    Returns {client_id: score_0_10}.
    """
    weight = float(config.get("weight", 1))
    pivot = {float(k): float(v) for k, v in config.get("pivot", {}).items()}

    # Sum Cash-class market value per client.
    mmf_by_client: dict[str, float] = {}
    for h in holdings:
        if h.get("asset_class") == "Cash":
            mmf_by_client[h["client_id"]] = mmf_by_client.get(h["client_id"], 0.0) + (h.get("market_value") or 0.0)

    scores: dict[str, float] = {}
    for c in clients:
        client_id = c["client_id"]
        aum = c.get("aum") or 0
        cash_pct = c.get("cash_pct") or 0
        mmf_value = mmf_by_client.get(client_id, 0.0)

        if aum and aum > 0:
            mmf_pct = (mmf_value / aum) * 100 if mmf_value else 0
            # cash_pct already includes some cash; MMF is additionally in Cash asset class.
            # Use the larger of the two to avoid double-counting (cash_pct may subsume MMF).
            effective_cash_pct = max(cash_pct, mmf_pct)
            k_cash = effective_cash_pct / 100.0
        else:
            k_cash = 0.0

        s_cash = _linear_interpolate(k_cash, pivot)
        scores[client_id] = round(s_cash, 2)

    return scores


def score_concentration_risk(
    clients: list[dict], holdings: list[dict], config: dict
) -> dict[str, float]:
    """Score each client on concentration risk.

    k_concentration = max( single_holding_pct, region_pct, asset_class_pct )
    each sub-dimension interpolated via its own pivot.

    Returns {client_id: score_0_10}.
    """
    weight = float(config.get("weight", 1))
    single_pivot = {
        float(k): float(v) for k, v in config.get("s_single_holding", {}).items()
    }
    region_pivot = {
        float(k): float(v) for k, v in config.get("s_region_exposure", {}).items()
    }
    asset_pivot = {
        float(k): float(v) for k, v in config.get("s_asset_class_exposure", {}).items()
    }

    client_aum = {c["client_id"]: c["aum"] for c in clients if c.get("aum") and c["aum"] > 0}

    # Single holding exposure
    single_max: dict[str, float] = {}
    for h in holdings:
        mv = h.get("market_value")
        if mv is None:
            continue
        cid = h["client_id"]
        if cid not in single_max or mv > single_max[cid]:
            single_max[cid] = mv
    single_exposure: dict[str, float] = {}
    for client_id, max_mv in single_max.items():
        aum = client_aum.get(client_id, 0)
        single_exposure[client_id] = (max_mv / aum) if aum > 0 else 0.0

    # Region exposure
    region_by_client: dict[str, dict[str, float]] = {}
    for h in holdings:
        mv = h.get("market_value")
        region = h.get("region")
        if mv is None or region is None or region == "":
            continue
        bucket = region_by_client.setdefault(h["client_id"], {})
        bucket[region] = bucket.get(region, 0.0) + mv
    region_exposure: dict[str, float] = {}
    for client_id, regions in region_by_client.items():
        aum = client_aum.get(client_id, 0)
        max_pct = max(v / aum for v in regions.values()) if aum > 0 else 0.0
        region_exposure[client_id] = max_pct

    # Asset class exposure
    asset_by_client: dict[str, dict[str, float]] = {}
    for h in holdings:
        mv = h.get("market_value")
        asset_class = h.get("asset_class")
        if mv is None or asset_class is None or asset_class == "":
            continue
        bucket = asset_by_client.setdefault(h["client_id"], {})
        bucket[asset_class] = bucket.get(asset_class, 0.0) + mv
    asset_exposure: dict[str, float] = {}
    for client_id, assets in asset_by_client.items():
        aum = client_aum.get(client_id, 0)
        max_pct = max(v / aum for v in assets.values()) if aum > 0 else 0.0
        asset_exposure[client_id] = max_pct

    # Compute concentration score per client: max of three interpolated sub-scores
    all_client_ids = set(client_aum.keys())
    scores: dict[str, float] = {}
    for cid in all_client_ids:
        s_single = _linear_interpolate(single_exposure.get(cid, 0), single_pivot)
        s_region = _linear_interpolate(region_exposure.get(cid, 0), region_pivot)
        s_asset = _linear_interpolate(asset_exposure.get(cid, 0), asset_pivot)
        scores[cid] = round(max(s_single, s_region, s_asset), 2)

    return scores


def score_active_manage(
    clients: list[dict], holdings: list[dict], config: dict
) -> dict[str, float]:
    """Score each client on investment experience.

    has_fund = 3 if client holds any Stock/ETF/MF (non-Cash asset class),
    else 0.  s_active scales 0-10.
    (number_of_trading_ttm is not yet available in client data.)

    Returns {client_id: score_0_10}.
    """
    weight = float(config.get("weight", 1))
    has_fund_score = float(config.get("has_fund", 3))

    scores: dict[str, float] = {}
    for h in holdings:
        cid = h["client_id"]
        asset_class = h.get("asset_class")
        if asset_class is not None and asset_class != "Cash":
            scores[cid] = round(has_fund_score, 2)
        elif cid not in scores:
            scores[cid] = 0.0

    # Also include clients with no holdings at all
    for c in clients:
        cid = c["client_id"]
        if cid not in scores:
            scores[cid] = 0.0

    return scores


def score_life_stage(
    clients: list[dict], config: dict
) -> dict[str, float]:
    """Score each client on life stage.

    Uses age interpolated through pivot.
    Reads birthdate directly from the unified clients table.

    Returns {client_id: score_0_10}.
    """
    from datetime import date

    weight = float(config.get("weight", 1))
    pivot = {float(k): float(v) for k, v in config.get("pivot", {}).items()}

    today = date.today()

    scores: dict[str, float] = {}
    for c in clients:
        client_id = c["client_id"]
        birthdate_str = c.get("birthdate")
        if not birthdate_str or str(birthdate_str).upper() in ("N/A", ""):
            scores[client_id] = 0.0
            continue

        try:
            parts = str(birthdate_str).strip().split("-")
            if len(parts) < 3:
                scores[client_id] = 0.0
                continue
            bd = date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            scores[client_id] = 0.0
            continue

        age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        s_life = _linear_interpolate(float(age), pivot)
        scores[client_id] = round(s_life, 2)

    return scores


# ---------------------------------------------------------------------------
# Scoring orchestrator
# ---------------------------------------------------------------------------


@dataclass
class ClientScore:
    client_id: str
    name: str
    total_score: float
    s_cash: float
    s_concentration: float
    s_active: float
    s_lifestage: float


def compute_total_scores(
    clients: list[dict], holdings: list[dict], config: dict
) -> list[ClientScore]:
    """Compute weighted total score for all clients. Returns ranked list."""

    # Weights
    w_cash = float(
        config.get("score_cash_drag", {}).get("weight", 1)
    )
    w_concentration = float(
        config.get("score_concentration_risk", {}).get("weight", 1)
    )
    w_active = float(
        config.get("score_active_manage", {}).get("weight", 1)
    )
    w_lifestage = float(
        config.get("score_life_stage", {}).get("weight", 1)
    )

    # Per-dimension scores
    cash_scores = score_cash_drag(clients, holdings, config.get("score_cash_drag", {}))
    conc_scores = score_concentration_risk(clients, holdings, config.get("score_concentration_risk", {}))
    active_scores = score_active_manage(clients, holdings, config.get("score_active_manage", {}))
    life_scores = score_life_stage(clients, config.get("score_life_stage", {}))

    results: list[ClientScore] = []
    for c in clients:
        client_id = c["client_id"]
        name = c.get("name")
        s_cash = cash_scores.get(client_id, 0)
        s_conc = conc_scores.get(client_id, 0)
        s_active = active_scores.get(client_id, 0)
        s_life = life_scores.get(client_id, 0)

        total = (
            w_cash * s_cash
            + w_concentration * s_conc
            + w_active * s_active
            + w_lifestage * s_life
        )

        results.append(
            ClientScore(
                client_id=client_id,
                name=name,
                total_score=round(total, 2),
                s_cash=s_cash,
                s_concentration=s_conc,
                s_active=s_active,
                s_lifestage=s_life,
            )
        )

    results.sort(key=lambda x: x.total_score, reverse=True)
    return results


def export_csv(scores: list[ClientScore], output_path: Path) -> None:
    """Write ranked scores to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "client_id",
                "name",
                "total_score",
                "s_cash",
                "s_concentration",
                "s_active",
                "s_lifestage",
            ],
        )
        writer.writeheader()
        for rank, s in enumerate(scores, 1):
            writer.writerow(
                {
                    "rank": rank,
                    "client_id": s.client_id,
                    "name": s.name,
                    "total_score": s.total_score,
                    "s_cash": s.s_cash,
                    "s_concentration": s.s_concentration,
                    "s_active": s.s_active,
                    "s_lifestage": s.s_lifestage,
                }
            )
    LOGGER.info("Exported %d client scores to %s", len(scores), output_path)


def _fetch_table_as_dicts(conn: duckdb.DuckDBPyConnection, table: str) -> list[dict]:
    """Fetch a full table as a list of dicts (seeder/CLI helper)."""
    cursor = conn.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def run_score_card(
    config_path: str | Path = "config/config_planbot.yaml",
) -> list[ClientScore]:
    """Main entry point: initialise DB, compute scores, export CSV.

    Returns the ranked list of ClientScore for programmatic use.
    """
    config_path = Path(config_path).resolve()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    score_config = raw.get("investor_readiness_score")

    if not score_config:
        raise ValueError(
            "Missing 'investor_readiness_score' section in config_planbot.yaml. "
            "Please add the section as documented in the spec."
        )

    output_cfg = score_config.get("output", {})
    output_csv = Path(
        output_cfg.get("file", "runs/investor_readiness_score/scores.csv")
    )
    db_path = output_cfg.get("duckdb", str(CLIENT_DB_PATH))
    # Override module-level path if config specifies a different duckdb
    if db_path:
        import src.planbot.investor_readiness_score as mod

        mod.CLIENT_DB_PATH = Path(db_path)

    if _db_has_data():
        # DB already populated — use read-only to avoid lock conflicts
        conn = duckdb.connect(str(CLIENT_DB_PATH), read_only=True)
        try:
            clients = _fetch_table_as_dicts(conn, "clients")
            holdings = _fetch_table_as_dicts(conn, "holdings")
            return compute_total_scores(clients, holdings, score_config)
        finally:
            conn.close()

    # First run or rebuild — needs write access
    conn = get_client_db_conn(read_only=False)
    try:
        init_client_db(conn)
        clients = _fetch_table_as_dicts(conn, "clients")
        holdings = _fetch_table_as_dicts(conn, "holdings")
        scores = compute_total_scores(clients, holdings, score_config)
        export_csv(scores, output_csv)
        return scores
    finally:
        conn.close()


def _db_has_data() -> bool:
    """Return True if the DuckDB already has client data loaded."""
    try:
        conn = duckdb.connect(str(CLIENT_DB_PATH), read_only=True)
        try:
            count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            return count > 0
        finally:
            conn.close()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    from src.shared.logging_utils import init_logging
    init_logging()

    config_arg = sys.argv[1] if len(sys.argv) > 1 else "config/config_planbot.yaml"
    results = run_score_card(config_arg)

    # Print summary table
    print()
    print(f"{'Rank':<5} {'Client ID':<18} {'Name':<25} {'Total':>7} {'Cash':>7} {'Conc':>7} {'Active':>7} {'Life':>7}")
    print("-" * 85)
    for i, s in enumerate(results, 1):
        print(
            f"{i:<5} {s.client_id:<18} {s.name:<25} {s.total_score:>7.2f} "
            f"{s.s_cash:>7.2f} {s.s_concentration:>7.2f} {s.s_active:>7.2f} {s.s_lifestage:>7.2f}"
        )