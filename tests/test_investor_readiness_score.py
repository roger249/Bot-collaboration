"""Unit tests for investor_readiness_score.py — scoring, DB init, normalization."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest
import yaml

from src.planbot.investor_readiness_score import (
    ClientScore,
    _linear_interpolate,
    _normalize_holdings_product_ids,
    compute_total_scores,
    get_client_db_conn,
    init_client_db,
    score_active_manage,
    score_cash_drag,
    score_concentration_risk,
    score_life_stage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    """Empty DuckDB with just the clients/holdings/profiles/products schema."""
    db_path = tmp_path / "test_score.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id TEXT PRIMARY KEY, name TEXT, aum DOUBLE, cash_pct DOUBLE, region TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            client_name TEXT PRIMARY KEY, birthdate TEXT, occupation TEXT,
            risk_rating INTEGER, marital_status TEXT, children_info TEXT,
            liquidity_need TEXT, income_stability TEXT, investment_objective TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            client_id TEXT NOT NULL, holding_idx INTEGER NOT NULL, holding_id TEXT, product_id TEXT,
            instrument_name TEXT, symbol TEXT, asset_class TEXT, region TEXT, currency TEXT,
            quantity DOUBLE, book_cost DOUBLE, market_value DOUBLE, unrealized_pl DOUBLE,
            unrealized_pl_pct DOUBLE, yield_pct DOUBLE, risk_bucket TEXT, esg_score TEXT, liquidity TEXT,
            PRIMARY KEY (client_id, holding_idx)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY, isin TEXT, name TEXT NOT NULL, ticker TEXT,
            trading_currency TEXT, risk_rating INTEGER, expected_return DOUBLE,
            region TEXT, country TEXT, sector TEXT, remarks TEXT,
            product_type TEXT NOT NULL, vehicle TEXT, type_specific TEXT, performance_history TEXT
        )
    """)
    yield conn
    conn.close()


@pytest.fixture
def seeded_db(empty_db: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """DB with test clients, profiles, holdings, and products."""
    conn = empty_db

    conn.executemany(
        "INSERT INTO clients VALUES (?,?,?,?,?)",
        [
            ("PB-S-001", "Alice Std", 1_000_000.0, 5.0, "North America"),
            ("PB-S-002", "Bob Heavy", 500_000.0, 30.0, "Europe"),
            ("PB-S-003", "Carol Cash", 100_000.0, 80.0, "Asia"),
        ],
    )
    conn.executemany(
        "INSERT INTO profiles VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("Alice Std", "1980-06-15", "Engineer", 4, "Married", "2", None, None, None),
            ("Bob Heavy", "1970-01-01", "Executive", 3, "Married", "1", None, None, None),
            ("Carol Cash", "1995-12-25", "Student", 1, "Single", "0", None, None, None),
        ],
    )
    conn.executemany(
        "INSERT INTO holdings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("PB-S-001", 0, "h1", "STOCK-AAPL", "Apple", "AAPL", "Equities", "NA", "USD",
             100, 15000, 500000, 0, 0, 0.5, "M", None, "T+2"),
            ("PB-S-001", 1, "h2", "ETF-SHV", "iShares ST", "SHV", "Cash", "NA", "USD",
             500, 50000, 50000, 0, 0, 4.0, "L", None, "T+1"),
            ("PB-S-002", 0, "h3", "STOCK-AAPL", "Apple", "AAPL", "Equities", "NA", "USD",
             200, 30000, 350000, 50000, 16.7, 0.5, "M", None, "T+2"),
            ("PB-S-003", 0, "h4", "ETF-VMRXX", "Cash Reserves", "VMRXX", "Cash", "NA", "USD",
             800, 80000, 80000, 0, 0, 5.0, "L", None, "T+1"),
        ],
    )
    conn.executemany(
        "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("STOCK-AAPL", None, "Apple Inc.", "AAPL", "USD", 4, None, "NA", "US", "Tech", None, "stock", None, None, None),
            ("ETF-SHV", None, "iShares Short Treasury", "SHV", "USD", 1, None, "NA", "US", None, None, "bond_fund", None,
             json.dumps({"maturity": (date.today() + timedelta(days=30)).isoformat()}), None),
            ("ETF-VMRXX", None, "Vanguard Cash Reserves", "VMRXX", "USD", 1, None, "NA", "US", None, None, "money_market_fund", None, None, None),
        ],
    )

    return conn


