"""Tests for the BankRestDataAdapter (Sprint 2, Task 4).

Uses ``httpx.MockTransport`` to simulate bank responses without a live server.
Covers the error-handling contract, pagination, auth header, and TTL caching.
"""

from __future__ import annotations

import httpx
import pytest

from src.adapters.rest_adapter import BankRestDataAdapter


def _handler_for(routes: dict) -> callable:
    """Build an httpx request handler that looks up a route by (method, path)."""

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        if key in routes:
            return routes[key](request)
        return httpx.Response(404, json={"detail": "not found"})

    return handler


def _json_list(items: list[dict]):
    return httpx.Response(200, json=items)


class TestFetchClients:
    def test_returns_list(self):
        adapter = BankRestDataAdapter(
            "https://bank.test",
            transport=httpx.MockTransport(
                _handler_for({("GET", "/crm/clients"): lambda r: _json_list([{"client_id": "C1"}])})
            ),
        )
        assert adapter.fetch_clients() == [{"client_id": "C1"}]

    def test_passes_client_id_and_pagination(self):
        captured: dict = {}

        def h(req):
            captured["params"] = dict(req.url.params)
            return _json_list([{"client_id": "C1"}])

        adapter = BankRestDataAdapter(
            "https://bank.test", transport=httpx.MockTransport(_handler_for({("GET", "/crm/clients"): h}))
        )
        adapter.fetch_clients(["C1", "C2"], limit=10, offset=5)
        assert captured["params"]["client_id"] == "C1,C2"
        assert captured["params"]["limit"] == "10"
        assert captured["params"]["offset"] == "5"

    def test_sends_bearer_auth(self):
        captured: dict = {}

        def h(req):
            captured["auth"] = req.headers.get("authorization")
            return _json_list([])

        adapter = BankRestDataAdapter(
            "https://bank.test",
            auth_token="sekret",
            transport=httpx.MockTransport(_handler_for({("GET", "/crm/clients"): h})),
        )
        adapter.fetch_clients()
        assert captured["auth"] == "Bearer sekret"


class TestErrorHandling:
    def test_404_returns_empty(self):
        adapter = BankRestDataAdapter(
            "https://bank.test",
            transport=httpx.MockTransport(lambda req: httpx.Response(404)),
        )
        assert adapter.fetch_clients(["C1"]) == []

    def test_500_raises(self):
        adapter = BankRestDataAdapter(
            "https://bank.test",
            transport=httpx.MockTransport(lambda req: httpx.Response(500)),
        )
        with pytest.raises(httpx.HTTPStatusError):
            adapter.fetch_clients()

    def test_401_raises(self):
        adapter = BankRestDataAdapter(
            "https://bank.test",
            transport=httpx.MockTransport(lambda req: httpx.Response(401)),
        )
        with pytest.raises(httpx.HTTPStatusError):
            adapter.fetch_products()

    def test_health_check_false_on_error(self):
        adapter = BankRestDataAdapter(
            "https://bank.test",
            transport=httpx.MockTransport(lambda req: httpx.Response(500)),
        )
        assert adapter.health_check() is False


class TestCaching:
    def test_ttl_cache_hits(self):
        calls = {"n": 0}

        def h(req):
            calls["n"] += 1
            return _json_list([{"client_id": "C1"}])

        adapter = BankRestDataAdapter(
            "https://bank.test",
            cache_ttl=300,
            transport=httpx.MockTransport(_handler_for({("GET", "/crm/clients"): h})),
        )
        adapter.fetch_clients(["C1"])
        adapter.fetch_clients(["C1"])
        assert calls["n"] == 1  # second call served from cache

    def test_cache_disabled_when_ttl_zero(self):
        calls = {"n": 0}

        def h(req):
            calls["n"] += 1
            return _json_list([{"client_id": "C1"}])

        adapter = BankRestDataAdapter(
            "https://bank.test",
            cache_ttl=0,
            transport=httpx.MockTransport(_handler_for({("GET", "/crm/clients"): h})),
        )
        adapter.fetch_clients(["C1"])
        adapter.fetch_clients(["C1"])
        assert calls["n"] == 2  # cache disabled — both hit the transport

    def test_wrapped_items_shape(self):
        adapter = BankRestDataAdapter(
            "https://bank.test",
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"items": [{"client_id": "C1"}]})
            ),
        )
        assert adapter.fetch_clients() == [{"client_id": "C1"}]
