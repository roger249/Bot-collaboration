"""Unit tests for the Data API server endpoints.

Verifies every endpoint returns 200 with non-empty data using the Swagger example payloads.
These tests use ``TestClient`` (in-process) — no real HTTP server needed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.integrations.data_server import app

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# GET endpoints
# ═══════════════════════════════════════════════════════════════════════════


class TestGetEndpoints:
    """GET /api/v1/clients/... and /api/v1/products/..."""

    def test_get_client_by_id_returns_client(self):
        r = client.get("/api/v1/clients/PB-HK-000007-5")
        assert r.status_code == 200
        data = r.json()
        assert data["client_id"] == "PB-HK-000007-5"
        assert "name" in data
        assert "risk_rating" in data
        assert "holdings" in data
        assert len(data["holdings"]) > 0

    def test_get_client_by_id_not_found(self):
        r = client.get("/api/v1/clients/PB-HK-NONEXIST")
        assert r.status_code == 404

    def test_get_product_by_id_returns_product(self):
        r = client.get("/api/v1/products/PROD053")
        assert r.status_code == 200
        data = r.json()
        assert data["product_id"] == "PROD053"
        assert "name" in data
        assert "risk_rating" in data

    def test_get_product_by_id_not_found(self):
        r = client.get("/api/v1/products/PROD-NONEXIST")
        assert r.status_code == 404

    def test_holdings_maturing_returns_results(self):
        r = client.get("/api/v1/clients/holdings/maturing?product_types=bond,bond_fund&within_days=365")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0
        for item in data:
            assert "client_id" in item
            assert "product_id" in item
            assert "days_to_mature" in item

    def test_holdings_maturing_default_params(self):
        r = client.get("/api/v1/clients/holdings/maturing")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestInvestorReadiness:
    """GET /api/v1/clients/readiness"""

    def test_returns_ranked_clients(self):
        """Readiness endpoint returns clients sorted by score."""
        r = client.get("/api/v1/clients/readiness?top_n=10")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert data[0]["rank"] == 1
        assert "client_id" in data[0]
        assert "name" in data[0]
        assert "investor_readiness_score" in data[0]
        assert "cash_score" in data[0]
        assert "concentration_score" in data[0]
        assert "active_score" in data[0]
        assert "life_stage_score" in data[0]

    def test_top_n_limits_results(self):
        """top_n=1 returns only the first result."""
        r = client.get("/api/v1/clients/readiness?top_n=1")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_default_returns_all(self):
        """No top_n returns all results."""
        r = client.get("/api/v1/clients/readiness")
        assert r.status_code == 200
        assert len(r.json()) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# POST endpoints — Client search
# ═══════════════════════════════════════════════════════════════════════════


class TestClientSearch:
    """POST /api/v1/clients/search"""

    # ── All five filters combined (Swagger example) ──────────────────────

    def test_all_filters_combined_returns_clients(self):
        """Swagger pre-filled example: all 5 filters, verified to return 9 clients."""
        r = client.post("/api/v1/clients/search", json={
            "risk_rating": [1, 3],
            "age": [35, 70],
            "product_types_in_holdings": "bond",
            "concentration_score": [6, 10],
            "cash_score": [0, 5],
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 9
        for c in data:
            assert "client_id" in c
            assert "name" in c
            assert 1 <= c["risk_rating"] <= 3

    # ── Individual filters ──────────────────────────────────────────────

    def test_single_risk_rating(self):
        r = client.post("/api/v1/clients/search", json={"risk_rating": 3})
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 4
        for c in data:
            assert c["risk_rating"] == 3

    def test_range_risk_rating(self):
        r = client.post("/api/v1/clients/search", json={"risk_rating": [2, 4]})
        assert r.status_code == 200
        assert len(r.json()) == 13

    def test_product_types_in_holdings_single(self):
        r = client.post("/api/v1/clients/search", json={"product_types_in_holdings": "bond"})
        assert r.status_code == 200
        assert len(r.json()) == 18

    def test_product_types_in_holdings_list(self):
        r = client.post("/api/v1/clients/search", json={"product_types_in_holdings": ["bond", "equity"]})
        assert r.status_code == 200
        assert len(r.json()) == 23

    def test_product_types_in_holdings_string_equity(self):
        r = client.post("/api/v1/clients/search", json={"product_types_in_holdings": "equity"})
        assert r.status_code == 200
        assert len(r.json()) == 21

    def test_product_types_in_holdings_string_cash(self):
        r = client.post("/api/v1/clients/search", json={"product_types_in_holdings": "cash"})
        assert r.status_code == 200
        assert len(r.json()) == 9

    def test_age_range(self):
        r = client.post("/api/v1/clients/search", json={"age": [35, 70]})
        assert r.status_code == 200
        for c in r.json():
            assert 35 <= c["age"] <= 70

    def test_cash_score_range(self):
        r = client.post("/api/v1/clients/search", json={"cash_score": [0, 3]})
        assert r.status_code == 200
        assert len(r.json()) == 17

    def test_concentration_score_range(self):
        r = client.post("/api/v1/clients/search", json={"concentration_score": [6, 10]})
        assert r.status_code == 200
        assert len(r.json()) == 23

    # ── Edge cases ──────────────────────────────────────────────────────

    def test_empty_body_returns_all_clients(self):
        r = client.post("/api/v1/clients/search", json={})
        assert r.status_code == 200
        assert len(r.json()) == 23

    def test_no_matching_filters_returns_empty(self):
        r = client.post("/api/v1/clients/search", json={"age": [1, 17]})
        assert r.status_code == 200
        assert r.json() == []

    def test_422_on_invalid_type(self):
        r = client.post("/api/v1/clients/search", json={"risk_rating": "not_a_number"})
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# POST endpoints — Product search
# ═══════════════════════════════════════════════════════════════════════════


class TestProductSearch:
    """POST /api/v1/products/search"""

    def test_search_returns_results(self):
        r = client.post("/api/v1/products/search", json={
            "query": {"risk_rating": 1, "expected_return": 3.7, "product_type": "bond"},
            "top_n": 3,
            "exclude_product_ids": ["PROD053"],
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data["results"]) == 3
        for p in data["results"]:
            assert p["product_id"] != "PROD053"
            assert "similarity_score" in p


class TestReinvestmentCandidates:
    """POST /api/v1/products/reinvestment-candidates"""

    def test_returns_candidates(self):
        r = client.post("/api/v1/products/reinvestment-candidates", json={
            "client_ids": ["PB-HK-000007-5"],
            "source_product_id": "PROD053",
        })
        assert r.status_code == 200
        data = r.json()
        candidates = data["results_by_client"]["PB-HK-000007-5"]
        assert len(candidates) == 7
        for c in candidates:
            assert "product_id" in c
            assert "similarity_score" in c

    def test_422_missing_required(self):
        r = client.post("/api/v1/products/reinvestment-candidates", json={})
        assert r.status_code == 422


class TestFitnessScore:
    """POST /api/v1/products/fitness-score"""

    def test_returns_scores(self):
        r = client.post("/api/v1/products/fitness-score", json={
            "client_ids": ["PB-HK-000007-5"],
            "product_ids": ["PROD054", "ETF-BIL", "ETF-SHV"],
        })
        assert r.status_code == 200
        data = r.json()
        assert len(data["results"]) == 3
        for item in data["results"]:
            assert "fitness_score" in item
            assert "component_scores" in item
            cs = item["component_scores"]
            for dim in ("risk_rating_match_score", "concentration_score",
                        "has_similar_investment_experience_score", "better_product_score"):
                assert dim in cs, f"Missing component score: {dim}"
                assert isinstance(cs[dim], (int, float)), f"{dim} is not a number"
