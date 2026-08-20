"""Embedding vector cache — DuckDB table + get-or-embed with hash invalidation.

The ``embeddings`` table is a **derived cache**, never a source of truth.  The
current text is always re-hashed on read; a mismatch triggers re-embedding, so
the same code works whether the source is the local DuckDB now or an external
FastAPI server later (no source-provided timestamp is relied on).

A process-local in-memory dict is layered on top as a fast path so repeat PFS
calls avoid DuckDB round-trips.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb

from src.planbot.semantic_embedding import Embedder, compute_content_hash, field_role

LOGGER = logging.getLogger(__name__)

DDL_EMBEDDINGS = """
CREATE TABLE IF NOT EXISTS embeddings (
    entity_type  VARCHAR NOT NULL,
    entity_id    VARCHAR NOT NULL,
    field_name   VARCHAR NOT NULL,
    field_idx    INTEGER,
    model        VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    embedding    DOUBLE[],
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# (model, entity_type, entity_id, field_name, field_idx, content_hash) → vector
_mem_cache: dict[tuple, list[float]] = {}


def _cache_key(
    model: str,
    entity_type: str,
    entity_id: str,
    field_name: str,
    field_idx: int | None,
    content_hash: str,
) -> tuple:
    return (model, entity_type, entity_id, field_name, field_idx, content_hash)


class EmbeddingStore:
    """DuckDB-backed embedding cache with an in-memory fast path."""

    def __init__(self, db_path: str | Path, table: str = "embeddings"):
        self._db_path = Path(db_path)
        self._table = table

    def _connect(self, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(self._db_path), read_only=read_only)
        conn.execute("PRAGMA enable_progress_bar=false;")
        return conn

    def ensure_table(self) -> bool:
        """Create the embeddings table if absent.  Returns False on failure."""
        try:
            conn = self._connect()
            try:
                conn.execute(DDL_EMBEDDINGS)
                return True
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not create embeddings table (%s); using in-memory only", exc)
            return False

    def get_or_embed(
        self,
        *,
        entity_type: str,
        entity_id: str,
        field_name: str,
        field_idx: int | None,
        text: str,
        embedder: Embedder,
    ) -> list[float]:
        """Return the cached vector for ``text``, embedding only on a hash miss.

        ``content_hash`` is always recomputed from the current ``text`` (hashing
        is ~microseconds), so changed source text is detected regardless of
        where the text originated.
        """
        model = embedder.model_id
        content_hash = compute_content_hash(text)
        key = _cache_key(model, entity_type, entity_id, field_name, field_idx, content_hash)

        if key in _mem_cache:
            return _mem_cache[key]

        vec = self._lookup_db(model, entity_type, entity_id, field_name, field_idx, content_hash)
        if vec is None:
            vec = embedder.embed(text, role=field_role(field_name))
            self._upsert_db(entity_type, entity_id, field_name, field_idx, model, content_hash, vec)

        _mem_cache[key] = vec
        return vec

    # ── internal DuckDB helpers ──────────────────────────────────────────

    def _lookup_db(
        self,
        model: str,
        entity_type: str,
        entity_id: str,
        field_name: str,
        field_idx: int | None,
        content_hash: str,
    ) -> list[float] | None:
        try:
            conn = self._connect(read_only=True)
            try:
                row = conn.execute(
                    f"SELECT embedding FROM {self._table} "
                    "WHERE entity_type = ? AND entity_id = ? AND field_name = ? "
                    "AND field_idx IS NOT DISTINCT FROM ? "
                    "AND model = ? AND content_hash = ?",
                    [entity_type, entity_id, field_name, field_idx, model, content_hash],
                ).fetchone()
                return [float(x) for x in row[0]] if row and row[0] else None
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("embeddings lookup skipped: %s", exc)
            return None

    def _upsert_db(
        self,
        entity_type: str,
        entity_id: str,
        field_name: str,
        field_idx: int | None,
        model: str,
        content_hash: str,
        vec: list[float],
    ) -> None:
        try:
            conn = self._connect()
            try:
                conn.execute(
                    f"DELETE FROM {self._table} WHERE entity_type = ? AND entity_id = ? "
                    "AND field_name = ? AND field_idx IS NOT DISTINCT FROM ? AND model = ?",
                    [entity_type, entity_id, field_name, field_idx, model],
                )
                conn.execute(
                    f"INSERT INTO {self._table} "
                    "(entity_type, entity_id, field_name, field_idx, model, content_hash, embedding) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?::DOUBLE[])",
                    [entity_type, entity_id, field_name, field_idx, model, content_hash, vec],
                )
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("embeddings upsert skipped: %s", exc)


# ---------------------------------------------------------------------------
# Module-level convenience: build a store from config_screener.yaml
# ---------------------------------------------------------------------------

_STORE: EmbeddingStore | None = None


def get_embedding_store() -> EmbeddingStore:
    """Return the process-wide embedding store singleton."""
    global _STORE
    if _STORE is None:
        from src.planbot.semantic_embedding import load_screener_config

        cfg = load_screener_config().get("embedding", {}) or {}
        store_cfg = cfg.get("store", {}) or {}
        path = store_cfg.get("path", "data/planbot/db/planbot.duckdb")
        table = store_cfg.get("table", "embeddings")
        _STORE = EmbeddingStore(path, table=table)
        _STORE.ensure_table()
    return _STORE
