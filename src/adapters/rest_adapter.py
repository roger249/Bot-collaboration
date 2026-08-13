"""Bank REST data adapter — raw data retrieval over HTTP.

Implements the ``DataAdapter`` protocol by calling bank-internal REST endpoints.
Shape-mapping only: JSON → ``list[dict]``, no business logic.

Error handling contract:
- ``5xx`` / ``429`` / ``401`` → raise (backend broken / rate-limited / unauthorized).
- ``404`` → return ``[]`` (resource genuinely missing).
- Connection errors → raise.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from cachetools import TTLCache

LOGGER = logging.getLogger(__name__)


def _make_key(resource: str, ids: list[str] | None, limit: int | None, offset: int) -> tuple:
    """Stable cache key.  ``ids`` is sorted so order-invariant."""
    return (resource, tuple(sorted(ids)) if ids else None, limit, offset)


class BankRestDataAdapter:
    """REST client for bank CRM / custody / product-master.

    One instance serves one backend host.  ``clients_path`` / ``holdings_path`` /
    ``products_path`` let the factory point at per-domain resources; defaults
    follow the doc's bank-style layout.
    """

    def __init__(
        self,
        base_url: str,
        auth_token: str | None = None,
        *,
        timeout: float = 10.0,
        cache_ttl: int = 300,
        cache_maxsize: int = 512,
        clients_path: str = "/crm/clients",
        holdings_path: str = "/custody/holdings",
        products_path: str = "/product-master/products",
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._auth_token = auth_token
        self._timeout = timeout
        self._clients_path = clients_path
        self._holdings_path = holdings_path
        self._products_path = products_path
        self._transport = transport
        self._cache: TTLCache[tuple, list[dict]] | None = (
            TTLCache(maxsize=cache_maxsize, ttl=cache_ttl) if cache_ttl > 0 else None
        )

    # ── HTTP helper ────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        if self._auth_token:
            return {"Authorization": f"Bearer {self._auth_token}"}
        return {}

    def _request(self, path: str, params: dict[str, Any] | None) -> list[dict]:
        url = f"{self._base_url}{path}"
        with httpx.Client(transport=self._transport, timeout=httpx.Timeout(self._timeout)) as client:
            LOGGER.debug("HTTP GET %s params=%s", url, params)
            response = client.get(url, params=params, headers=self._headers())
            if response.status_code == 404:
                # Resource genuinely missing → empty, not an error.
                return []
            response.raise_for_status()  # 5xx/429/401/other → raise
            data = response.json()
            # Accept both a bare list and a wrapped {"items": [...]}.
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data["items"]
            LOGGER.warning("Unexpected REST response shape from %s: %r", url, data)
            return []

    # ── generic cached fetch ──────────────────────────────────────────

    def _fetch(
        self,
        resource: str,
        path: str,
        ids: list[str] | None,
        *,
        limit: int | None,
        offset: int,
        id_param: str,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if ids:
            # Comma-separated list — the simulator/bank splits it server-side.
            params[id_param] = ",".join(ids)
        if offset:
            params["offset"] = offset
        if limit is not None:
            params["limit"] = limit

        if self._cache is None:
            return self._request(path, params)

        key = _make_key(resource, ids, limit, offset)
        try:
            return self._cache[key]
        except KeyError:
            data = self._request(path, params)
            self._cache[key] = data
            return data

    # ── DataAdapter interface ─────────────────────────────────────────

    def fetch_clients(
        self,
        client_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        return self._fetch(
            "clients", self._clients_path, client_ids,
            limit=limit, offset=offset, id_param="client_id",
        )

    def fetch_holdings(
        self,
        client_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        return self._fetch(
            "holdings", self._holdings_path, client_ids,
            limit=limit, offset=offset, id_param="client_id",
        )

    def fetch_products(
        self,
        product_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        return self._fetch(
            "products", self._products_path, product_ids,
            limit=limit, offset=offset, id_param="product_id",
        )

    def health_check(self) -> bool:
        try:
            self._request(self._clients_path, {"limit": 1})
            return True
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Bank REST health check failed: %s", exc)
            return False
