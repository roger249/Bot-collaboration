"""Tests for the Bank API Simulator (raw data endpoints).

Sprint 2: the Data API server is now a pure bank simulator exposing only raw
client / holding / product data.  Business-logic endpoints (search, readiness,
maturing, similarity, reinvestment-candidates, fitness-score) are removed and
must be exercised via the Python Logic Layer instead.

These tests use ``TestClient`` (in-process) against the simulator's DuckDB-backed
raw data.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.integrations.data_server import app

client = TestClient(app)


class TestClients:
    def test_list_clients_returns_rows(self):
        r = client.get("/api/v1/clients")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "client_id" in data[0]

    def test_list_clients_filter_by_id(self):
        r = client.get("/api/v1/clients?client_id=PB-HK-000007-5")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["client_id"] == "PB-HK-000007-5"

    def test_list_clients_filter_multiple_ids(self):
        r = client.get("/api/v1/clients?client_id=PB-HK-000007-5,PB-HK-000001-8")
        assert r.status_code == 200
        data = r.json()
        assert {c["client_id"] for c in data} == {"PB-HK-000007-5", "PB-HK-000001-8"}

    def test_get_client_by_id_returns_raw_row(self):
        r = client.get("/api/v1/clients/PB-HK-000007-5")
        assert r.status_code == 200
        data = r.json()
        assert data["client_id"] == "PB-HK-000007-5"
        assert "name" in data
        # Raw row — no nested holdings (holdings are a separate endpoint).
        assert "holdings" not in data

    def test_get_client_not_found(self):
        r = client.get("/api/v1/clients/PB-HK-NONEXIST")
        assert r.status_code == 404


class TestHoldings:
    def test_list_holdings_returns_rows(self):
        r = client.get("/api/v1/holdings")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "client_id" in data[0]
        assert "product_id" in data[0]

    def test_list_holdings_filter_by_client(self):
        r = client.get("/api/v1/holdings?client_id=PB-HK-000007-5")
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        assert all(h["client_id"] == "PB-HK-000007-5" for h in data)


class TestProducts:
    def test_list_products_returns_rows(self):
        r = client.get("/api/v1/products")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "product_id" in data[0]

    def test_list_products_filter_by_id(self):
        r = client.get("/api/v1/products?product_id=PROD053")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["product_id"] == "PROD053"

    def test_get_product_by_id(self):
        r = client.get("/api/v1/products/PROD053")
        assert r.status_code == 200
        data = r.json()
        assert data["product_id"] == "PROD053"
        assert "risk_rating" in data

    def test_get_product_not_found(self):
        r = client.get("/api/v1/products/PROD-NONEXIST")
        assert r.status_code == 404


class TestRemovedBusinessEndpoints:
    """Business-logic endpoints must be gone (moved to Python Logic Layer)."""

    def test_search_removed(self):
        assert client.post("/api/v1/clients/search", json={}).status_code in (404, 405)

    def test_readiness_removed(self):
        assert client.get("/api/v1/clients/readiness").status_code in (404, 405)

    def test_holdings_maturing_removed(self):
        assert client.get("/api/v1/clients/holdings/maturing").status_code in (404, 405)

    def test_search_similar_removed(self):
        assert client.post("/api/v1/products/search-similar", json={}).status_code in (404, 405)

    def test_reinvestment_candidates_removed(self):
        assert client.post("/api/v1/products/reinvestment-candidates", json={}).status_code in (404, 405)

    def test_fitness_score_removed(self):
        assert client.post("/api/v1/products/fitness-score", json={}).status_code in (404, 405)
