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
    investment_objective TEXT,
    like_products     VARCHAR[],
    dislike_products  VARCHAR[],
    date_last_traded  DATE,
    product_name_last_traded TEXT,
    position_bought   DOUBLE
);
"""

# Idempotent migration for pre-existing client tables (semantic-embedding columns).
DDL_ADD_SEMANTIC_COLUMNS = [
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS like_products VARCHAR[];",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS dislike_products VARCHAR[];",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS date_last_traded DATE;",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS product_name_last_traded TEXT;",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS position_bought DOUBLE;",
]

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

# Semantic-embedding seed data: like/dislike keyword lists per client (by name).
# Populates the ``like_products`` / ``dislike_products`` columns on the client
# table so the similarity features have realistic input.
_CLIENT_SEMANTIC_SEED: dict[str, dict[str, list[str]]] = {
    "David Kim": {
        "like_products": ["technology", "structured products", "tactical equity"],
        "dislike_products": ["idle cash"],
    },
    "Sarah Chen": {
        "like_products": ["ESG", "sustainable investing", "APAC equity", "alternatives"],
        "dislike_products": [],
    },
    "James Harrison": {
        "like_products": ["government bonds", "investment-grade credit", "dividend stocks", "guaranteed income"],
        "dislike_products": ["market volatility"],
    },
    "Michael Sterling": {
        "like_products": ["tax-efficient structures", "fixed income", "balanced funds"],
        "dislike_products": [],
    },
    "Emma Thompson": {
        "like_products": ["guaranteed income", "inflation protection"],
        "dislike_products": ["equity risk"],
    },
    "Robert Rodriguez": {
        "like_products": ["growth", "emerging markets"],
        "dislike_products": [],
    },
    "Akira Tanaka": {
        "like_products": ["asian real estate", "infrastructure", "structured products", "alternatives"],
        "dislike_products": [],
    },
    "Elena Petrova": {
        "like_products": ["fixed-income laddering", "inflation-linked bonds"],
        "dislike_products": [],
    },
    "Sophia Rossi": {
        "like_products": ["healthcare", "biotech", "equity", "alternatives"],
        "dislike_products": [],
    },
    "William Turner": {
        "like_products": ["balanced strategies", "downside protection", "tax-loss harvesting"],
        "dislike_products": [],
    },
    "Emily Harrison": {
        "like_products": ["international equity", "EM debt", "diversification"],
        "dislike_products": [],
    },
    "Harrison Holdings Ltd.": {
        "like_products": ["liquid", "investment-grade", "yield"],
        "dislike_products": ["illiquid"],
    },
    "Harrison Jr. Education Trust": {
        "like_products": ["ESG", "balanced funds", "growth", "multi-asset"],
        "dislike_products": [],
    },
    "Sarah Wong": {
        "like_products": ["annuities", "fixed-income ladders", "steady income"],
        "dislike_products": [],
    },
    "Michael Wang": {
        "like_products": ["dividend stocks", "HK/China stocks", "asian REITs", "income"],
        "dislike_products": ["FX risk"],
    },
    "James Chen": {
        "like_products": ["equity funds", "downside hedging"],
        "dislike_products": [],
    },
    "Catherine Li": {
        "like_products": ["technology", "AI", "emerging markets", "private equity"],
        "dislike_products": [],
    },
    "Emily Zhang": {
        "like_products": ["balanced funds", "multi-asset"],
        "dislike_products": [],
    },
    "Linda Xu": {
        "like_products": ["APAC stocks", "dividend stocks", "gold"],
        "dislike_products": [],
    },
    "David Wu": {
        "like_products": ["balanced funds", "income-oriented"],
        "dislike_products": ["market volatility"],
    },
    "Anna Lin": {
        "like_products": ["real assets", "inflation protection"],
        "dislike_products": [],
    },
    "Victor Ng": {
        "like_products": ["dividend strategies", "bond ladders", "retirement income", "annuities"],
        "dislike_products": [],
    },
    "Rachel Ho": {
        "like_products": ["AI", "clean energy", "demographics", "equity"],
        "dislike_products": [],
    },
}

# Static "last trade" date used for seeding the trade-derived columns.
_SEED_LAST_TRADE_DATE = "2026-08-18"


def _seed_semantic_columns(conn: duckdb.DuckDBPyConnection) -> None:
    """Populate the semantic-embedding client columns with realistic values.

    ``like_products`` / ``dislike_products`` come from ``_CLIENT_SEMANTIC_SEED``;
    the trade-derived fields (``date_last_traded``, ``product_name_last_traded``,
    ``position_bought``) are derived from each client's first holding.
    """
    for name, seed in _CLIENT_SEMANTIC_SEED.items():
        conn.execute(
            "UPDATE clients SET like_products = ?, dislike_products = ? WHERE name = ?",
            [seed.get("like_products", []), seed.get("dislike_products", []), name],
        )

    first_holdings = conn.execute(
        "SELECT client_id, instrument_name, market_value FROM holdings "
        "WHERE holding_idx = 0 ORDER BY client_id"
    ).fetchall()
    for client_id, instrument_name, market_value in first_holdings:
        conn.execute(
            "UPDATE clients SET date_last_traded = ?, product_name_last_traded = ?, "
            "position_bought = ? WHERE client_id = ?",
            [_SEED_LAST_TRADE_DATE, instrument_name or "", float(market_value or 0.0), client_id],
        )

    LOGGER.info(
        "Seeded semantic columns: %d clients with like/dislike, %d with trade fields",
        len(_CLIENT_SEMANTIC_SEED), len(first_holdings),
    )


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
    for stmt in DDL_ADD_SEMANTIC_COLUMNS:
        conn.execute(stmt)
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
                """INSERT OR REPLACE INTO clients
                   (client_id, name, aum, cash_pct, region, birthdate, occupation, risk_rating,
                    marital_status, children_info, liquidity_need, income_stability, investment_objective,
                    like_products, dislike_products, date_last_traded, product_name_last_traded, position_bought)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    client_id, name, aum, cash_pct, region,
                    None, None, None, None, None,  # birthdate, occupation, risk_rating, marital_status, children_info
                    None, None, None,              # liquidity_need, income_stability, investment_objective
                    [], [], None, None, None,      # semantic columns — populated by _seed_semantic_columns
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

    # Populate semantic-embedding columns (like/dislike + trade-derived fields)
    _seed_semantic_columns(conn)


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
