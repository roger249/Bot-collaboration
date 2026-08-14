"""DuckDB data adapter — raw row retrieval from ``planbot.duckdb``.

Shape mapping only: ``SELECT *`` → ``list[dict]``.  JSON columns
(``type_specific``, ``performance_history``) are parsed to dicts here so the
Logic Layer receives plain dicts with no JSON strings.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import duckdb

LOGGER = logging.getLogger(__name__)

_PRODUCT_JSON_COLUMNS = ("type_specific", "performance_history")


class DuckDBDataAdapter:
    """Read-only DuckDB adapter implementing the ``DataAdapter`` protocol."""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)

    # ── raw fetch helper ──────────────────────────────────────────────

    def _fetch(
        self,
        table: str,
        ids: list[str] | None,
        id_col: str | None,
        *,
        json_cols: tuple[str, ...] = (),
        order_by: str | None = None,
    ) -> list[dict]:
        if not self._db_path.exists():
            raise FileNotFoundError(
                f"DuckDB not found at {self._db_path}. "
                "Run the seeder (investor_readiness_score.py / product_catalog_seed.py) first."
            )
        conn = duckdb.connect(str(self._db_path), read_only=True)
        try:
            conn.execute("PRAGMA enable_progress_bar=false;")
            query = f"SELECT * FROM {table}"
            params: list[Any] = []
            if ids and id_col:
                placeholders = ",".join("?" for _ in ids)
                query += f" WHERE {id_col} IN ({placeholders})"
                params = list(ids)
            if order_by:
                query += f" ORDER BY {order_by}"
            cursor = conn.execute(query, params)
            cols = [d[0] for d in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
            for row in rows:
                for jc in json_cols:
                    raw = row.get(jc)
                    row[jc] = json.loads(raw) if isinstance(raw, str) else (raw or {})
                for k, v in row.items():
                    if isinstance(v, float):
                        row[k] = round(v, 4)
            return rows
        finally:
            conn.close()

    # ── DataAdapter interface ─────────────────────────────────────────

    def fetch_clients(
        self,
        client_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        rows = self._fetch("clients", client_ids, "client_id", order_by="client_id")
        return rows[offset : offset + limit] if limit is not None else rows[offset:]

    def fetch_holdings(
        self,
        client_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        rows = self._fetch(
            "holdings", client_ids, "client_id",
            order_by="client_id, holding_idx",
        )
        return rows[offset : offset + limit] if limit is not None else rows[offset:]

    def fetch_products(
        self,
        product_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        rows = self._fetch(
            "products", product_ids, "product_id", json_cols=_PRODUCT_JSON_COLUMNS,
            order_by="product_id",
        )
        return rows[offset : offset + limit] if limit is not None else rows[offset:]

    def health_check(self) -> bool:
        try:
            self._fetch("clients", None, None)
            return True
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("DuckDB health check failed: %s", exc)
            return False
