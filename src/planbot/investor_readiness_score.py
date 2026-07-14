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
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import yaml

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DuckDB helpers
# ---------------------------------------------------------------------------

CLIENT_DB_PATH = Path("data/planbot/db/planbot.duckdb")
CLIENT_LIST_CSV = Path("data/planbot/shared/client_profile/client_list.csv")
CLIENT_PROFILE_CSV = Path("data/planbot/shared/client_profile/client_profile.csv")

DDL_CLIENTS = """
CREATE TABLE IF NOT EXISTS clients (
    client_id         TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    aum               DOUBLE,
    cash_pct          DOUBLE,
    region            TEXT,
    birthdate         TEXT,
    occupation        TEXT,
    risk_rating       INTEGER,
    marital_status    TEXT,
    children_info     TEXT,
    liquidity_need    TEXT,
    income_stability  TEXT,
    investment_objective TEXT
);
"""

DDL_HOLDINGS = """
CREATE TABLE IF NOT EXISTS holdings (
    client_id    TEXT NOT NULL,
    holding_idx  INTEGER NOT NULL,
    holding_id   TEXT,
    product_id   TEXT,
    instrument_name TEXT,
    symbol       TEXT,
    asset_class  TEXT,
    region       TEXT,
    currency     TEXT,
    quantity     DOUBLE,
    book_cost    DOUBLE,
    market_value DOUBLE,
    unrealized_pl DOUBLE,
    unrealized_pl_pct DOUBLE,
    yield_pct    DOUBLE,
    risk_bucket  TEXT,
    esg_score    TEXT,
    liquidity    TEXT,
    PRIMARY KEY (client_id, holding_idx)
);
"""


