"""
Unit tests for reinvestment proposal module.

Tests cover:
- normal flow with valid targets
- exception/missing data handling
- response mode behavior
- optional flags (include_llm_input, include_debug_scores)
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.integrations.reinvestment_proposal import (
    propose_reinvestment,
    _build_debug_scores,
)
from src.planbot.workflow import build_llm_input, summarize_holdings


SAMPLE_CLIENT = {
    "client_id": "PB-HK-000001-8",
    "name": "Test Client",
    "aum": 5000000,
    "risk_rating": 3,
    "age": 55,
    "cash_score": 8.0,
    "concentration_score": 6.5,
    "active_score": 3.0,
    "life_stage_score": 5.0,
    "investor_readiness_score": 72.5,
    "holdings": [
        {
            "product_id": "ETF-HYG",
            "instrument_name": "High Yield Bond ETF",
            "asset_class": "fixed_income",
            "market_value": 500000,
            "yield_pct": 5.2,
            "risk_bucket": "medium",
        },
    ],
}

SAMPLE_PRODUCT = {
    "product_id": "ETF-HYG",
    "name": "High Yield Bond ETF",
    "product_type": "bond_fund",
    "risk_rating": 3,
    "expected_return": 6.0,
    "region": "US",
}

SAMPLE_CANDIDATES = {
    "results_by_client": {
        "PB-HK-000001-8": [
            {"product_id": "ETF-BND", "product_type": "bond_fund", "similarity_score": 0.92},
            {"product_id": "ETF-TIPS", "product_type": "bond_fund", "similarity_score": 0.87},
        ]
    }
}

SAMPLE_CANDIDATE_PRODUCT = {
    "product_id": "ETF-BND",
    "name": "Total Bond Market ETF",
    "product_type": "bond_fund",
    "risk_rating": 2,
    "expected_return": 4.5,
}


class TestReinvestmentProposal(unittest.TestCase):
    """Normal-flow and exception-condition tests for reinvestment proposal."""

    @classmethod
    def setUpClass(cls):
        """Force Phase A (local imports) for all tests in this class."""
        cls._http_cfg_patcher = patch(
            "src.integrations.reinvestment_proposal._read_http_resolver_config",
            return_value=None,
        )
        cls._http_cfg_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._http_cfg_patcher.stop()

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    @patch("src.integrations.reinvestment_proposal.search_reinvestment_candidates")
    def test_generate_proposal_normal_flow(
        self, mock_candidates, mock_product, mock_client
    ):
        """Normal flow: valid targets produce expected response structure."""
        mock_client.return_value = SAMPLE_CLIENT

        def product_side_effect(pid):
            if pid == "ETF-HYG":
                return SAMPLE_PRODUCT
            return SAMPLE_CANDIDATE_PRODUCT

        mock_product.side_effect = product_side_effect
        mock_candidates.return_value = SAMPLE_CANDIDATES

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
            ],
        )

        self.assertEqual(result["status"], "success")
        self.assertIn("results_by_client", result)
        self.assertEqual(len(result["results_by_client"]), 1)

        item = result["results_by_client"][0]
        self.assertEqual(item["client_id"], "PB-HK-000001-8")
        self.assertEqual(item["source_product_id"], "ETF-HYG")
        self.assertIn("candidate_products", item)
        self.assertTrue(len(item["candidate_products"]) > 0)
        self.assertIn("output_path", item)
        self.assertTrue(item["output_path"].endswith(".md"))

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    def test_missing_client_returns_graceful(self, mock_client):
        """Missing client produces partial_error with diagnostic error message."""
        mock_client.return_value = None

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "NONEXISTENT", "source_product_id": "ETF-HYG"},
            ],
        )

        self.assertEqual(result["status"], "partial_error")
        item = result["results_by_client"][0]
        self.assertIn("error", item)
        self.assertIn("NONEXISTENT", item["error"])
        self.assertEqual(item["client_id"], "NONEXISTENT")
        self.assertEqual(item["source_product_id"], "ETF-HYG")

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    def test_missing_source_product_returns_graceful(self, mock_product, mock_client):
        """Missing source product produces partial_error with diagnostic error message."""
        mock_client.return_value = SAMPLE_CLIENT
        mock_product.return_value = None

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "PB-HK-000001-8", "source_product_id": "NONEXISTENT"},
            ],
        )

        self.assertEqual(result["status"], "partial_error")
        item = result["results_by_client"][0]
        self.assertIn("error", item)
        self.assertIn("NONEXISTENT", item["error"])
        self.assertEqual(item["client_id"], "PB-HK-000001-8")

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    @patch("src.integrations.reinvestment_proposal.search_reinvestment_candidates")
    def test_response_mode_path(self, mock_candidates, mock_product, mock_client):
        """path mode returns output_path, no markdown_output."""
        mock_client.return_value = SAMPLE_CLIENT
        mock_product.side_effect = lambda pid: (
            SAMPLE_PRODUCT if pid == "ETF-HYG" else SAMPLE_CANDIDATE_PRODUCT
        )
        mock_candidates.return_value = SAMPLE_CANDIDATES

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
            ],
            response_mode="path",
        )

        item = result["results_by_client"][0]
        self.assertIn("output_path", item)
        self.assertNotIn("markdown_output", item)

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    @patch("src.integrations.reinvestment_proposal.search_reinvestment_candidates")
    def test_response_mode_markdown(self, mock_candidates, mock_product, mock_client):
        """markdown mode returns markdown_output, no output_path."""
        mock_client.return_value = SAMPLE_CLIENT
        mock_product.side_effect = lambda pid: (
            SAMPLE_PRODUCT if pid == "ETF-HYG" else SAMPLE_CANDIDATE_PRODUCT
        )
        mock_candidates.return_value = SAMPLE_CANDIDATES

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
            ],
            response_mode="markdown",
        )

        item = result["results_by_client"][0]
        self.assertIn("markdown_output", item)
        self.assertNotIn("output_path", item)

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    @patch("src.integrations.reinvestment_proposal.search_reinvestment_candidates")
    def test_response_mode_both(self, mock_candidates, mock_product, mock_client):
        """both mode returns output_path and markdown_output."""
        mock_client.return_value = SAMPLE_CLIENT
        mock_product.side_effect = lambda pid: (
            SAMPLE_PRODUCT if pid == "ETF-HYG" else SAMPLE_CANDIDATE_PRODUCT
        )
        mock_candidates.return_value = SAMPLE_CANDIDATES

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
            ],
            response_mode="both",
        )

        item = result["results_by_client"][0]
        self.assertIn("output_path", item)
        self.assertIn("markdown_output", item)

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    @patch("src.integrations.reinvestment_proposal.search_reinvestment_candidates")
    def test_include_llm_input_true(self, mock_candidates, mock_product, mock_client):
        """include_llm_input=True returns llm_input in output."""
        mock_client.return_value = SAMPLE_CLIENT
        mock_product.side_effect = lambda pid: (
            SAMPLE_PRODUCT if pid == "ETF-HYG" else SAMPLE_CANDIDATE_PRODUCT
        )
        mock_candidates.return_value = SAMPLE_CANDIDATES

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
            ],
            include_llm_input=True,
        )

        item = result["results_by_client"][0]
        self.assertIn("llm_input", item)
        self.assertIn("client_profile", item["llm_input"])
        self.assertIn("candidate_products", item["llm_input"])

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    @patch("src.integrations.reinvestment_proposal.search_reinvestment_candidates")
    def test_include_llm_input_false(self, mock_candidates, mock_product, mock_client):
        """include_llm_input=False omits llm_input from output (default)."""
        mock_client.return_value = SAMPLE_CLIENT
        mock_product.side_effect = lambda pid: (
            SAMPLE_PRODUCT if pid == "ETF-HYG" else SAMPLE_CANDIDATE_PRODUCT
        )
        mock_candidates.return_value = SAMPLE_CANDIDATES

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
            ],
            include_llm_input=False,
        )

        item = result["results_by_client"][0]
        self.assertNotIn("llm_input", item)

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    @patch("src.integrations.reinvestment_proposal.search_reinvestment_candidates")
    def test_include_debug_scores_true(self, mock_candidates, mock_product, mock_client):
        """include_debug_scores=True returns debug_scores."""
        mock_client.return_value = SAMPLE_CLIENT
        mock_product.side_effect = lambda pid: (
            SAMPLE_PRODUCT if pid == "ETF-HYG" else SAMPLE_CANDIDATE_PRODUCT
        )
        mock_candidates.return_value = SAMPLE_CANDIDATES

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
            ],
            include_debug_scores=True,
        )

        item = result["results_by_client"][0]
        self.assertIn("debug_scores", item)
        self.assertIn("investor_readiness_score", item["debug_scores"])
        self.assertIn("product_fitness_scores", item["debug_scores"])

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    @patch("src.integrations.reinvestment_proposal.search_reinvestment_candidates")
    def test_include_debug_scores_false(self, mock_candidates, mock_product, mock_client):
        """include_debug_scores=False omits debug_scores (default)."""
        mock_client.return_value = SAMPLE_CLIENT
        mock_product.side_effect = lambda pid: (
            SAMPLE_PRODUCT if pid == "ETF-HYG" else SAMPLE_CANDIDATE_PRODUCT
        )
        mock_candidates.return_value = SAMPLE_CANDIDATES

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
            ],
            include_debug_scores=False,
        )

        item = result["results_by_client"][0]
        self.assertNotIn("debug_scores", item)

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    @patch("src.integrations.reinvestment_proposal.search_reinvestment_candidates")
    def test_multiple_targets(self, mock_candidates, mock_product, mock_client):
        """Multiple targets produce multiple results_by_client entries."""
        mock_client.return_value = SAMPLE_CLIENT
        mock_product.side_effect = lambda pid: (
            SAMPLE_PRODUCT if pid == "ETF-HYG" else SAMPLE_CANDIDATE_PRODUCT
        )
        mock_candidates.return_value = SAMPLE_CANDIDATES

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
                {"client_id": "PB-HK-000002-6", "source_product_id": "ETF-HYG"},
            ],
        )

        self.assertEqual(len(result["results_by_client"]), 2)

    @patch("src.integrations.reinvestment_proposal.search_by_id")
    @patch("src.integrations.reinvestment_proposal.search_by_product_id")
    @patch("src.integrations.reinvestment_proposal.search_reinvestment_candidates")
    def test_bad_target_skipped(self, mock_candidates, mock_product, mock_client):
        """Target with missing client_id or source_product_id is skipped."""
        mock_client.return_value = SAMPLE_CLIENT
        mock_product.side_effect = lambda pid: (
            SAMPLE_PRODUCT if pid == "ETF-HYG" else SAMPLE_CANDIDATE_PRODUCT
        )
        mock_candidates.return_value = SAMPLE_CANDIDATES

        result = propose_reinvestment(
            reinvestment_targets=[
                {"client_id": "", "source_product_id": "ETF-HYG"},
                {"client_id": "PB-HK-000001-8", "source_product_id": ""},
                {"client_id": "PB-HK-000002-6", "source_product_id": "ETF-HYG"},
            ],
        )

        # Two targets fail validation, third succeeds — status is partial_error
        self.assertEqual(result["status"], "partial_error")
        self.assertEqual(len(result["results_by_client"]), 3)
        # First two have errors
        self.assertIn("error", result["results_by_client"][0])
        self.assertIn("error", result["results_by_client"][1])
        # Third target succeeds
        self.assertEqual(result["results_by_client"][2]["client_id"], "PB-HK-000002-6")

    def test_invalid_response_mode(self):
        """Invalid response_mode raises ValueError."""
        with self.assertRaises(ValueError):
            propose_reinvestment(
                reinvestment_targets=[
                    {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
                ],
                response_mode="invalid",
            )


class TestLLMInputBuilder(unittest.TestCase):
    """Tests for the build_llm_input helper."""

    def test_build_llm_input_structure(self):
        """llm_input contains all required context blocks."""
        payload = build_llm_input(
            client_profile=SAMPLE_CLIENT,
            source_product=SAMPLE_PRODUCT,
            candidate_products=[SAMPLE_CANDIDATE_PRODUCT],
            include_market_outlook=True,
        )

        self.assertIn("client_profile", payload)
        self.assertIn("holdings", payload)
        self.assertIn("source_product", payload)
        self.assertIn("candidate_products", payload)
        self.assertIn("output_instructions", payload)
        self.assertIn("sections", payload["output_instructions"])

    def test_build_llm_input_optional_market_outlook(self):
        """Market outlook is included when flag is True, omitted when False."""
        payload_with = build_llm_input(
            client_profile=SAMPLE_CLIENT,
            source_product=SAMPLE_PRODUCT,
            candidate_products=[],
            include_market_outlook=True,
        )
        self.assertIn("market_outlook", payload_with)

        payload_without = build_llm_input(
            client_profile=SAMPLE_CLIENT,
            source_product=SAMPLE_PRODUCT,
            candidate_products=[],
            include_market_outlook=False,
        )
        self.assertNotIn("market_outlook", payload_without)


class TestDebugScoresBuilder(unittest.TestCase):
    """Tests for the _build_debug_scores helper."""

    def test_build_debug_scores_structure(self):
        """debug_scores contains investor readiness and product fitness data."""
        scores = _build_debug_scores(
            client_profile=SAMPLE_CLIENT,
            candidate_products=[SAMPLE_CANDIDATE_PRODUCT],
        )
        self.assertIn("investor_readiness_score", scores)
        self.assertIn("product_fitness_scores", scores)
        self.assertEqual(
            scores["investor_readiness_score"]["client_id"],
            "PB-HK-000001-8",
        )
        self.assertEqual(len(scores["product_fitness_scores"]), 1)


class TestHoldingsSummary(unittest.TestCase):
    """Tests for summarize_holdings helper."""

    def test_summarize_holdings(self):
        """Holdings are reduced to minimal fields."""
        summary = summarize_holdings(SAMPLE_CLIENT["holdings"])
        self.assertEqual(len(summary), 1)
        self.assertIn("product_id", summary[0])
        self.assertIn("market_value", summary[0])
        self.assertNotIn("quantity", summary[0])


# ---------------------------------------------------------------------------
# FastAPI integration tests (TestClient, no real server needed)
# ---------------------------------------------------------------------------


class TestFastAPIReinvestmentEndpoints(unittest.TestCase):
    """Integration tests for FastAPI reinvestment proposal endpoints (AC5, AC17)."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from src.integrations.proposal_server import app
        cls.client = TestClient(app)

    @patch("src.integrations.proposal_server.propose_reinvestment")
    def test_fastapi_propose_reinvestment_returns_200(self, mock_propose):
        """POST /api/v1/reinvestment-proposals returns 200 with valid payload (AC5)."""
        mock_propose.return_value = {
            "status": "success",
            "results_by_client": [
                {
                    "client_id": "PB-HK-000001-8",
                    "source_product_id": "ETF-HYG",
                    "candidate_products": [],
                    "output_path": "runs/reinvestment_proposal/test.md",
                }
            ],
        }

        response = self.client.post(
            "/api/v1/reinvestment-proposals",
            json={
                "reinvestment_targets": [
                    {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(len(data["results_by_client"]), 1)
        mock_propose.assert_called_once()

    @patch("src.integrations.proposal_server.propose_reinvestment")
    def test_fastapi_propose_reinvestment_passes_all_params(self, mock_propose):
        """Endpoint forwards all optional parameters to propose_reinvestment."""
        mock_propose.return_value = {"status": "success", "results_by_client": []}

        self.client.post(
            "/api/v1/reinvestment-proposals",
            json={
                "reinvestment_targets": [
                    {"client_id": "C1", "source_product_id": "P1"},
                ],
                "max_per_product_type": 3,
                "top_n_per_client": 5,
                "risk_rating_hard_filter": False,
                "response_mode": "both",
                "include_llm_input": True,
                "include_market_outlook": False,
                "include_debug_scores": True,
            },
        )

        mock_propose.assert_called_once_with(
            reinvestment_targets=[{"client_id": "C1", "source_product_id": "P1"}],
            max_per_product_type=3,
            top_n_per_client=5,
            risk_rating_hard_filter=False,
            response_mode="both",
            include_llm_input=True,
            include_market_outlook=False,
            include_debug_scores=True,
        )

    @patch("src.integrations.proposal_server.propose_reinvestment_for_maturing_holdings")
    def test_fastapi_propose_reinvestment_for_maturing_holdings_returns_200(self, mock_func):
        """POST .../propose_reinvestment_for_maturing_holdings returns 200 (AC17)."""
        mock_func.return_value = {"status": "success", "results_by_client": []}

        response = self.client.post(
            "/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings",
            json={
                "product_types": ["bond", "bond_fund"],
                "within_days": 180,
                "response_mode": "path",
                "include_debug_scores": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        mock_func.assert_called_once()

    @patch("src.integrations.proposal_server.propose_reinvestment_for_maturing_holdings")
    def test_fastapi_maturing_defaults(self, mock_func):
        """Endpoint uses sensible defaults when optional fields are omitted."""
        mock_func.return_value = {"status": "success", "results_by_client": []}

        self.client.post(
            "/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings",
            json={},
        )

        mock_func.assert_called_once_with(
            within_days=365,
            as_of_date=None,
            max_clients=2,
            max_per_product_type=2,
            top_n_per_client=10,
            risk_rating_hard_filter=True,
            response_mode="path",
            include_llm_input=False,
            include_market_outlook=True,
            include_debug_scores=False,
        )


if __name__ == "__main__":
    unittest.main()
