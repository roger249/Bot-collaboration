#!/usr/bin/env python3
"""Export the client + holdings tables from DuckDB to a YAML file.

Produces a flat list of client records, each with its holdings nested under a
``holdings`` key — mirroring the shape returned by ``search_by_id()`` and the
style of ``docs/test data/products_export.yaml``.

Run from the repository root::

    ./.venv/bin/python scripts/export_clients_holdings.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_DB_PATH = _ROOT / "data" / "planbot" / "db" / "planbot.duckdb"
_OUT_PATH = _ROOT / "docs" / "test data" / "clients_export.yaml"

# Column order for the two tables (schema source of truth:
# docs/specification/schema_client/client_holdings_schema.md).
_CLIENT_COLUMNS = [
    "client_id", "name", "aum", "cash_pct", "region", "birthdate",
    "occupation", "risk_rating", "marital_status", "children_info",
    "liquidity_need", "income_stability", "investment_objective",
    "qualitative_profile", "like_products", "dislike_products",
    "date_last_traded", "product_name_last_traded", "position_bought",
]

_HOLDING_COLUMNS = [
    "holding_idx", "holding_id", "product_id", "instrument_name", "symbol",
    "asset_class", "region", "currency", "quantity", "book_cost",
    "market_value", "unrealized_pl", "unrealized_pl_pct", "yield_pct",
    "risk_bucket", "esg_score", "liquidity",
]

# `client_id` is fetched for grouping but is not part of the nested holding
# record (it is implied by the parent client).
_HOLDING_QUERY_COLUMNS = ["client_id", *_HOLDING_COLUMNS]


def _dump_value(value: object) -> object:
    """Normalize DuckDB values for clean, JSON-friendly YAML output."""
    if isinstance(value, date):
        return value.isoformat()
    return value


def _rows_to_dicts(conn, table: str, columns: list[str]) -> list[dict]:
    quoted = ", ".join(f'"{c}"' for c in columns)
    rows = conn.execute(f'SELECT {quoted} FROM {table}').fetchall()
    return [
        {c: _dump_value(v) for c, v in zip(columns, row)}
        for row in rows
    ]


def main() -> None:
    if not _DB_PATH.exists():
        print(f"DuckDB not found: {_DB_PATH}", file=sys.stderr)
        raise SystemExit(1)

    conn = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        clients = _rows_to_dicts(conn, "clients", _CLIENT_COLUMNS)
        holdings = _rows_to_dicts(conn, "holdings", _HOLDING_QUERY_COLUMNS)
    finally:
        conn.close()

    # Group holdings by client (ordered by holding_idx within each client).
    holdings_by_client: dict[str, list[dict]] = {}
    for h in holdings:
        cid = h.pop("client_id")
        holdings_by_client.setdefault(cid, []).append(h)

    records = []
    for c in clients:
        cid = c["client_id"]
        c["holdings"] = holdings_by_client.get(cid, [])
        records.append(c)

    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUT_PATH.write_text(
        yaml.safe_dump(records, sort_keys=False, allow_unicode=True, width=100) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {_OUT_PATH.relative_to(_ROOT)} "
        f"({len(records)} clients, {len(holdings)} holdings)"
    )


if __name__ == "__main__":
    main()
