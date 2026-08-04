"""Unit tests for product_opportunity_proposal module."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.integrations.product_opportunity_proposal import (
    propose_product_opportunity,
    _load_latest_matcher_output,
)

FIT_MARKDOWN = """# Product Opportunity Proposal

## Investment Recommendation

- **Suggested Product:** PROD016 Healthcare Innovation Fund
- **Position:** 8.1% of portfolio

## Supporting Analysis

### Executive Summary
Test proposal generated successfully.

### Product Specification
- Issuer: Test Fund
- Asset Class: Equity

### Scenario Analysis
- Bull case: +15%
- Base case: +8%
- Bear case: -10%

### Risk Disclaimer
Past performance does not guarantee future returns.
"""


def _make_crew_result(markdown: str, output_path_str: str = "/tmp/test_output.md") -> MagicMock:
    """Build a mock crew result."""
    result = MagicMock()

    # Use a simple object for output_path so str() and read_text() both work
    class MockPath:
        def __str__(self):
            return output_path_str

        def read_text(self):
            return markdown

    result.output_path = MockPath()
    return result


class TestProposeProductOpportunity(unittest.TestCase):
    """Normal and exception flow tests."""

    def setUp(self):
        self._crew_patcher = patch(
            "src.integrations.product_opportunity_proposal.run_crew_planbot"
        )
        self.mock_run_crew = self._crew_patcher.start()

    def tearDown(self):
        self._crew_patcher.stop()

    def test_normal_flow(self):
        """Normal flow: valid client + product → successful proposal."""
        test_path = "runs/product_opportunity_proposal/product_opportunity_proposal_PB-HK-000001-8_PROD016.md"
        self.mock_run_crew.return_value = _make_crew_result(FIT_MARKDOWN, test_path)

        result = propose_product_opportunity(
            client_id="PB-HK-000001-8",
            product_id="PROD016",
            rationale="Test rationale for matching.",
        )

        self.assertEqual(result["client_id"], "PB-HK-000001-8")
        self.assertEqual(result["product_id"], "PROD016")
        self.assertIn("output_filename", result)
        self.assertIn("product_opportunity_proposal", result["output_filename"])
        self.assertIn("PB-HK-000001-8", result["output_filename"])
        self.assertIn("PROD016", result["output_filename"])
        self.assertGreater(len(result["proposal_markdown"]), 0)
        self.assertIn("Investment Recommendation", result["proposal_markdown"])
        self.assertIn("Supporting Analysis", result["proposal_markdown"])
        self.assertIn("metadata", result)
        self.assertIn("product_fitness_scores", result["metadata"])

    def test_client_not_found(self):
        """Exception: client ID not in DB."""
        with self.assertRaises(LookupError) as ctx:
            propose_product_opportunity(
                client_id="PB-HK-999999-9",
                product_id="PROD016",
            )
        self.assertIn("Client not found", str(ctx.exception))

    def test_product_not_found(self):
        """Exception: product ID not in DB."""
        with self.assertRaises(LookupError) as ctx:
            propose_product_opportunity(
                client_id="PB-HK-000001-8",
                product_id="PROD999",
            )
        self.assertIn("Product not found", str(ctx.exception))


class TestLoadLatestMatcherOutput(unittest.TestCase):
    """Disk loader tests."""

    def test_no_files_returns_empty(self):
        """No _pairs.json → empty result."""
        with patch.object(
            Path, "glob", return_value=[]
        ):
            run_id, pairs = _load_latest_matcher_output()
        self.assertEqual(run_id, "")
        self.assertEqual(pairs, [])


if __name__ == "__main__":
    unittest.main()
