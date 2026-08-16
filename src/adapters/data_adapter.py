"""Data Adapter Protocol + factory.

Layer 1 (DAL).  Adapters return plain ``list[dict]`` — no business logic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class DataAdapter(Protocol):
    """Raw data provider. Returns plain dicts — no business logic."""

    def fetch_clients(
        self,
        client_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]: ...

    def fetch_holdings(
        self,
        client_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]: ...

    def fetch_products(
        self,
        product_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]: ...

    def health_check(self) -> bool:
        """Return True if the backend is reachable."""
        ...


def build_data_adapters(config: dict) -> tuple[DataAdapter, DataAdapter]:
    """Build client + product adapters from ``config_planbot.yaml``.

    ``get_client_product_from_restapi: false`` (default) → DuckDB (self-contained).
    ``true`` → bank REST adapters (Sprint 2).

    The REST base URLs may be overridden per deployment via environment
    variables (12-factor style).  Each falls back to the YAML value when
    unset:

      * ``DATA_CLIENT_BASE_URL``  → ``data_source.rest.client_base_url``
      * ``DATA_PRODUCT_BASE_URL`` → ``data_source.rest.product_base_url``
    """
    from src.adapters.duckdb_adapter import DuckDBDataAdapter
    from src.adapters.rest_adapter import BankRestDataAdapter

    use_rest = bool(config.get("common", {}).get("get_client_product_from_restapi", False))
    if not use_rest:
        db_path = (
            config.get("data_source", {}).get("duckdb", {}).get(
                "path", "data/planbot/db/planbot.duckdb"
            )
        )
        adapter = DuckDBDataAdapter(Path(db_path))
        return adapter, adapter  # same instance serves client and product

    # ── Bank REST path ────────────────────────────────────────────────
    rest = config.get("data_source", {}).get("rest", {})
    auth_token_env = rest.get("auth_token_env")
    auth_token = os.environ.get(auth_token_env) if auth_token_env else None

    timeout = rest.get("timeout_seconds", 10)
    cache_ttl = rest.get("cache_ttl_seconds", 300)
    cache_maxsize = rest.get("cache_maxsize", 512)

    # Env var wins over YAML; YAML is the fallback default.
    client_base = os.environ.get("DATA_CLIENT_BASE_URL") or rest.get("client_base_url")
    product_base = os.environ.get("DATA_PRODUCT_BASE_URL") or rest.get("product_base_url")
    if not client_base or not product_base:
        raise ValueError(
            "data_source.rest requires client_base_url and product_base_url "
            "when get_client_product_from_restapi is true."
        )

    client_adapter = BankRestDataAdapter(
        base_url=client_base,
        auth_token=auth_token,
        timeout=timeout,
        cache_ttl=cache_ttl,
        cache_maxsize=cache_maxsize,
        clients_path=rest.get("clients_path", "/api/v1/clients"),
        holdings_path=rest.get("holdings_path", "/api/v1/holdings"),
    )
    product_adapter = BankRestDataAdapter(
        base_url=product_base,
        auth_token=auth_token,
        timeout=timeout,
        cache_ttl=cache_ttl,
        cache_maxsize=cache_maxsize,
        products_path=rest.get("products_path", "/api/v1/products"),
    )
    return client_adapter, product_adapter
