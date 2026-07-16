"""Unit tests for client_api.py — all four client API methods.

Uses a temporary DuckDB seeded with minimal test data so tests are
isolated from the production database.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest
import yaml

from src.integrations.client_api import (
    search,
    search_by_id,
    search_by_investor_readiness_score,
    search_holdings_maturing,
)
from src.planbot.investor_readiness_score import (
    init_client_db,
    get_client_db_conn,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_minimal_db(db_path: Path) -> None:
    """Create a temporary DuckDB with clients, holdings, and products."""
    conn = duckdb.connect(str(db_path))

    # Products
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id   TEXT PRIMARY KEY,
            isin         TEXT,
            name         TEXT NOT NULL,
            ticker       TEXT,
            trading_currency TEXT,
            risk_rating  INTEGER NOT NULL,
            expected_return DOUBLE,
            region       TEXT,
            country      TEXT,
            sector       TEXT,
            remarks      TEXT,
            product_type TEXT NOT NULL,
            vehicle      TEXT,
            type_specific TEXT,
            performance_history TEXT
        )
    """)

    products = [
        ("STOCK-AAPL", None, "Apple Inc.", "AAPL", "USD", 4, None, "North America", "US", "Technology", None, "stock", None, None, None),
        ("ETF-SHV", None, "iShares Short Treasury Bond ETF", "SHV", "USD", 1, None, "North America", "US", None, None, "bond_fund", None,
         json.dumps({"maturity": (date.today() + timedelta(days=30)).isoformat()}), None),
        ("ETF-BND", None, "Vanguard Total Bond Market ETF", "BND", "USD", 2, None, "North America", "US", None, None, "bond_fund", None,
         json.dumps({"maturity": (date.today() + timedelta(days=180)).isoformat()}), None),
        ("PROD003", None, "5Y Callable Bond", None, "USD", 2, None, "North America", "US", None, None, "bond", None,
         json.dumps({"maturity": (date.today() + timedelta(days=10)).isoformat()}), None),
        ("ETF-VMRXX", None, "Vanguard Cash Reserves", "VMRXX", "USD", 1, None, "North America", "US", None, None, "money_market_fund", None, None, None),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        products,
    )

    # Clients (unified — includes all profile fields)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id          TEXT PRIMARY KEY,
            name               TEXT NOT NULL,
            aum                DOUBLE,
            cash_pct           DOUBLE,
            region             TEXT,
            birthdate          TEXT,
            occupation         TEXT,
            risk_rating        INTEGER,
            marital_status     TEXT,
            children_info      TEXT,
            liquidity_need     TEXT,
            income_stability   TEXT,
            investment_objective TEXT
        )
    """)
    conn.executemany(
        "INSERT OR REPLACE INTO clients VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("PB-TEST-001", "Alice Alpha", 1_000_000.0, 5.0, "North America",
             "1980-06-15", "Engineer", 4, "Married", "2 children", "Low", "High", "Growth"),
            ("PB-TEST-002", "Bob Beta", 500_000.0, 20.0, "Europe",
             "1955-03-20", "Retired", 2, "Married", "0 children", "Medium", "Low", "Income"),
            ("PB-TEST-003", "Carol Gamma", 2_000_000.0, 1.0, "Asia",
             "1990-11-01", "Entrepreneur", 5, "Single", "0 children", "High", "Variable", "Aggressive Growth"),
        ],
    )

    # Holdings
    conn.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            client_id TEXT NOT NULL, holding_idx INTEGER NOT NULL, holding_id TEXT, product_id TEXT,
            instrument_name TEXT, symbol TEXT, asset_class TEXT, region TEXT, currency TEXT,
            quantity DOUBLE, book_cost DOUBLE, market_value DOUBLE, unrealized_pl DOUBLE,
            unrealized_pl_pct DOUBLE, yield_pct DOUBLE, risk_bucket TEXT, esg_score TEXT, liquidity TEXT,
            PRIMARY KEY (client_id, holding_idx)
        )
    """)
    conn.executemany(
        "INSERT OR REPLACE INTO holdings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("PB-TEST-001", 0, "h1", "STOCK-AAPL", "Apple Inc.", "AAPL", "Equities", "North America", "USD",
             100, 15000, 18000, 3000, 20.0, 0.5, "Medium", None, "T+2"),
            ("PB-TEST-001", 1, "h2", "ETF-SHV", "iShares Short Treasury", "SHV", "Cash", "North America", "USD",
             500, 50000, 50000, 0, 0.0, 4.0, "Low", None, "T+1"),
            ("PB-TEST-001", 2, "h3", "PROD003", "5Y Callable Bond", None, "Fixed Income", "North America", "USD",
             10, 10000, 10000, 0, 0.0, 3.0, "Low", None, "T+2"),
            ("PB-TEST-002", 0, "h4", "ETF-VMRXX", "Vanguard Cash Reserves", "VMRXX", "Cash", "North America", "USD",
             1000, 100000, 100000, 0, 0.0, 5.0, "Low", None, "T+1"),
            ("PB-TEST-003", 0, "h5", "ETF-BND", "Vanguard Total Bond", "BND", "Fixed Income", "North America", "USD",
             200, 15000, 16000, 1000, 6.67, 3.5, "Low", None, "T+2"),
            ("PB-TEST-003", 1, "h6", "STOCK-AAPL", "Apple Inc.", "AAPL", "Equities", "North America", "USD",
             50, 7500, 9000, 1500, 20.0, 0.5, "Medium", None, "T+2"),
        ],
    )

    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary DuckDB and point client_api to it."""
    db_path = tmp_path / "test_planbot.duckdb"
    _seed_minimal_db(db_path)

    # Patch DB_PATH and CONFIG_PATH in client_api
    monkeypatch.setattr("src.integrations.client_api.DB_PATH", db_path)

    # Also write a minimal config for scoring
    config_path = tmp_path / "config_planbot.yaml"
    config_path.write_text(
        yaml.dump({
            "investor_readiness_score": {
                "output": {"file": str(tmp_path / "scores.csv"), "duckdb": str(db_path)},
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
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr("src.integrations.client_api.CONFIG_PATH", config_path)

    return db_path


# ---------------------------------------------------------------------------
# Tests: search_by_id
# ---------------------------------------------------------------------------


class TestSearchById:
    def test_returns_full_profile_with_holdings(self, test_db_path: Path):
        result = search_by_id("PB-TEST-001")
        assert result is not None
        assert result["client_id"] == "PB-TEST-001"
        assert result["name"] == "Alice Alpha"
        assert len(result["holdings"]) == 3
        assert result["holdings"][0]["product_id"] == "STOCK-AAPL"

    def test_returns_none_for_missing_client(self, test_db_path: Path):
        result = search_by_id("PB-NONEXISTENT")
        assert result is None

    def test_includes_derived_fields(self, test_db_path: Path):
        result = search_by_id("PB-TEST-001")
        assert "age" in result
        assert "has_fund" in result
        assert "investor_readiness_score" in result
        assert "cash_score" in result
        assert "concentration_score" in result
        assert "product_types_in_holdings" in result

    def test_includes_holding_details(self, test_db_path: Path):
        result = search_by_id("PB-TEST-001")
        h0 = result["holdings"][0]
        assert h0["holding_idx"] == 0
        assert h0["instrument_name"] == "Apple Inc."
        assert h0["symbol"] == "AAPL"
        assert h0["asset_class"] == "Equities"
        assert h0["market_value"] == 18000
        assert h0["quantity"] == 100


# ---------------------------------------------------------------------------
# Tests: search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_risk_rating_exact_match(self, test_db_path: Path):
        results = search(risk_rating=4)
        assert len(results) == 1
        assert results[0]["client_id"] == "PB-TEST-001"

    def test_risk_rating_range(self, test_db_path: Path):
        results = search(risk_rating=[2, 5])
        assert len(results) >= 2

    def test_age_filter(self, test_db_path: Path):
        # Alice born 1980 should be ~46
        results = search(risk_rating=[1, 5], age=[40, 50])
        assert any(r["client_id"] == "PB-TEST-001" for r in results)

    def test_product_types_in_holdings(self, test_db_path: Path):
        # Alice holds stock + bond_fund + bond
        results = search(risk_rating=[1, 5], product_types_in_holdings="equity")
        assert any(r["client_id"] == "PB-TEST-001" for r in results)

    def test_product_types_list(self, test_db_path: Path):
        results = search(risk_rating=[1, 5], product_types_in_holdings=["equity", "bond"])
        assert any(r["client_id"] == "PB-TEST-001" for r in results)

    def test_cash_score_filter(self, test_db_path: Path):
        results = search(risk_rating=[1, 5], cash_score=[0, 5])
        assert len(results) >= 1

    def test_concentration_score_filter(self, test_db_path: Path):
        results = search(risk_rating=[1, 5], concentration_score=[0, 10])
        assert len(results) >= 1

    def test_results_sorted_by_readiness_score_desc(self, test_db_path: Path):
        results = search(risk_rating=[1, 5])
        scores = [r["investor_readiness_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_result_for_impossible_filter(self, test_db_path: Path):
        results = search(risk_rating=99)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Tests: search_holdings_maturing
# ---------------------------------------------------------------------------


class TestSearchHoldingsMaturing:
    def test_finds_bonds_maturing_within_window(self, test_db_path: Path):
        # PROD003 matures in 10 days
        results = search_holdings_maturing(product_types=["bond"], within_days=14)
        assert len(results) >= 1
        assert results[0]["product_id"] == "PROD003"
        assert results[0]["days_to_mature"] <= 14

    def test_defaults_to_bond_type(self, test_db_path: Path):
        results = search_holdings_maturing(within_days=14)
        # Should only return bond type, not bond_fund
        for r in results:
            assert r["product_id"] == "PROD003"  # Only PROD003 is product_type='bond'

    def test_no_results_when_nothing_matures(self, test_db_path: Path):
        results = search_holdings_maturing(within_days=1)
        # PROD003 matures in 10 days, nothing in 1 day
        assert len(results) == 0

    def test_bond_fund_type_also_works(self, test_db_path: Path):
        results = search_holdings_maturing(product_types=["bond_fund"], within_days=365)
        assert len(results) >= 1

    def test_as_of_date_parameter(self, test_db_path: Path):
        future_date = (date.today() + timedelta(days=5)).isoformat()
        results = search_holdings_maturing(within_days=14, as_of_date=future_date)
        # PROD003 matures 10 days from today, so from future_date it's 5 days away
        assert len(results) >= 1


# ---------------------------------------------------------------------------
# Tests: search_by_investor_readiness_score
# ---------------------------------------------------------------------------


class TestSearchByInvestorReadinessScore:
    @pytest.fixture(autouse=True)
    def _patch_run_score_card(self, monkeypatch, test_db_path):
        """Patch run_score_card to use the test DB instead of re-seeding from CSV."""
        from src.planbot import investor_readiness_score as irs

        def _fake_run_score_card(config_path="config/config_planbot.yaml"):
            conn = duckdb.connect(str(test_db_path), read_only=False)
            try:
                raw = yaml.safe_load(Path("config/config_planbot.yaml").read_text()) or {}
                score_config = raw.get("investor_readiness_score", {})
                return irs.compute_total_scores(conn, score_config)
            finally:
                conn.close()

        monkeypatch.setattr(
            "src.integrations.client_api.run_score_card", _fake_run_score_card
        )

    def test_returns_ranked_clients(self, test_db_path: Path):
        results = search_by_investor_readiness_score()
        assert len(results) == 3
        # Should be sorted by total_score descending
        scores = [r["total_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_top_n_limits_results(self, test_db_path: Path):
        results = search_by_investor_readiness_score(top_n=2)
        assert len(results) == 2

    def test_has_required_fields(self, test_db_path: Path):
        results = search_by_investor_readiness_score(top_n=1)
        r = results[0]
        assert "rank" in r
        assert "client_id" in r
        assert "name" in r
        assert "total_score" in r
        assert "s_cash" in r
        assert "s_concentration" in r
        assert "s_active" in r
        assert "s_lifestage" in r

    def test_rank_starts_at_one(self, test_db_path: Path):
        results = search_by_investor_readiness_score()
        assert results[0]["rank"] == 1