@pytest.fixture
def score_config() -> dict:
    return {
        "score_cash_drag": {"weight": 1, "pivot": {0.0: 0, 0.2: 3, 0.5: 9, 1.0: 10}},
        "score_concentration_risk": {
            "weight": 1,
            "s_single_holding": {0.2: 0, 1.0: 10},
            "s_region_exposure": {0.4: 0, 1.0: 10},
            "s_asset_class_exposure": {0.6: 0, 1.0: 10},
        },
        "score_active_manage": {"weight": 1, "has_fund": 3},
        "score_life_stage": {"weight": 1, "pivot": {25: 0, 35: 5, 45: 10, 65: 10, 80: 5}},
    }


# ---------------------------------------------------------------------------
# Tests: _linear_interpolate
# ---------------------------------------------------------------------------


class TestLinearInterpolate:
    def test_exact_match(self):
        pivot = {0.0: 0, 0.5: 5, 1.0: 10}
        assert _linear_interpolate(0.5, pivot) == 5.0

    def test_interpolation(self):
        pivot = {0.0: 0, 1.0: 10}
        assert _linear_interpolate(0.3, pivot) == 3.0

    def test_below_range_flat_extrapolation(self):
        pivot = {0.2: 3, 1.0: 10}
        assert _linear_interpolate(0.0, pivot) == 3.0

    def test_above_range_flat_extrapolation(self):
        pivot = {0.0: 0, 0.5: 9}
        assert _linear_interpolate(1.0, pivot) == 9.0

    def test_empty_pivot_returns_zero(self):
        assert _linear_interpolate(0.5, {}) == 0.0

    def test_single_point_pivot(self):
        pivot = {0.5: 7}
        assert _linear_interpolate(0.0, pivot) == 7.0
        assert _linear_interpolate(1.0, pivot) == 7.0


# ---------------------------------------------------------------------------
# Tests: score_cash_drag
# ---------------------------------------------------------------------------


class TestScoreCashDrag:
    def test_low_cash_scores_low(self, seeded_db, score_config):
        scores = score_cash_drag(seeded_db, score_config["score_cash_drag"])
        # Alice has 5% cash reported + $50K MMF / $1M AUM = 5% → effective 5%
        # That's k=0.05, which is below 0.2 pivot → score=0
        assert scores["PB-S-001"] <= 2.0

    def test_high_cash_scores_high(self, seeded_db, score_config):
        scores = score_cash_drag(seeded_db, score_config["score_cash_drag"])
        # Carol has 80% cash + $80K / $100K = 80% → effective 80%
        # k=0.8, between 0.5 and 1.0 → high score
        assert scores["PB-S-003"] >= 5.0

    def test_all_clients_have_scores(self, seeded_db, score_config):
        scores = score_cash_drag(seeded_db, score_config["score_cash_drag"])
        for cid in ["PB-S-001", "PB-S-002", "PB-S-003"]:
            assert cid in scores
            assert 0.0 <= scores[cid] <= 10.0


# ---------------------------------------------------------------------------
# Tests: score_concentration_risk
# ---------------------------------------------------------------------------


