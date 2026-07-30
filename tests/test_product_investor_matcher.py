"""
Unit tests for product-investor matcher module.

Tests cover:
- normal flow with valid inputs
- empty-result handling (no clients, no eligible)
- error paths (API failures, LLM failures)
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from src.integrations.product_investor_matcher import (
    match_products_to_investors,
    _extract_top_pairs,
    _resolve_product_ids,
)

SAMPLE_READINESS_SCORES = [
    {"rank": 1, "client_id": "PB-HK-000001-8", "name": "Test A", "total_score": 29.5},
    {"rank": 2, "client_id": "PB-HK-000002-6", "name": "Test B", "total_score": 25.0},
    {"rank": 3, "client_id": "PB-HK-000003-4", "name": "Test C", "total_score": 22.0},
]

SAMPLE_CLIENTS = [
    {"client_id": "PB-HK-000001-8", "name": "Test A", "risk_rating": 3},
    {"client_id": "PB-HK-000002-6", "name": "Test B", "risk_rating": 4},
    {"client_id": "PB-HK-000003-4", "name": "Test C", "risk_rating": 2},
]

SAMPLE_CLIENT_DETAIL = {
    "client_id": "PB-HK-000001-8",
    "name": "Test A",
    "risk_rating": 3,
    "aum": 5000000,
    "age": 55,
    "holdings": [],
    "qualitative_profile": "Experienced investor seeking growth.",
}

SAMPLE_FITNESS_RESULTS = {
    "PB-HK-000001-8": {
        "results": [
            {
                "client_id": "PB-HK-000001-8",
                "product_id": "ETF-HYG",
                "product_name": "High Yield Bond ETF",
                "investment_note": "Attractive carry in current rate environment.",
                "fitness_score": 8.35,
                "component_scores": {"risk_rating_match_score": 9.0},
            },
        ]
    },
    "PB-HK-000002-6": {
        "results": [
            {
                "client_id": "PB-HK-000002-6",
                "product_id": "ETF-HYG",
                "product_name": "High Yield Bond ETF",
                "investment_note": "Attractive carry in current rate environment.",
                "fitness_score": 7.80,
                "component_scores": {"risk_rating_match_score": 8.0},
            },
        ]
    },
    "PB-HK-000003-4": {
        "results": [
            {
                "client_id": "PB-HK-000003-4",
                "product_id": "ETF-HYG",
                "product_name": "High Yield Bond ETF",
                "investment_note": "Attractive carry in current rate environment.",
                "fitness_score": 6.50,
                "component_scores": {"risk_rating_match_score": 7.0},
            },
        ]
    },
}


def _mock_fitness_results(client_ids, product_ids, **kwargs):
    results = []
    for cid in client_ids:
        entry = SAMPLE_FITNESS_RESULTS.get(cid, {})
        results.extend(entry.get("results", []))
    return {"results": results}


SAMPLE_MATCHING_MARKDOWN = """# Product-Investor Matching Report

## Rank 1 – Client PB-HK-000001-8 — Buying Score: 4.5

- **Product ID:** ETF-HYG
- **Investment Amount:** $500,000
- **Funding Source:** Cash reserves
- **Rationale:** Strong alignment with income objective and risk profile.

## Rank 2 – Client PB-HK-000002-6 — Buying Score: 3.8

