"""
Reseed pipeline for the products table in planbot.duckdb.

Usage:
    python -m src.test_data.reseed            # incremental — bridge rows only
    python -m src.test_data.reseed --full     # complete — rebuild DB from scratch

Modes:
    **Incremental** (default):
        Yahoo fetch *only the bridge tickers* → merge into CSV →
        INSERT OR REPLACE bridge rows.  Existing products are untouched.

    **Complete** (--full):
        Drop all products → Yahoo fetch *all* configured tickers →
        regenerate CSV → seed from CSV + OTC → insert bridge rows.
        The entire products table is rebuilt from zero.

Config:
    Reads duckdb_ticker_groups from config/config_marketdata.yaml.
    Each group defines entries with product_id (holdings-compatible) and ticker
    (Yahoo symbol).  Market data (risk_rating, expected_return, performance_history)
    is read from the generated CSV — never hardcoded.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from src.planbot.market_data_module import get_market_data
from src.test_data.product_catalog import get_conn
from src.test_data.product_catalog_seed import (
    DDL_COLUMNS,
    _generate_investment_note,
    _infer_region,
    _infer_vehicle,
    _synthesize_stock,
    extract_performance_history,
    seed as seed_products,
)

CONFIG_PATH = Path("config/config_marketdata.yaml")
CSV_PATH = Path("data/planbot/shared/product_catalog/selected_etf.csv")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reseed(
    config_path: str | Path = CONFIG_PATH,
    use_yahoo: bool = True,
    *,
    full: bool = False,
) -> None:
    """Reseed the products table.

    Parameters
    ----------
    full : bool
        ``True`` → **complete rebuild**: clear the products table, fetch ALL
        tickers from Yahoo, regenerate the CSV, seed from CSV + OTC, and
        insert bridge rows.  Existing products are wiped then repopulated.
        ``False`` (default) → **incremental**: fetch only bridge tickers,
        merge into the existing CSV, and INSERT OR REPLACE only the bridge
        rows.  All other products are left intact.
    """
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    bridge_groups: dict[str, Any] = raw.get("duckdb_ticker_groups", {})

    if full:
        print(f"─" * 50)
        print(f"COMPLETE REBUILD — products table will be wiped and repopulated.")
        print(f"─" * 50)

        # ── 1. Collect all tickers needed (existing groups + bridge groups)
        bridge_tickers = _collect_bridge_tickers(bridge_groups)
        config_tickers = _resolve_existing_tickers(raw)

        all_tickers = sorted(set(config_tickers + bridge_tickers))
        print(f"─" * 50)
        print(f"Step 1/3: Fetching market data for {len(all_tickers)} tickers …")
        print(f"  ({len(config_tickers)} from ticker_groups, {len(bridge_tickers)} from duckdb_ticker_groups)")
        print(f"─" * 50)

        get_market_data(
            tickers=all_tickers,
            output_filename=raw.get("output_filename", "selected_etf.csv"),
            frequency=raw.get("frequency", "1w"),
            metrics=raw.get("metrics", ["return", "CAGR", "max_drawdown"]),
            periods=raw.get("periods", ["6m", "1y", "3y", "5y", "10y"]),
            output_dir="data/planbot/shared/product_catalog",
            name_preference=raw.get("name_preference", "long"),
            asset_class_proxy=raw.get("asset_class_proxy"),
            risk_rating_table=raw.get("risk_rating"),
            certainty_rating_table=raw.get("certainty_rating"),
            certainty_periods=raw.get("certainty_period", ["1y", "3y", "8y"]),
            certainty_enabled=raw.get("certainty_enabled", False),
            liquidity_rating_map=raw.get("liquidity_rating"),
        )

        # ── 2. Seed DuckDB ────────────────────────────────────────────
        print()
        print(f"─" * 50)
        print(f"Step 2/3: Seeding DuckDB from CSV + OTC markdown …")
        print(f"─" * 50)
        seed_products(use_yahoo=use_yahoo)

        step_label = "Step 3/3"
    else:
        print(f"─" * 50)
        print(f"INCREMENTAL — only bridge rows will be added/updated (existing products untouched).")
        print(f"─" * 50)

        bridge_tickers = _collect_bridge_tickers(bridge_groups)
        bridge_tickers.sort()
        step_label = "Step 1/1"

    # ── Bridge rows ───────────────────────────────────────────────────
    print()
    print(f"─" * 50)
    total_entries = sum(len(g.get("entries", [])) for g in bridge_groups.values())
    print(f"{step_label}: Inserting {total_entries} bridge row(s) from {len(bridge_groups)} groups …")
    print(f"─" * 50)

    # Build in-memory ticker→data map
    if full:
        # Read from the full CSV written by get_market_data above
        csv_row_map = _read_csv_to_dict(CSV_PATH)
    else:
        # Fetch only bridge tickers, get_market_data writes CSV as debug artifact
        csv_row_map = _fetch_tickers_data(bridge_tickers, raw)

    _insert_bridge_rows(bridge_groups, csv_data=csv_row_map)

    _print_summary()


def _insert_bridge_rows(
    bridge_groups: dict[str, Any],
    csv_data: dict[str, dict] | None = None,
    csv_path: str | Path = CSV_PATH,
) -> None:
    """Insert bridge rows into DuckDB.

    Parameters
    ----------
    csv_data : dict | None
        ``{ticker: {...row...}}`` map (in-memory).  If None, reads from *csv_path*.
    """
    if not bridge_groups:
        print("  (no duckdb_ticker_groups configured — skipping)")
        return

    # Build ticker → row lookup (in-memory if provided, else fall back to file)
    if csv_data is None:
        csv_data = _read_csv_to_dict(csv_path)

    conn = get_conn(read_only=False)
    inserted = 0
    skipped = 0

    for group_name, group in bridge_groups.items():
        product_type = group.get("product_type", "stock")
        entries = group.get("entries", [])
        for entry in entries:
            pid = entry.get("product_id", "")
            ticker = entry.get("ticker", "")
            csv_row = csv_data.get(ticker)

            if csv_row is None:
                print(f"  ⚠ {pid:20s}  ticker={ticker} — not in CSV, skipping")
                skipped += 1
                continue

            # ── Build row from CSV (market-derived) + config fallbacks
            csv_name = csv_row.get("name", "")
            csv_asset_class = csv_row.get("asset_class", "")
            csv_region = _infer_region(ticker, csv_asset_class)

            name = entry.get("name") or csv_name or pid
            sector = entry.get("sector") or csv_asset_class or ""
            region = csv_region

            # risk_rating / expected_return: config overrides take priority over CSV
            risk_rating_str = csv_row.get("risk_rating", "")
            risk_rating: int
            if "risk_rating" in entry:
                risk_rating = int(entry["risk_rating"])
            else:
                try:
                    risk_rating = int(risk_rating_str)
                except (ValueError, TypeError):
                    risk_rating = 3  # default

            expected_return: float | None = None
            if "expected_return" in entry:
                expected_return = float(entry["expected_return"])
            else:
                try:
                    expected_return = float(csv_row.get("expected_return", ""))
                except (ValueError, TypeError):
                    pass

            perf = extract_performance_history(csv_row)

            # Type-specific synthesis (entry can supply an override map)
            ts_override = entry.get("type_specific")
            if product_type == "stock" and not ts_override:
                vehicle = "Direct"
                ts = _synthesize_stock(csv_row, {})
            elif ts_override:
                vehicle = _infer_vehicle(product_type)
                ts = dict(ts_override)  # shallow copy to avoid mutating config
            else:
                vehicle = _infer_vehicle(product_type)
                ts = {}

            row_data = {
                "product_id": pid,
                "isin": csv_row.get("isin"),
                "name": name,
                "ticker": ticker,
                "trading_currency": csv_row.get("currency", "USD"),
                "risk_rating": risk_rating,
                "expected_return": expected_return,
                "region": region,
                "country": csv_row.get("country"),
                "sector": sector,
                "remarks": f"Bridge row for holdings product_id={pid}. Group: {group_name}.",
                "product_type": product_type,
                "vehicle": vehicle,
                "type_specific": json.dumps(ts, ensure_ascii=False),
                "performance_history": json.dumps(perf, ensure_ascii=False),
                "investment_note": _generate_investment_note(
                    name=name,
                    product_type=product_type,
                    sector=sector,
                    expected_return=expected_return,
                    risk_rating=risk_rating,
                    region=region,
                ),
            }

            conn.execute(
                "INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [row_data[k] for k in DDL_COLUMNS],
            )
            print(f"  ✓ {pid:20s}  type={product_type:20s}  risk={risk_rating}  er={expected_return}")
            inserted += 1

    conn.close()
    print(f"  Inserted: {inserted}, Skipped: {skipped}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_tickers_data(
    tickers: list[str],
    raw: dict,
) -> dict[str, dict]:
    """Fetch market data for *tickers* from Yahoo and return ``{ticker: row}``.

    Calls ``get_market_data`` which writes a CSV as a debugging artifact
    (the file is not used for data transfer — data flows in-memory).
    """
    import tempfile

    with tempfile.NamedTemporaryFile(
        suffix=".csv", mode="w", delete=False, newline="", encoding="utf-8"
    ) as tmp:
        tmp_path = Path(tmp.name)

    print(f"  Fetching {len(tickers)} ticker(s) from Yahoo …")
    get_market_data(
        tickers=tickers,
        output_filename=tmp_path.name,
        frequency=raw.get("frequency", "1w"),
        metrics=raw.get("metrics", ["return", "CAGR", "max_drawdown"]),
        periods=raw.get("periods", ["6m", "1y", "3y", "5y", "10y"]),
        output_dir=tmp_path.parent,
        name_preference=raw.get("name_preference", "long"),
        asset_class_proxy=raw.get("asset_class_proxy"),
        risk_rating_table=raw.get("risk_rating"),
        certainty_rating_table=raw.get("certainty_rating"),
        certainty_periods=raw.get("certainty_period", ["1y", "3y", "8y"]),
        certainty_enabled=raw.get("certainty_enabled", False),
        liquidity_rating_map=raw.get("liquidity_rating"),
    )

    result = _read_csv_to_dict(tmp_path)
    tmp_path.unlink(missing_ok=True)
    return result


def _read_csv_to_dict(csv_path: str | Path) -> dict[str, dict]:
    """Read a market-data CSV into ``{ticker: {...row...}}``."""
    result: dict[str, dict] = {}
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            t = row.get("ticker", "").strip()
            if t:
                result[t] = row
    return result


def _collect_bridge_tickers(bridge_groups: dict) -> list[str]:
    """Extract unique tickers from all duckdb_ticker_groups entries."""
    tickers: list[str] = []
    seen: set[str] = set()
    for group in bridge_groups.values():
        for entry in group.get("entries", []):
            t = entry.get("ticker", "").strip()
            if t and t not in seen:
                tickers.append(t)
                seen.add(t)
    return tickers


def _resolve_existing_tickers(raw: dict) -> list[str]:
    """Resolve tickers from execute_ticker_groupname like market_data_module does."""
    groups = raw.get("ticker_groups", {})
    exec_name = raw.get("execute_ticker_groupname")

    if exec_name is None:
        return []

    names = exec_name if isinstance(exec_name, list) else [exec_name]
    tickers: list[str] = []
    seen: set[str] = set()
    for name in names:
        name = str(name).strip()
        group_tickers = groups.get(name, [])
        for t in group_tickers:
            t = str(t).strip().upper() if t else ""
            if t and t not in seen:
                tickers.append(t)
                seen.add(t)
    return tickers


def _print_summary() -> None:
    """Print products count and remaining gap count."""
    conn = get_conn(read_only=True)
    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    orphans = conn.execute("""
        SELECT COUNT(DISTINCT h.product_id)
        FROM holdings h
        LEFT JOIN products p ON h.product_id = p.product_id
        WHERE p.product_id IS NULL
    """).fetchone()[0]
    conn.close()

    print()
    print("=" * 50)
    print(f"  Products in DB                    : {total}")
    print(f"  Holdings without matching product : {orphans}")
    print("=" * 50)


if __name__ == "__main__":
    import sys
    full = "--full" in sys.argv
    reseed(full=full)
