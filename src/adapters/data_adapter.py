"""Data Adapter Protocol + factory.

Layer 1 (DAL).  Adapters return plain ``list[dict]`` — no business logic.
"""

from __future__ import annotations

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
    ``true`` → bank REST (Sprint 2).
    """
    from src.adapters.duckdb_adapter import DuckDBDataAdapter

    use_rest = bool(config.get("common", {}).get("get_client_product_from_restapi", False))
    if use_rest:
        # Sprint 2: bank REST adapters.
        raise NotImplementedError(
            "Bank REST adapters are not implemented yet (Sprint 2). "
            "Set common.get_client_product_from_restapi to false for DuckDB."
        )

    db_path = (
        config.get("data_source", {}).get("duckdb", {}).get(
            "path", "data/planbot/db/planbot.duckdb"
        )
    )
    adapter = DuckDBDataAdapter(Path(db_path))
    return adapter, adapter  # same instance serves client and product
