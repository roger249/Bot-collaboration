"""Demo control helpers — HTTP-only test-data mutation for demos/tests.

The proposal read path uses a read-only DuckDB adapter; this module owns a
transient **read-write** connection used only for demo mutation/reset.  Each
operation opens, mutates, commits, and closes within a single call so it does
not hold a lock across requests.

Gated by ``demo_tools.enabled`` in ``config/config_planbot.yaml`` (default true).
In bank-REST mode (``common.get_client_product_from_restapi: true``) there is no
DuckDB to mutate, so the endpoints refuse with a clear message.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb
import yaml

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"

# Canonical baseline restored by reset(): (table, key_column, key, column) → value.
# Sourced from the seeders / docs/how_to/how_to_add_fx_tarf.md.
_DEMO_CANONICAL_BASELINE: dict[tuple[str, str, str, str], Any] = {
    (
        "clients",
        "client_id",
        "PB-HK-000001-8",
        "qualitative_profile",
    ): (
        "Experienced executive with strong income stream. Actively manages "
        "portfolio; prefers evidence-based decisions. Open to structured "
        "products and tactical equity plays. Has expressed concern about "
        "inflation eroding idle cash. Two children approaching university "
        "age — education funding is a near-term priority."
    ),
}


def _load_config() -> dict:
    return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def is_enabled() -> bool:
    cfg = _load_config()
    return bool((cfg.get("demo_tools") or {}).get("enabled", True))


def _is_rest_mode() -> bool:
    cfg = _load_config()
    return bool(cfg.get("common", {}).get("get_client_product_from_restapi", False))


def _db_path() -> Path:
    cfg = _load_config()
    raw = (
        cfg.get("data_source", {})
        .get("duckdb", {})
        .get("path", "data/planbot/db/planbot.duckdb")
    )
    return (_ROOT_DIR / raw).resolve()


def _mutate(sql: str, params: list[Any]) -> None:
    """Run one write statement on a transient read-write connection."""
    conn = duckdb.connect(str(_db_path()), read_only=False)
    try:
        conn.execute(sql, params)
    finally:
        conn.close()


def _fetch_one(sql: str, params: list[Any]) -> Any:
    conn = duckdb.connect(str(_db_path()), read_only=True)
    try:
        row = conn.execute(sql, params).fetchone()
        return row
    finally:
        conn.close()


def patch_client_note(client_id: str, note: str) -> dict:
    """Set a client's ``qualitative_profile``, returning previous + new value."""
    if not is_enabled():
        raise RuntimeError("demo_tools disabled")
    if _is_rest_mode():
        raise RuntimeError("demo_tools require DuckDB mode (get_client_product_from_restapi=false)")

    row = _fetch_one(
        "SELECT qualitative_profile FROM clients WHERE client_id = ?",
        [client_id],
    )
    if row is None:
        raise KeyError(client_id)

    previous = row[0]
    _mutate(
        "UPDATE clients SET qualitative_profile = ? WHERE client_id = ?",
        [note, client_id],
    )
    return {
        "client_id": client_id,
        "qualitative_profile": note,
        "previous_qualitative_profile": previous,
    }


def reset_demo() -> dict:
    """Restore all demo-mutated data to the canonical baseline (idempotent)."""
    if not is_enabled():
        raise RuntimeError("demo_tools disabled")
    if _is_rest_mode():
        raise RuntimeError("demo_tools require DuckDB mode (get_client_product_from_restapi=false)")

    restored: list[str] = []
    for (table, key_col, key, column), value in _DEMO_CANONICAL_BASELINE.items():
        _mutate(
            f"UPDATE {table} SET {column} = ? WHERE {key_col} = ?",
            [value, key],
        )
        restored.append(f"{table}.{column}:{key}")

    return {"status": "reset", "restored": restored}
