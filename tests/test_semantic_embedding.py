"""Unit tests for semantic embedding — embedder, similarity features, and store.

Covers the two required test classes per repo standard: normal flow and
exception condition.  Uses the deterministic ``HashEmbedder`` (no trained
model needed) so tests run offline and repeatably.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.planbot.semantic_embedding import (
    HashEmbedder,
    compute_content_hash,
    compute_similarity_features,
    cosine_sim,
    map_sim_to_score,
    similarity_scores_from_embeddings,
)
from src.planbot.embeddings_store import EmbeddingStore


class TestSemanticEmbeddingNormalFlow(unittest.TestCase):
    def setUp(self):
        self.embedder = HashEmbedder(dim=128, model_id="hash")

    def test_identical_text_cosine_is_one(self):
        v = self.embedder.embed("technology growth fund")
        self.assertAlmostEqual(cosine_sim(v, v), 1.0, places=5)

    def test_hash_embedder_is_deterministic(self):
        self.assertEqual(self.embedder.embed("ESG"), self.embedder.embed("ESG"))

    def test_map_sim_to_score_minmax(self):
        # floor→0, ceiling→10, linear in between
        self.assertEqual(map_sim_to_score(0.6, floor=0.6, ceiling=0.84), 0.0)
        self.assertEqual(map_sim_to_score(0.84, floor=0.6, ceiling=0.84), 10.0)
        self.assertEqual(map_sim_to_score(0.72, floor=0.6, ceiling=0.84), 5.0)
        # inverted term (dislike/comfort)
        self.assertEqual(map_sim_to_score(0.84, invert=True, floor=0.6, ceiling=0.84), 0.0)
        self.assertEqual(map_sim_to_score(0.6, invert=True, floor=0.6, ceiling=0.84), 10.0)

    def test_map_sim_to_score_floor_ceiling_calibration(self):
        # Clamping: below floor → 0, above ceiling → 10.
        self.assertEqual(map_sim_to_score(0.5, floor=0.6, ceiling=0.84), 0.0)
        self.assertEqual(map_sim_to_score(0.9, floor=0.6, ceiling=0.84), 10.0)
        # Monotonic across the calibrated band.
        self.assertLess(
            map_sim_to_score(0.65, floor=0.6, ceiling=0.84),
            map_sim_to_score(0.75, floor=0.6, ceiling=0.84),
        )
        # Inverted: below floor (irrelevant) → 10; at ceiling (match) → 0.
        self.assertEqual(map_sim_to_score(0.5, invert=True, floor=0.6, ceiling=0.84), 10.0)
        self.assertEqual(map_sim_to_score(0.84, invert=True, floor=0.6, ceiling=0.84), 0.0)

    def test_compute_similarity_features_like_matches_product(self):
        client = {
            "like_products": ["technology", "AI"],
            "dislike_products": ["bonds"],
            "qualitative_profile": "wants growth and AI exposure",
        }
        product = {
            "name": "AI Technology Growth Fund",
            "investment_note": "High-growth AI and technology equities",
        }
        scores = compute_similarity_features(self.embedder, client, product, [])
        for k, v in scores.items():
            self.assertGreaterEqual(v, 0.0, f"{k} below 0: {v}")
            self.assertLessEqual(v, 10.0, f"{k} above 10: {v}")
        # product investment_note shares vocabulary with the stated like → signal
        self.assertGreater(scores["similarity_product_note_in_like_products"], 0.0)
        # product does NOT match the stated dislike ("bonds") → high comfort.
        self.assertGreater(scores["similarity_product_note_in_dislike_products"], 5.0)

    def test_empty_inputs_are_neutral(self):
        scores = similarity_scores_from_embeddings(
            prod_name_emb=None,
            prod_note_emb=None,
            like_embs=[],
            dislike_embs=[],
            hold_note_embs=[],
            rm_emb=None,
        )
        for v in scores.values():
            self.assertEqual(v, 5.0)

    def test_rm_note_matches_product_name_when_note_missing(self):
        # RM note should still match when only the product name is available.
        name = self.embedder.embed("Technology Growth Fund")
        rm = self.embedder.embed("Technology Growth Fund")
        scores = similarity_scores_from_embeddings(
            prod_name_emb=name,
            prod_note_emb=None,
            like_embs=[],
            dislike_embs=[],
            hold_note_embs=[],
            rm_emb=rm,
        )
        # Identical text → cosine 1.0 → top score, proving the name is used.
        self.assertEqual(scores["similarity_to_RM_note"], 10.0)

    def test_rm_note_uses_max_of_name_and_note(self):
        # When both surfaces exist, the RM note should align with the stronger
        # of the product name vs. its investment_note (here, the name).
        name = self.embedder.embed("Technology Growth Fund")
        note = self.embedder.embed("bonds income fixed")
        rm = self.embedder.embed("Technology Growth Fund")
        scores = similarity_scores_from_embeddings(
            prod_name_emb=name,
            prod_note_emb=note,
            like_embs=[],
            dislike_embs=[],
            hold_note_embs=[],
            rm_emb=rm,
        )
        self.assertEqual(scores["similarity_to_RM_note"], 10.0)

    def test_similarity_scores_uses_per_feature_bounds(self):
        # Each feature maps through its own (floor, ceiling); an unset feature
        # falls back to the identity mapping.
        note = self.embedder.embed("High-growth AI and technology equities")
        like = self.embedder.embed("technology")
        rm = self.embedder.embed("High-growth AI and technology equities")
        bounds = {
            "like": (0.6, 0.84),
            "dislike": (0.6, 0.84),
            "holding": (0.6, 0.84),
            # "rm" omitted → identity mapping (0.0, 1.0)
        }
        scores = similarity_scores_from_embeddings(
            prod_name_emb=rm,
            prod_note_emb=note,
            like_embs=[like],
            dislike_embs=[],
            hold_note_embs=[],
            rm_emb=rm,
            bounds=bounds,
        )
        # note↔"technology" cosine ~0.43 < floor 0.6 → clipped to 0.
        self.assertEqual(scores["similarity_product_note_in_like_products"], 0.0)
        # rm omitted from bounds → identity mapping; identical text → 10.
        self.assertEqual(scores["similarity_to_RM_note"], 10.0)


class TestSemanticEmbeddingException(unittest.TestCase):
    def test_zero_vector_cosine_returns_zero(self):
        # No division-by-zero; a zero vector yields 0 similarity.
        self.assertEqual(cosine_sim([0.0, 0.0], [1.0, 0.0]), 0.0)

    def test_map_sim_clips_out_of_range(self):
        self.assertEqual(map_sim_to_score(5.0), 10.0)   # clipped high
        self.assertEqual(map_sim_to_score(-5.0), 0.0)   # clipped low
        self.assertEqual(map_sim_to_score(5.0, invert=True), 0.0)

    def test_content_hash_stable_and_distinct(self):
        self.assertEqual(compute_content_hash("abc"), compute_content_hash("abc"))
        self.assertNotEqual(compute_content_hash("abc"), compute_content_hash("abd"))


class TestEmbeddingStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test.duckdb"
        self.embedder = HashEmbedder(dim=128, model_id="hash")
        self.store = EmbeddingStore(self.db_path)
        self.assertTrue(self.store.ensure_table())

    def tearDown(self):
        self._tmp.cleanup()

    def test_get_or_embed_caches_and_invalidates_on_change(self):
        v1 = self.store.get_or_embed(
            entity_type="product", entity_id="P1", field_name="name", field_idx=None,
            text="AI Growth Fund", embedder=self.embedder,
        )
        v2 = self.store.get_or_embed(
            entity_type="product", entity_id="P1", field_name="name", field_idx=None,
            text="AI Growth Fund", embedder=self.embedder,
        )
        self.assertEqual(v1, v2)  # unchanged text reuses the cached vector

        v3 = self.store.get_or_embed(
            entity_type="product", entity_id="P1", field_name="name", field_idx=None,
            text="Government Bond", embedder=self.embedder,
        )
        self.assertNotEqual(v1, v3)  # changed text re-embeds

    def test_get_or_embed_scalar_and_list_field_idx(self):
        v_scalar = self.store.get_or_embed(
            entity_type="client", entity_id="C1", field_name="RM_note", field_idx=None,
            text="prefers ESG", embedder=self.embedder,
        )
        v_list0 = self.store.get_or_embed(
            entity_type="client", entity_id="C1", field_name="like_products", field_idx=0,
            text="ESG", embedder=self.embedder,
        )
        self.assertIsNotNone(v_scalar)
        self.assertIsNotNone(v_list0)
        self.assertNotEqual(v_scalar, v_list0)


if __name__ == "__main__":
    unittest.main()