- **Product ID:** ETF-HYG
- **Investment Amount:** $300,000
- **Funding Source:** Maturing bond proceeds
- **Rationale:** Suitable replacement for maturing fixed-income position.
"""


class TestResolveProductIds(unittest.TestCase):
    """Unit tests for product-group name resolution."""

    CONFIG = {
        "product_groups": {
            "bank_recommended": {
                "description": "Bank recommended products",
                "product_ids": ["PROD001", "PROD002", "PROD003"],
            },
            "ETF": {
                "description": "Exchange Traded Funds",
                "product_ids": ["VOO", "HYG", "GOVT"],
            },
        }
    }

    def test_resolve_group_expands_to_ids(self):
        """Known group name expands to its product_ids list."""
        result = _resolve_product_ids(["ETF"], self.CONFIG)
        self.assertEqual(result, ["VOO", "HYG", "GOVT"])

    def test_mixed_groups_and_literal_ids(self):
        """Group names expand; literal IDs pass through unchanged."""
        result = _resolve_product_ids(
            ["bank_recommended", "ETF-CUSTOM"],
            self.CONFIG,
        )
        self.assertEqual(result, ["PROD001", "PROD002", "PROD003", "ETF-CUSTOM"])

    def test_literal_only_no_expansion(self):
        """When no IDs are group names, the list is unchanged."""
        result = _resolve_product_ids(
            ["ETF-HYG", "ETF-BND"],
            self.CONFIG,
        )
        self.assertEqual(result, ["ETF-HYG", "ETF-BND"])

    def test_unknown_group_passes_through_as_literal(self):
        """A group name not in config stays as a literal product ID."""
        result = _resolve_product_ids(
            ["unknown_group", "ETF-HYG"],
            self.CONFIG,
        )
        self.assertEqual(result, ["unknown_group", "ETF-HYG"])

    def test_deduplication_across_groups(self):
        """Duplicate product IDs across groups/literals are deduplicated."""
        result = _resolve_product_ids(
            ["ETF", "HYG", "GOVT"],  # HYG, GOVT appear in both
            self.CONFIG,
        )
        self.assertEqual(result, ["VOO", "HYG", "GOVT"])

    def test_empty_product_ids(self):
        """Empty input returns empty list."""
        result = _resolve_product_ids([], self.CONFIG)
        self.assertEqual(result, [])

    def test_empty_config_groups(self):
        """Missing or empty product_groups — all IDs pass as literals."""
        result = _resolve_product_ids(
            ["ETF-HYG"], {"product_groups": {}},
        )
        self.assertEqual(result, ["ETF-HYG"])

        result2 = _resolve_product_ids(["ETF-HYG"], {})
        self.assertEqual(result2, ["ETF-HYG"])


class TestExtractTopPairs(unittest.TestCase):
    """Unit tests for markdown parsing."""

    def test_extract_pairs_normal(self):
        pairs = _extract_top_pairs(SAMPLE_MATCHING_MARKDOWN, top_n=5)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0]["client_id"], "PB-HK-000001-8")
        self.assertEqual(pairs[0]["buying_score"], 4.5)
        self.assertEqual(pairs[0]["product_id"], "ETF-HYG")
        self.assertEqual(pairs[0]["funding_source"], "Cash reserves")
        self.assertEqual(pairs[1]["client_id"], "PB-HK-000002-6")
        self.assertEqual(pairs[1]["buying_score"], 3.8)

    def test_extract_pairs_top_n_limit(self):
        pairs = _extract_top_pairs(SAMPLE_MATCHING_MARKDOWN, top_n=1)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["client_id"], "PB-HK-000001-8")

    def test_extract_pairs_empty(self):
        pairs = _extract_top_pairs("No client data here.", top_n=5)
        self.assertEqual(len(pairs), 0)


class TestProductInvestorMatcher(unittest.TestCase):
    """Integration tests for the full matching pipeline (mocked dependencies)."""

    def setUp(self):
        # Common patches for all tests
        self._load_config_patcher = patch(
            "src.integrations.product_investor_matcher.load_config",
            return_value=MagicMock(),
        )
        self._load_yaml_patcher = patch(
            "src.integrations.product_investor_matcher.yaml.safe_load",
            return_value={
                "product_investor_matching": {
                    "matcher": {"readiness_pool_size": 20},
                }
            },
        )
        self._load_config_patcher.start()
        self._load_yaml_patcher.start()

    def tearDown(self):
        self._load_config_patcher.stop()
        self._load_yaml_patcher.stop()

    @patch("src.integrations.product_investor_matcher.search")
    @patch("src.integrations.product_investor_matcher.search_by_investor_readiness_score")
    @patch("src.integrations.product_investor_matcher.search_product_by_fitness_score")
    @patch("src.integrations.product_investor_matcher.run_crew_planbot")
    @patch("src.integrations.product_investor_matcher.search_by_id")
    @patch("src.integrations.product_investor_matcher.search_by_product_id")
    @patch("src.test_data.product_catalog.get_conn")
    def test_normal_flow(
        self,
        mock_pcat_conn,
        mock_search_by_pid,
        mock_search_by_id,
        mock_run_crew,
        mock_fitness,
        mock_readiness,
        mock_search,
    ):
        """Normal flow: clients found, readiness passes, fitness scores, LLM runs."""
        # Mock client API
        mock_search.return_value = SAMPLE_CLIENTS
        mock_readiness.return_value = SAMPLE_READINESS_SCORES

        # Mock fitness
        mock_fitness.side_effect = _mock_fitness_results

        # Mock product catalog (full universe)
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("ETF-HYG",), ("ETF-BND",), ("ETF-VOO",),
        ]
        mock_pcat_conn.return_value = mock_conn

        # Mock LLM CrewAI — first call is matching, subsequent calls are fit analysis
        mock_matching_result = MagicMock()
        mock_matching_result.output_path.read_text.return_value = (
            SAMPLE_MATCHING_MARKDOWN
        )
        fit_mock = MagicMock()
        fit_mock.output_path.read_text.return_value = "# Fit Analysis\n\nTest proposal"
        mock_run_crew.side_effect = [
            mock_matching_result,  # product_investor_matching
            fit_mock,  # fit analysis pair 1
            fit_mock,  # fit analysis pair 2
        ]

        # Mock single client/product lookups
        mock_search_by_id.return_value = SAMPLE_CLIENT_DETAIL
        mock_search_by_pid.return_value = {
            "product_id": "ETF-HYG",
            "name": "High Yield Bond ETF",
            "product_type": "bond_fund",
            "risk_rating": 3,
            "expected_return": 6.0,
            "investment_note": "Attractive carry.",
        }

        result = match_products_to_investors(
            product_ids=["ETF-HYG"],
            top_n=2,
        )

        self.assertEqual(result["summary"]["status"], "success")
        self.assertEqual(result["summary"]["total_clients_retrieved"], 3)
        self.assertGreaterEqual(
            result["summary"]["clients_after_readiness"], 1,
        )
        self.assertGreater(len(result["product_investor_matching_markdown"]), 0)
        self.assertGreater(len(result["final_proposals"]), 0)
        self.assertEqual(len(result["errors"]), 0)

    @patch("src.integrations.product_investor_matcher.search")
    def test_no_clients_retrieved(self, mock_search):
        """Empty result: client API returns no clients."""
        mock_search.return_value = []

        result = match_products_to_investors(
            product_ids=["ETF-HYG"],
            top_n=5,
        )

        self.assertEqual(result["summary"]["status"], "warning")
        self.assertIn("NO_CLIENTS_RETRIEVED", result["warnings"])
        self.assertEqual(len(result["final_proposals"]), 0)

    @patch("src.integrations.product_investor_matcher.search")
    @patch("src.integrations.product_investor_matcher.search_by_investor_readiness_score")
    def test_no_eligible_clients(self, mock_readiness, mock_search):
        """Empty result: clients retrieved but none eligible."""
        mock_search.return_value = [
            {"client_id": "PB-HK-000099-9", "name": "Unknown", "risk_rating": 3},
        ]
        # Readiness scores exist but for a different client set
        mock_readiness.return_value = [
            {"rank": 1, "client_id": "PB-HK-000088-8", "name": "Other", "total_score": 20.0},
        ]

        result = match_products_to_investors(
            product_ids=["ETF-HYG"],
            top_n=5,
        )

        self.assertEqual(result["summary"]["status"], "warning")
        self.assertIn("NO_ELIGIBLE_CLIENTS", result["warnings"])

    @patch("src.integrations.product_investor_matcher.search")
    def test_client_api_error(self, mock_search):
        """Exception: client API raises an error."""
        mock_search.side_effect = RuntimeError("Connection refused")

        result = match_products_to_investors(
            product_ids=["ETF-HYG"],
            top_n=5,
        )

        self.assertEqual(result["summary"]["status"], "error")
        self.assertGreater(len(result["errors"]), 0)
        self.assertEqual(result["errors"][0]["code"], "CLIENT_API_ERROR")

    @patch("src.integrations.product_investor_matcher.search")
    @patch("src.integrations.product_investor_matcher.search_by_investor_readiness_score")
    def test_readiness_score_error(self, mock_readiness, mock_search):
        """Exception: readiness scorecard fails."""
        mock_search.return_value = SAMPLE_CLIENTS
        mock_readiness.side_effect = RuntimeError("Scorecard crash")

        result = match_products_to_investors(
            product_ids=["ETF-HYG"],
            top_n=5,
        )

        self.assertEqual(result["summary"]["status"], "error")
        self.assertGreater(len(result["errors"]), 0)
        self.assertEqual(result["errors"][0]["code"], "READINESS_SCORE_ERROR")

    @patch("src.integrations.product_investor_matcher.search")
    @patch("src.integrations.product_investor_matcher.search_by_investor_readiness_score")
    @patch("src.integrations.product_investor_matcher.search_product_by_fitness_score")
    def test_fitness_score_error(self, mock_fitness, mock_readiness, mock_search):
        """Exception: product fitness scorecard fails."""
        mock_search.return_value = SAMPLE_CLIENTS
        mock_readiness.return_value = SAMPLE_READINESS_SCORES
        mock_fitness.side_effect = RuntimeError("Fitness scoring crash")

        result = match_products_to_investors(
            product_ids=["ETF-HYG"],
            top_n=5,
        )

        self.assertEqual(result["summary"]["status"], "error")
        self.assertGreater(len(result["errors"]), 0)
        self.assertEqual(result["errors"][0]["code"], "FITNESS_SCORE_ERROR")

    @patch("src.integrations.product_investor_matcher.search")
    @patch("src.integrations.product_investor_matcher.search_by_investor_readiness_score")
    @patch("src.integrations.product_investor_matcher.search_product_by_fitness_score")
    @patch("src.integrations.product_investor_matcher.run_crew_planbot")
    @patch("src.integrations.product_investor_matcher.search_by_id")
    @patch("src.integrations.product_investor_matcher.search_by_product_id")
    def test_product_source_request_payload_no_group_expansion(
        self,
        mock_search_by_pid,
        mock_search_by_id,
        mock_run_crew,
        mock_fitness,
        mock_readiness,
        mock_search,
    ):
        """request_payload mode: group names are treated as literal IDs, not expanded."""
        mock_search.return_value = SAMPLE_CLIENTS
        mock_readiness.return_value = SAMPLE_READINESS_SCORES
        mock_fitness.side_effect = _mock_fitness_results

        # Mock LLM
        mock_result = MagicMock()
        mock_result.output_path.read_text.return_value = SAMPLE_MATCHING_MARKDOWN
        mock_run_crew.side_effect = [mock_result, MagicMock(), MagicMock()]

        mock_search_by_id.return_value = SAMPLE_CLIENT_DETAIL
        mock_search_by_pid.return_value = {
            "product_id": "ETF", "name": "ETF Group", "product_type": "fund",
            "risk_rating": 3, "expected_return": 5.0, "investment_note": "Note",
        }

        # Pass "ETF" (a known group name) in request_payload mode
        match_products_to_investors(
            product_ids=["ETF"],
            product_source="request_payload",
            top_n=2,
        )

        # Verify fitness was called with "ETF" as a literal product ID
        # (not expanded to VOO,HYG,GOVT)
        call_args = mock_fitness.call_args_list[0][1]
        self.assertEqual(call_args["product_ids"], ["ETF"])

    @patch("src.integrations.product_investor_matcher.search")
    @patch("src.integrations.product_investor_matcher.search_by_investor_readiness_score")
    @patch("src.integrations.product_investor_matcher.search_product_by_fitness_score")
    @patch("src.integrations.product_investor_matcher.run_crew_planbot")
    @patch("src.integrations.product_investor_matcher.search_by_id")
    @patch("src.integrations.product_investor_matcher.search_by_product_id")
    def test_product_source_default_yaml_expands_groups(
        self,
        mock_search_by_pid,
        mock_search_by_id,
        mock_run_crew,
        mock_fitness,
        mock_readiness,
        mock_search,
    ):
        """default_yaml mode: group names ARE expanded to member IDs."""
        mock_search.return_value = SAMPLE_CLIENTS
        mock_readiness.return_value = SAMPLE_READINESS_SCORES
        mock_fitness.side_effect = _mock_fitness_results

        mock_result = MagicMock()
        mock_result.output_path.read_text.return_value = SAMPLE_MATCHING_MARKDOWN
        mock_run_crew.side_effect = [mock_result, MagicMock(), MagicMock()]

        mock_search_by_id.return_value = SAMPLE_CLIENT_DETAIL
        mock_search_by_pid.return_value = {
            "product_id": "VOO", "name": "S&P 500 ETF", "product_type": "equity_fund",
            "risk_rating": 4, "expected_return": 8.0, "investment_note": "Note",
        }

        # The yaml.safe_load mock returns config without product_groups —
        # so we need to override it for this test.  Patch _resolve_product_ids
        # to verify it's called with the group name.
        with patch(
            "src.integrations.product_investor_matcher._resolve_product_ids",
            wraps=_resolve_product_ids,
        ) as mock_resolve:
            match_products_to_investors(
                product_ids=["ETF"],
                product_source="default_yaml",
                top_n=2,
            )

        # _resolve_product_ids should be called with ["ETF"]
        mock_resolve.assert_called_once()
        self.assertEqual(mock_resolve.call_args[0][0], ["ETF"])


if __name__ == "__main__":
    unittest.main()
