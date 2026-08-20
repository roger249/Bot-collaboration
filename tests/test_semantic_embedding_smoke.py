"""End-to-end smoke test — scorecard generation for human examination.

Implements the "Manual scorecard smoke test" acceptance criterion from
``docs/specification/scorecard/semantic_embedding.md``.

Revised to surface the semantic-similarity spread that matters for human
review: select **2 random clients** against the **full product catalog**, run
PFS end-to-end, and emit each client's **top-K and bottom-K** products ranked
by ``sum(similarity_*)`` — so a human can eyeball whether the similarity
features actually separate good from bad fits.

This is a *slow* test (loads the real sentence-transformer model and the real
DuckDB), so it is skipped unless ``--run-slow`` is passed::

    ./.venv/bin/python -m pytest tests/test_semantic_embedding_smoke.py --run-slow

Output is written to ``test_output/semantic_embedding_scorecard.json`` for
human inspection.  It does NOT assert on the score *values* (which depend on
the embedding model) — only on the response structure.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

DB_PATH = Path("data/planbot/db/planbot.duckdb")
OUTPUT_PATH = Path("test_output/semantic_embedding_scorecard.json")

N_CLIENTS = 2        # random clients to inspect
TOP_K = 10           # top-K products per client
BOTTOM_K = 10        # bottom-K products per client

# The four similarity dimensions summed to produce the ranking key.
SIMILARITY_DIMS = (
    "similarity_product_note_in_like_products",
    "similarity_product_note_in_dislike_products",
    "similarity_to_current_holding",
    "similarity_to_RM_note",
)


def _sum_similarity(row: dict) -> float:
    cs = row["component_scores"]
    return sum(cs.get(d, 0.0) for d in SIMILARITY_DIMS)


def _trim_row(row: dict) -> dict:
    """Keep only the similarity dimensions, plus a total similarity score."""
    cs = row["component_scores"]
    similarity = {d: cs.get(d, 0.0) for d in SIMILARITY_DIMS}
    trimmed = {k: v for k, v in row.items() if k != "component_scores"}
    trimmed["total_similarity_score"] = round(sum(similarity.values()), 4)
    trimmed["component_scores"] = similarity
    return trimmed


def _build_scorecard(results: list[dict], client_ids: list[str]) -> dict:
    """Group results per client, rank by sum(similarity_*), and pick top/bottom K."""
    scorecard: dict[str, dict] = {}
    for cid in client_ids:
        rows = [r for r in results if r["client_id"] == cid]
        rows.sort(key=_sum_similarity, reverse=True)
        trimmed = [_trim_row(r) for r in rows]
        scorecard[cid] = {
            "client_id": cid,
            "total_products_scored": len(trimmed),
            "top": trimmed[:TOP_K],
            "bottom": trimmed[-BOTTOM_K:] if len(trimmed) > BOTTOM_K else [],
        }
    return scorecard


@pytest.mark.slow
def test_generate_scorecard_for_human_examination():
    """Write a top-K/bottom-K similarity scorecard for human review."""
    if not DB_PATH.exists():
        pytest.skip(f"DuckDB not found at {DB_PATH}")

    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        client_ids = [
            r[0]
            for r in conn.execute(
                "SELECT client_id FROM clients ORDER BY random() LIMIT ?", [N_CLIENTS]
            ).fetchall()
        ]
        product_ids = [
            r[0]
            for r in conn.execute(
                "SELECT product_id FROM products WHERE investment_note IS NOT NULL "
                "ORDER BY product_id"
            ).fetchall()
        ]
    finally:
        conn.close()

    if not client_ids or not product_ids:
        pytest.skip("No clients/products in DuckDB")

    from src.integrations.product_tool import search_product_by_fitness_score

    result = search_product_by_fitness_score(
        client_ids=client_ids,
        product_ids=product_ids,
        top_n=len(product_ids) * len(client_ids),  # return every scored pair
    )

    # ── Structural assertions (not value assertions) ───────────────────
    assert "results" in result
    assert "meta" in result
    assert "warnings" in result
    for row in result["results"]:
        assert set(
            (
                "client_id",
                "product_id",
                "product_name",
                "investment_note",
                "fitness_score",
                "component_scores",
                "client_like_products",
                "client_dislike_products",
                "client_rm_note",
            )
        ).issubset(row.keys())
        cs = row["component_scores"]
        for dim in SIMILARITY_DIMS:
            assert 0 <= cs[dim] <= 10, f"{dim} out of range: {cs[dim]}"

    # ── Build the top-K/bottom-K scorecard artifact ────────────────────
    scorecard = _build_scorecard(result["results"], client_ids)
    artifact = {
        "criteria": {
            "clients": N_CLIENTS,
            "top_k": TOP_K,
            "bottom_k": BOTTOM_K,
            "ranking_key": f"sum({', '.join(SIMILARITY_DIMS)})",
        },
        "meta": result.get("meta"),
        "warnings": result.get("warnings"),
        "clients": scorecard,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, ensure_ascii=False))
    assert OUTPUT_PATH.exists()
