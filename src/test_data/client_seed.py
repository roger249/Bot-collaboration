"""Client data seeder — build the DuckDB client/holding tables from CSV.

Extracted from ``investor_readiness_score.py`` (Sprint 2, Task 5).  These are
ETL helpers that talk to DuckDB directly (populating the file), so they are
the one place the ``duckdb`` import is still needed in the data path.

The scorecard itself (``investor_readiness_score.py``) is I/O-free.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import duckdb

LOGGER = logging.getLogger(__name__)

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

# Known market suffixes in holdings productId values from the source CSV.
# e.g. 'aapl-o' → base ticker 'AAPL' → product 'STOCK-AAPL'
_MARKET_SUFFIXES = ["-O", "-K", "-HK", "-RR", "-X"]


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