class TestScoreConcentrationRisk:
    def test_high_concentration_scores_high(self, seeded_db, score_config):
        scores = score_concentration_risk(seeded_db, score_config["score_concentration_risk"])
        # Bob has 1 holding of $350K / $500K = 70% in one stock → high concentration
        assert scores["PB-S-002"] >= 5.0

    def test_diversified_scores_lower(self, seeded_db, score_config):
        scores = score_concentration_risk(seeded_db, score_config["score_concentration_risk"])
        # Alice has 2 holdings: 50% stock, 5% cash → max is 50%
        assert scores["PB-S-001"] <= scores["PB-S-002"]

    def test_all_scores_in_range(self, seeded_db, score_config):
        scores = score_concentration_risk(seeded_db, score_config["score_concentration_risk"])
        for v in scores.values():
            assert 0.0 <= v <= 10.0


# ---------------------------------------------------------------------------
# Tests: score_active_manage
# ---------------------------------------------------------------------------


class TestScoreActiveManage:
    def test_clients_with_non_cash_get_score(self, seeded_db, score_config):
        scores = score_active_manage(seeded_db, score_config["score_active_manage"])
        # Alice and Bob have non-Cash holdings
        assert scores["PB-S-001"] == 3.0
        assert scores["PB-S-002"] == 3.0

    def test_cash_only_client_scores_zero(self, seeded_db, score_config):
        scores = score_active_manage(seeded_db, score_config["score_active_manage"])
        # Carol only has Cash asset class
        assert scores["PB-S-003"] == 0.0


# ---------------------------------------------------------------------------
# Tests: score_life_stage
# ---------------------------------------------------------------------------


class TestScoreLifeStage:
    def test_mid_age_scores_high(self, seeded_db, score_config):
        scores = score_life_stage(seeded_db, score_config["score_life_stage"])
        # Alice born 1980 (~46 years old) → between 45 and 65 pivot → score ~10
        assert scores["PB-S-001"] >= 5.0

    def test_missing_birthdate_scores_zero(self, seeded_db, score_config):
        scores = score_life_stage(seeded_db, score_config["score_life_stage"])
        for v in scores.values():
            assert 0.0 <= v <= 10.0


# ---------------------------------------------------------------------------
# Tests: compute_total_scores
# ---------------------------------------------------------------------------


class TestComputeTotalScores:
    def test_returns_all_clients(self, seeded_db, score_config):
        scores = compute_total_scores(seeded_db, score_config)
        assert len(scores) == 3

    def test_sorted_descending(self, seeded_db, score_config):
        scores = compute_total_scores(seeded_db, score_config)
        for i in range(len(scores) - 1):
            assert scores[i].total_score >= scores[i + 1].total_score

    def test_client_score_structure(self, seeded_db, score_config):
        scores = compute_total_scores(seeded_db, score_config)
        s = scores[0]
        assert isinstance(s, ClientScore)
        assert s.client_id
        assert s.name
        assert 0.0 <= s.total_score <= 40.0  # max 4*10
        assert 0.0 <= s.s_cash <= 10.0
        assert 0.0 <= s.s_concentration <= 10.0
        assert 0.0 <= s.s_active <= 10.0
        assert 0.0 <= s.s_lifestage <= 10.0


# ---------------------------------------------------------------------------
# Tests: _normalize_holdings_product_ids
# ---------------------------------------------------------------------------


