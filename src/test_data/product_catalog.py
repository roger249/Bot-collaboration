"""
Product Catalog — DuckDB schema, query helpers.

Database location:  data/planbot/db/planbot.duckdb
Single-table design with two JSON columns:
  - type_specific        Product-type-specific fields
  - performance_history  Historical return/risk metrics by period
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

DB_PATH = Path("data/planbot/db/planbot.duckdb")

DDL_PRODUCTS = """
CREATE TABLE IF NOT EXISTS products (
    product_id          TEXT PRIMARY KEY,
    isin                TEXT,
    name                TEXT NOT NULL,
    ticker              TEXT,
    trading_currency    TEXT,
    risk_rating         INTEGER NOT NULL CHECK (risk_rating BETWEEN 1 AND 5),
    expected_return     DOUBLE,
    region              TEXT,
    country             TEXT,
    sector              TEXT,
    remarks             TEXT,
    product_type        TEXT NOT NULL,
    vehicle             TEXT,
    type_specific       TEXT,
    performance_history TEXT
);
"""


def get_conn(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection to the product catalog."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH), read_only=read_only)
    conn.execute("PRAGMA enable_progress_bar=false;")
    return conn


def init_db(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the products table if it does not already exist."""
    conn.execute(DDL_PRODUCTS)


# ---------------------------------------------------------------------------
# Query: search_aligned_products
# ---------------------------------------------------------------------------


def search_aligned_products(
    conn: duckdb.DuckDBPyConnection,
    *,
    product_type: str | None = None,
    region: str | None = None,
    max_risk_rating: int = 5,
    target_currency: str | None = None,
    strategic_intent: dict | None = None,
) -> dict[str, Any]:
    """Return products grouped by risk_rating, sorted by expected_return DESC.
    JSON columns parsed into Python dicts for LLM consumption."""
    conditions = ["1=1"]
    params: list[Any] = []
    if product_type:
        conditions.append("product_type = ?"); params.append(product_type)
    if region:
        conditions.append("region = ?"); params.append(region)
    if max_risk_rating < 5:
        conditions.append("risk_rating <= ?"); params.append(max_risk_rating)
    if target_currency:
        conditions.append("trading_currency = ?"); params.append(target_currency)

    where = " AND ".join(conditions)
    query = f"""
        SELECT product_id, name, ticker, risk_rating, expected_return,
               product_type, vehicle, trading_currency, region, sector,
               type_specific, performance_history
        FROM products WHERE {where}
        ORDER BY risk_rating, expected_return DESC
    """
    result = conn.execute(query, params).fetchall()
    columns = [desc[0] for desc in conn.description]

    grouped: dict[int, list[dict]] = {}
    for row in result:
        record = dict(zip(columns, row))
        for json_col in ("type_specific", "performance_history"):
            raw = record.get(json_col)
            record[json_col] = json.loads(raw) if isinstance(raw, str) else raw
        for k, v in record.items():
            if isinstance(v, float):
                record[k] = round(v, 4) if v is not None else None
        rr = record["risk_rating"]
        grouped.setdefault(rr, []).append(record)

    return {
        "query": {"product_type": product_type, "region": region,
                  "max_risk_rating": max_risk_rating, "target_currency": target_currency},
        "total_products": len(result),
        "by_risk_rating": grouped,
    }


def search_aligned_products_json(
    conn: duckdb.DuckDBPyConnection, **kwargs: Any
) -> str:
    """Convenience wrapper returning JSON string for LLM consumption."""
    return json.dumps(search_aligned_products(conn, **kwargs), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------


def get_summary(conn: duckdb.DuckDBPyConnection) -> dict:
    """Return count per product_type in the catalog."""
    rows = conn.execute(
        "SELECT product_type, COUNT(*) FROM products GROUP BY product_type ORDER BY COUNT(*) DESC"
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def get_product(conn: duckdb.DuckDBPyConnection, product_id: str) -> dict | None:
    """Return a single product with parsed JSON columns."""
    row = conn.execute(
        "SELECT * FROM products WHERE product_id = ?", [product_id]
    ).fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in conn.description]
    record = dict(zip(columns, row))
    for json_col in ("type_specific", "performance_history"):
        raw = record.get(json_col)
        record[json_col] = json.loads(raw) if isinstance(raw, str) else raw
    return record
