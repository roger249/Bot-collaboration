"""
Unit tests for reseed.py — bridge row insertion logic.

Uses a temp DuckDB + temp CSV to verify that _insert_bridge_rows correctly
reads market data and inserts holdings-compatible product_id rows.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.test_data.reseed import _collect_bridge_tickers, _insert_bridge_rows

# ---------------------------------------------------------------------------
# Sample bridge groups (mirrors the MD proposal, trimmed for speed)
# ---------------------------------------------------------------------------

SAMPLE_BRIDGE_GROUPS = {
    "holdings_stocks": {
        "description": "Stocks in client holdings",
        "product_type": "stock",
        "entries": [
            {"product_id": "1810-hk", "ticker": "1810.HK"},
            {"product_id": "brka", "ticker": "BRK-A"},
            {"product_id": "2018-hk", "ticker": "2018.HK"},
        ],
    },
    "holdings_treasury_yields": {
        "description": "Treasury yields",
        "product_type": "bond",
        "entries": [
            {"product_id": "us5yt-rr", "ticker": "US5YT=RR",
             "name": "US 5-Year Treasury Yield", "sector": "Government"},
        ],
    },
    "holdings_treasury_bills": {
        "description": "Treasury bills",
        "product_type": "money_market_fund",
        "entries": [
            {"product_id": "us2mt-x", "ticker": "US2MT=X",
             "name": "US 2-Month Treasury Bill", "sector": "Government"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_temp_db(db_path: Path) -> None:
    """Create a products table in a temp DuckDB."""
    import duckdb
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute("PRAGMA enable_progress_bar=false;")
    conn.execute("""
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
            performance_history TEXT,
            investment_note     TEXT
        );
    """)
    conn.close()


def _setup_monkeypatch(monkeypatch, db_path: Path) -> None:
    """Point reseed.get_conn to a temp DuckDB."""
    import duckdb
    import src.test_data.reseed as reseed_mod

    def _temp_get_conn(read_only: bool = False):
        return duckdb.connect(str(db_path), read_only=read_only)

    monkeypatch.setattr(reseed_mod, "get_conn", _temp_get_conn)


def _write_sample_csv(csv_path: Path) -> None:
    """Write a minimal market-data CSV for the bridge tickers."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ticker", "asset_class", "name", "currency",
        "risk_rating", "expected_return",
        "6m_return", "1y_return", "3y_return", "5y_return", "10y_return",
        "6m_cagr", "1y_cagr", "3y_cagr", "5y_cagr", "10y_cagr",
        "6m_max_drawdown", "1y_max_drawdown", "3y_max_drawdown", "5y_max_drawdown", "10y_max_drawdown",
    ]
    rows = [
        ["1810.HK", "EQUITY", "Xiaomi Corporation", "HKD", "4", "12.5",
         "8.2", "15.3", "28.7", "42.1", "55.0", "8.2", "15.3", "28.7", "42.1", "55.0",
         "-5.2", "-12.1", "-25.3", "-35.0", "-42.1"],
        ["BRK-A", "FINANCIAL", "Berkshire Hathaway Inc.", "USD", "3", "8.5",
         "5.1", "10.2", "22.5", "35.0", "48.0", "5.1", "10.2", "22.5", "35.0", "48.0",
         "-3.5", "-8.0", "-18.5", "-22.0", "-28.5"],
        ["2018.HK", "EQUITY", "AAC Technologies Holdings Inc.", "HKD", "4", "10.0",
         "6.0", "12.0", "18.0", "28.0", "35.0", "6.0", "12.0", "18.0", "28.0", "35.0",
         "-4.0", "-10.0", "-20.0", "-28.0", "-35.0"],
        ["US5YT=RR", "Fixed Income", "", "USD", "1", "3.8",
         "1.5", "2.8", "5.5", "8.0", "9.5", "1.5", "2.8", "5.5", "8.0", "9.5",
         "-0.5", "-1.0", "-2.0", "-3.0", "-4.0"],
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(fieldnames)
        for row in rows:
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_collect_bridge_tickers_deduplicates():
    """Tickers from multiple groups are collected and deduplicated."""
    groups = {
        "group_a": {"entries": [
            {"ticker": "AAPL"}, {"ticker": "GOOGL"},
        ]},
        "group_b": {"entries": [
            {"ticker": "AAPL"}, {"ticker": "MSFT"},
        ]},
    }
    tickers = _collect_bridge_tickers(groups)
    assert sorted(tickers) == ["AAPL", "GOOGL", "MSFT"]


def test_collect_bridge_tickers_empty():
    assert _collect_bridge_tickers({}) == []


class TestInsertBridgeRows:
    """Tests for _insert_bridge_rows — uses temp DuckDB and temp CSV."""

    def test_all_tickers_inserted_with_csv_values(self, monkeypatch, tmp_path: Path):
        """Normal flow: all bridge entries have matching CSV rows; values from CSV."""
        db_path = tmp_path / "planbot.duckdb"
        _create_temp_db(db_path)
        _setup_monkeypatch(monkeypatch, db_path)

        csv_path = tmp_path / "selected_etf.csv"
        _write_sample_csv(csv_path)

        _insert_bridge_rows(SAMPLE_BRIDGE_GROUPS, csv_path=csv_path)

        import duckdb
        conn = duckdb.connect(str(db_path), read_only=True)
        rows = conn.execute(
            "SELECT product_id, name, ticker, risk_rating, expected_return, product_type, sector "
            "FROM products ORDER BY product_id"
        ).fetchall()
        conn.close()

        by_pid = {r[0]: r for r in rows}
        # 4 of 5 bridge entries match CSV (us2mt-x ticker not in sample CSV)
        assert len(rows) == 4

        r = by_pid["1810-hk"]
        assert r[1] == "Xiaomi Corporation"   # name from CSV
        assert r[3] == 4                      # risk from CSV
        assert r[4] == 12.5                   # er from CSV
        assert r[5] == "stock"

        r = by_pid["brka"]
        assert r[1] == "Berkshire Hathaway Inc."
        assert r[3] == 3
        assert r[4] == 8.5

        # us5yt-rr: CSV name is empty → config fallback
        r = by_pid["us5yt-rr"]
        assert r[1] == "US 5-Year Treasury Yield"
        assert r[6] == "Government"
        assert r[3] == 1
        assert r[4] == 3.8
        assert r[5] == "bond"

    def test_ticker_not_in_csv_is_skipped(self, monkeypatch, tmp_path: Path):
        """A bridge entry whose ticker is absent from CSV is skipped."""
        db_path = tmp_path / "planbot.duckdb"
        _create_temp_db(db_path)
        _setup_monkeypatch(monkeypatch, db_path)

        csv_path = tmp_path / "selected_etf.csv"
        _write_sample_csv(csv_path)

        # US2MT=X is in the bridge group but NOT in the sample CSV
        _insert_bridge_rows(SAMPLE_BRIDGE_GROUPS, csv_path=csv_path)

        import duckdb
        conn = duckdb.connect(str(db_path), read_only=True)
        pids = [r[0] for r in conn.execute(
            "SELECT product_id FROM products ORDER BY product_id"
        ).fetchall()]
        conn.close()

        assert "us2mt-x" not in pids
        assert "1810-hk" in pids
        assert "us5yt-rr" in pids

    def test_performance_history_extracted(self, monkeypatch, tmp_path: Path):
        """Performance history JSON is extracted from CSV columns."""
        db_path = tmp_path / "planbot.duckdb"
        _create_temp_db(db_path)
        _setup_monkeypatch(monkeypatch, db_path)

        csv_path = tmp_path / "selected_etf.csv"
        _write_sample_csv(csv_path)

        _insert_bridge_rows(
            {"test_group": {"product_type": "stock", "entries": [
                {"product_id": "1810-hk", "ticker": "1810.HK"},
            ]}},
            csv_path=csv_path,
        )

        import duckdb
        conn = duckdb.connect(str(db_path), read_only=True)
        perf_json = conn.execute(
            "SELECT performance_history FROM products WHERE product_id = '1810-hk'"
        ).fetchone()[0]
        conn.close()

        perf = json.loads(perf_json)
        assert "1y" in perf
        assert "3y" in perf
        assert perf["1y"]["return"] == 15.3
        assert perf["3y"]["cagr"] == 28.7
        assert perf["1y"]["max_drawdown"] == -12.1

    def test_investment_note_generated(self, monkeypatch, tmp_path: Path):
        """Investment note is auto-generated and non-empty."""
        db_path = tmp_path / "planbot.duckdb"
        _create_temp_db(db_path)
        _setup_monkeypatch(monkeypatch, db_path)

        csv_path = tmp_path / "selected_etf.csv"
        _write_sample_csv(csv_path)

        _insert_bridge_rows(
            {"test_group": {"product_type": "stock", "entries": [
                {"product_id": "1810-hk", "ticker": "1810.HK"},
            ]}},
            csv_path=csv_path,
        )

        import duckdb
        conn = duckdb.connect(str(db_path), read_only=True)
        note = conn.execute(
            "SELECT investment_note FROM products WHERE product_id = '1810-hk'"
        ).fetchone()[0]
        conn.close()

        assert note is not None
        assert len(note) > 0
        assert "expected return" in note.lower()