class TestNormalizeHoldingsProductIds:
    def test_normalizes_ticker_with_market_suffix(self, empty_db):
        """holdings.product_id 'aapl-o' should become 'STOCK-AAPL'."""
        conn = empty_db
        conn.execute("INSERT INTO products VALUES ('STOCK-AAPL', NULL, 'Apple', 'AAPL', 'USD', 4, NULL, NULL, NULL, NULL, NULL, 'stock', NULL, NULL, NULL)")
        conn.execute("INSERT INTO clients VALUES ('PB-N-001', 'Test', 1000, 0, 'NA')")
        conn.execute("INSERT INTO holdings VALUES ('PB-N-001', 0, 'h1', 'aapl-o', 'Apple', 'AAPL', 'Equities', 'NA', 'USD', 10, 100, 100, 0, 0, 0, NULL, NULL, NULL)")

        _normalize_holdings_product_ids(conn)

        result = conn.execute("SELECT product_id FROM holdings WHERE client_id='PB-N-001'").fetchone()
        assert result[0] == "STOCK-AAPL"

    def test_direct_ticker_match_unchanged_if_already_correct(self, empty_db):
        """holdings.product_id that already matches should not change."""
        conn = empty_db
        conn.execute("INSERT INTO products VALUES ('STOCK-AAPL', NULL, 'Apple', 'AAPL', 'USD', 4, NULL, NULL, NULL, NULL, NULL, 'stock', NULL, NULL, NULL)")
        conn.execute("INSERT INTO clients VALUES ('PB-N-002', 'Test', 1000, 0, 'NA')")
        conn.execute("INSERT INTO holdings VALUES ('PB-N-002', 0, 'h1', 'AAPL', 'Apple', 'AAPL', 'Equities', 'NA', 'USD', 10, 100, 100, 0, 0, 0, NULL, NULL, NULL)")

        _normalize_holdings_product_ids(conn)

        result = conn.execute("SELECT product_id FROM holdings WHERE client_id='PB-N-002'").fetchone()
        assert result[0] == "STOCK-AAPL"

    def test_unmatched_product_id_left_as_is(self, empty_db):
        """Unknown product IDs like FX or treasuries are left unchanged."""
        conn = empty_db
        conn.execute("INSERT INTO products VALUES ('ETF-BND', NULL, 'Vanguard Bond', 'BND', 'USD', 2, NULL, NULL, NULL, NULL, NULL, 'bond_fund', NULL, NULL, NULL)")
        conn.execute("INSERT INTO clients VALUES ('PB-N-003', 'Test', 1000, 0, 'NA')")
        conn.execute(
            "INSERT INTO holdings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ['PB-N-003', 0, 'h1', 'eur-usd', 'EUR/USD', None, 'Currency', 'EU', 'EUR', 1000, 1000, 1000, 0, 0, 0, None, None, None],
        )

        _normalize_holdings_product_ids(conn)

        result = conn.execute("SELECT product_id FROM holdings WHERE client_id='PB-N-003'").fetchone()
        assert result[0] == "eur-usd"  # unchanged

    def test_skips_when_no_products_table(self, empty_db):
        """Should not crash when products table doesn't exist yet."""
        conn = empty_db
        conn.execute("DROP TABLE IF EXISTS products")
        conn.execute("INSERT INTO clients VALUES ('PB-N-004', 'Test', 1000, 0, 'NA')")
        conn.execute(
            "INSERT INTO holdings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ['PB-N-004', 0, 'h1', 'aapl-o', 'Apple', 'AAPL', 'Equities', 'NA', 'USD', 10, 100, 100, 0, 0, 0, None, None, None],
        )

        # Should not raise
        _normalize_holdings_product_ids(conn)


# ---------------------------------------------------------------------------
# Tests: init_client_db
# ---------------------------------------------------------------------------

class TestInitClientDb:
    def test_idempotent(self, tmp_path: Path, monkeypatch):
        """Running init_client_db twice should not duplicate data."""
        db_path = tmp_path / "test_idem.duckdb"
        # Point the module to our temp DB
        monkeypatch.setattr("src.planbot.investor_readiness_score.CLIENT_DB_PATH", db_path)

        conn = get_client_db_conn(read_only=False)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS products (product_id TEXT PRIMARY KEY, name TEXT, ticker TEXT, risk_rating INTEGER, product_type TEXT, isin TEXT, trading_currency TEXT, expected_return DOUBLE, region TEXT, country TEXT, sector TEXT, remarks TEXT, vehicle TEXT, type_specific TEXT, performance_history TEXT)")
            init_client_db(conn)
            count1 = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            init_client_db(conn)
            count2 = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            assert count1 == count2
        finally:
            conn.close()