def get_client_db_conn(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection to the client database."""
    CLIENT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(CLIENT_DB_PATH), read_only=read_only)
    conn.execute("PRAGMA enable_progress_bar=false;")
    return conn


def _parse_float(val: str | None) -> float | None:
    """Parse a string to float, returning None for empty/missing values."""
    if val is None:
        return None
    stripped = val.strip()
    if stripped == "" or stripped.lower() == "n/a":
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _parse_int(val: str | None) -> int | None:
    """Parse a string to int, returning None for empty/missing values."""
    if val is None:
        return None
    stripped = val.strip()
    if stripped == "" or stripped.lower() == "n/a":
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def init_client_db(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all client tables and populate from CSV sources."""
    conn.execute(DDL_CLIENTS)
    conn.execute(DDL_HOLDINGS)

    # Clear existing data for idempotent rebuild
    conn.execute("DELETE FROM holdings")
    conn.execute("DELETE FROM clients")

    # -------------------------------------------------------------------
    # Load client_list.csv (wide-format: one row per client with nested holdings)
    # -------------------------------------------------------------------
    with open(CLIENT_LIST_CSV, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            client_id = row.get("client/id", "").strip()
            name = row.get("client/name", "").strip()
            aum = _parse_float(row.get("client/aum"))
            cash_pct = _parse_float(row.get("client/cashPercentage"))
            region = row.get("client/region", "").strip()

            if not client_id:
                continue

            conn.execute(
                "INSERT OR REPLACE INTO clients VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    client_id, name, aum, cash_pct, region,
                    None, None, None, None, None,  # birthdate, occupation, risk_rating, marital_status, children_info
                    None, None, None,              # liquidity_need, income_stability, investment_objective
                ],
            )

            # Unpivot holdings (up to 10 per client: holdings/0 … holdings/9)
            for idx in range(10):
                prefix = f"holdings/{idx}/"
                holding_id = row.get(f"{prefix}id", "").strip()
                if not holding_id:
                    continue  # No holding at this index

                conn.execute(
                    """INSERT OR REPLACE INTO holdings VALUES
                       (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        client_id,
                        idx,
                        holding_id,
                        row.get(f"{prefix}productId", "").strip(),
                        row.get(f"{prefix}instrumentName", "").strip(),
                        row.get(f"{prefix}symbol", "").strip(),
                        row.get(f"{prefix}assetClass", "").strip(),
                        row.get(f"{prefix}region", "").strip(),
                        row.get(f"{prefix}currency", "").strip(),
                        _parse_float(row.get(f"{prefix}quantity")),
                        _parse_float(row.get(f"{prefix}bookCost")),
                        _parse_float(row.get(f"{prefix}marketValue")),
                        _parse_float(row.get(f"{prefix}unrealizedPL")),
                        _parse_float(row.get(f"{prefix}unrealizedPLPercent")),
                        _parse_float(row.get(f"{prefix}yield")),
                        row.get(f"{prefix}riskBucket", "").strip(),
                        row.get(f"{prefix}esgScore", "").strip() or None,
                        row.get(f"{prefix}liquidity", "").strip(),
                    ],
                )

    # -------------------------------------------------------------------
    # Load client_profile.csv and UPDATE existing clients by name
    # -------------------------------------------------------------------
    with open(CLIENT_PROFILE_CSV, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            client_name = row.get("Client Name", "").strip()
            if not client_name:
                continue

            conn.execute(
                """UPDATE clients SET
                    birthdate = ?,
                    occupation = ?,
                    risk_rating = ?,
                    marital_status = ?,
                    children_info = ?,
                    liquidity_need = ?,
                    income_stability = ?,
                    investment_objective = ?
                 WHERE name = ?""",
                [
                    row.get("Birthdate", "").strip(),
                    row.get("Occupation", "").strip(),
                    _parse_int(row.get("Risk Rating")),
                    row.get("Marital Status", "").strip(),
                    row.get("Children Info", "").strip(),
                    row.get("Liquidity Need", "").strip(),
                    row.get("Income Stability", "").strip(),
                    row.get("Investment Objective", "").strip(),
                    client_name,
                ],
            )

    LOGGER.info(
        "Client DB initialised: %s clients, %s holdings",
        conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0],
    )

    # Normalize holdings.product_id to match products.product_id via ticker lookup
    _normalize_holdings_product_ids(conn)


# ---------------------------------------------------------------------------
# Product ID normalization
# ---------------------------------------------------------------------------

# Known market suffixes in holdings productId values from the source CSV.
# e.g. 'aapl-o' → base ticker 'AAPL' → product 'STOCK-AAPL'
_MARKET_SUFFIXES = ["-O", "-K", "-HK", "-RR", "-X"]


def _normalize_holdings_product_ids(conn: duckdb.DuckDBPyConnection) -> None:
    """Update holdings.product_id to match the actual products.product_id.

    Source CSV productId values are ticker+market-suffix (e.g. 'aapl-o'),
    while the product catalog uses 'ETF-{TICKER}' or 'STOCK-{TICKER}'.
    This function resolves holdings → products FK by stripping the market
    suffix and matching on the products.ticker column.
    """
    # Only normalize if products table exists and has data
    product_count = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_name='products'"
    ).fetchone()[0]
    if product_count == 0:
        LOGGER.info("Products table not found — skipping product_id normalization")
        return

    actual_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if actual_count == 0:
        LOGGER.info("Products table is empty — skipping product_id normalization")
        return

    # Build ticker → product_id map from products table
    product_rows = conn.execute(
        "SELECT product_id, ticker FROM products WHERE ticker IS NOT NULL AND ticker != ''"
    ).fetchall()
    ticker_to_pid: dict[str, str] = {}
    for pid, ticker in product_rows:
        ticker_to_pid[ticker.upper().strip()] = pid

    # Fetch all holdings to normalize
    holdings_rows = conn.execute(
        "SELECT client_id, holding_idx, product_id FROM holdings"
    ).fetchall()

    updates: list[tuple[str, int, str]] = []  # (new_pid, client_id, holding_idx)
    unmatched: set[str] = set()
    matched_count = 0

    for client_id, holding_idx, source_pid in holdings_rows:
        if not source_pid:
            continue
        upper = source_pid.upper().strip()
        new_pid = None

        # 1) Direct ticker match (case-insensitive)
        if upper in ticker_to_pid:
            new_pid = ticker_to_pid[upper]
        else:
            # 2) Strip known market suffix and try again
            for suffix in _MARKET_SUFFIXES:
                if upper.endswith(suffix):
                    base = upper[: -len(suffix)]
                    if base in ticker_to_pid:
                        new_pid = ticker_to_pid[base]
                    break

        if new_pid:
            if new_pid != source_pid:
                updates.append((new_pid, client_id, holding_idx))
            matched_count += 1
        else:
            unmatched.add(source_pid)

    # Apply updates
    for new_pid, client_id, holding_idx in updates:
        conn.execute(
            "UPDATE holdings SET product_id = ? WHERE client_id = ? AND holding_idx = ?",
            [new_pid, client_id, holding_idx],
        )

    LOGGER.info(
        "Product ID normalization: %d matched, %d updated, %d unmatched (%s)",
        matched_count,
        len(updates),
        len(unmatched),
        ", ".join(sorted(unmatched)) if unmatched else "none",
    )


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


def score_cash_drag(conn: duckdb.DuckDBPyConnection, config: dict) -> dict[str, float]:
    """Score each client on cash drag.

    k_cash = (cash_pct + MMF pct) / 100, then interpolated through pivot.
    MMF holdings are those in Cash asset class (Money Market Funds).
    Returns {client_id: score_0_10}.
    """
    weight = float(config.get("weight", 1))
    pivot = {float(k): float(v) for k, v in config.get("pivot", {}).items()}

    # Compute effective cash %: reported cash_pct + market value of Cash-class holdings / aum
    rows = conn.execute("""
        SELECT
            c.client_id,
            c.aum,
            c.cash_pct,
            COALESCE(SUM(CASE WHEN h.asset_class = 'Cash' THEN h.market_value ELSE 0 END), 0) AS mmf_value
        FROM clients c
        LEFT JOIN holdings h ON c.client_id = h.client_id
        GROUP BY c.client_id, c.aum, c.cash_pct
    """).fetchall()

    scores: dict[str, float] = {}
    for client_id, aum, cash_pct, mmf_value in rows:
        if aum and aum > 0:
            mmf_pct = (mmf_value / aum) * 100 if mmf_value else 0
            # cash_pct already includes some cash; MMF is additionally in Cash asset class.
            # Use the larger of the two to avoid double-counting (cash_pct may subsume MMF).
            effective_cash_pct = max(cash_pct or 0, mmf_pct)
            k_cash = effective_cash_pct / 100.0
        else:
            k_cash = 0.0

        s_cash = _linear_interpolate(k_cash, pivot)
        scores[client_id] = round(s_cash, 2)

    return scores


def score_concentration_risk(
    conn: duckdb.DuckDBPyConnection, config: dict
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

    # Per-client: single holding max, region max, asset class max
    rows = conn.execute("""
        SELECT c.client_id, c.aum
        FROM clients c
    """).fetchall()

    client_aum = {row[0]: row[1] for row in rows if row[1] and row[1] > 0}

    # Single holding exposure
    single_rows = conn.execute("""
        SELECT client_id, MAX(market_value) AS max_mv
        FROM holdings
        WHERE market_value IS NOT NULL
        GROUP BY client_id
    """).fetchall()

    single_exposure: dict[str, float] = {}
    for client_id, max_mv in single_rows:
        aum = client_aum.get(client_id, 0)
        single_exposure[client_id] = (max_mv / aum) if aum > 0 else 0.0

    # Region exposure
    region_rows = conn.execute("""
        SELECT client_id, region,
               SUM(market_value) AS total_mv
        FROM holdings
        WHERE market_value IS NOT NULL AND region IS NOT NULL AND region != ''
        GROUP BY client_id, region
    """).fetchall()

    region_by_client: dict[str, dict[str, float]] = {}
    for client_id, region, total_mv in region_rows:
        region_by_client.setdefault(client_id, {})[region] = total_mv

    region_exposure: dict[str, float] = {}
    for client_id, regions in region_by_client.items():
        aum = client_aum.get(client_id, 0)
        max_pct = max(v / aum for v in regions.values()) if aum > 0 else 0.0
        region_exposure[client_id] = max_pct

    # Asset class exposure
    asset_rows = conn.execute("""
        SELECT client_id, asset_class,
               SUM(market_value) AS total_mv
        FROM holdings
        WHERE market_value IS NOT NULL AND asset_class IS NOT NULL AND asset_class != ''
        GROUP BY client_id, asset_class
    """).fetchall()

    asset_by_client: dict[str, dict[str, float]] = {}
    for client_id, asset_class, total_mv in asset_rows:
        asset_by_client.setdefault(client_id, {})[asset_class] = total_mv

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
    conn: duckdb.DuckDBPyConnection, config: dict
) -> dict[str, float]:
    """Score each client on investment experience.

    has_fund = 3 if client holds any Stock/ETF/MF (non-Cash asset class),
    else 0.  s_active scales 0-10.
    (number_of_trading_ttm is not yet available in client data.)

    Returns {client_id: score_0_10}.
    """
    weight = float(config.get("weight", 1))
    has_fund_score = float(config.get("has_fund", 3))

    # A client "has fund" if they hold any non-Cash asset class
    rows = conn.execute("""
        SELECT client_id,
               MAX(CASE WHEN asset_class != 'Cash' THEN 1 ELSE 0 END) AS has_non_cash
        FROM holdings
        GROUP BY client_id
    """).fetchall()

    scores: dict[str, float] = {}
    for client_id, has_non_cash in rows:
        # Scale has_fund_score 0-10: if has fund → has_fund_score, else 0
        # The score is on a 0-10 scale
        if has_non_cash:
            scores[client_id] = round(has_fund_score, 2)
        else:
            scores[client_id] = 0.0

    # Also include clients with no holdings at all
    all_clients = conn.execute("SELECT client_id FROM clients").fetchall()
    for (client_id,) in all_clients:
        if client_id not in scores:
            scores[client_id] = 0.0

    return scores


def score_life_stage(
    conn: duckdb.DuckDBPyConnection, config: dict
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

    rows = conn.execute("""
        SELECT client_id, birthdate
        FROM clients
    """).fetchall()

    scores: dict[str, float] = {}
    for client_id, birthdate_str in rows:
        if not birthdate_str or birthdate_str.upper() in ("N/A", ""):
            scores[client_id] = 0.0
            continue

        try:
            parts = birthdate_str.strip().split("-")
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
    conn: duckdb.DuckDBPyConnection, config: dict
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
    cash_scores = score_cash_drag(conn, config.get("score_cash_drag", {}))
    conc_scores = score_concentration_risk(conn, config.get("score_concentration_risk", {}))
    active_scores = score_active_manage(conn, config.get("score_active_manage", {}))
    life_scores = score_life_stage(conn, config.get("score_life_stage", {}))

    # Fetch client names
    client_rows = conn.execute("SELECT client_id, name FROM clients").fetchall()
    client_names = {row[0]: row[1] for row in client_rows}

    results: list[ClientScore] = []
    for client_id in client_names:
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
                name=client_names[client_id],
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

    conn = get_client_db_conn(read_only=False)
    try:
        init_client_db(conn)
        scores = compute_total_scores(conn, score_config)
        export_csv(scores, output_csv)
        return scores
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

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