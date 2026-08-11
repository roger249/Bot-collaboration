"""
Unit tests for product-investor matcher module.

Tests cover:
- normal flow with valid inputs (real DB, only LLM mocked)
- empty-result handling (no clients, no eligible)
- error paths (API failures, LLM failures)

Only ``run_crew_planbot`` (the LLM call) is mocked.  All other functions
(search, readiness scorecard, fitness scorecard, DB lookups) run against
the real DuckDB under source control at ``data/planbot/db/planbot.duckdb``.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.integrations.product_investor_matcher import (
    product_investor_matcher,
    _extract_top_pairs,
    _resolve_product_ids,
)

SAMPLE_MATCHING_MARKDOWN = """# Product Investor Matching

## Executive Summary

Summary text.

| Client ID (Name) | Buying Score | Suggested Product & Position | Funding Source | Fitness Score | Expected Return – Suggested | Expected Return – Source | Key Rationale |
|---:|---:|---|---:|---:|---:|---|--|
| PB-HK-000001-8 (David Kim) | 5 | ETF-HYG iShares High Yield Corp Bond ETF – USD 500,000 (10.0%) | Sell Cash – USD 500,000 | 4.20 | 5.5% | 0.0% | Strong alignment with income objective and risk profile. |
| PB-HK-000002-6 (Sarah Chen) | 4 | ETF-HYG iShares High Yield Corp Bond ETF – USD 300,000 (6.0%) | Sell STOCK-AMZN – USD 300,000 | 4.20 | 5.5% | 15.0% | Suitable replacement for existing position. |

## Top clients with detail analysis

### PB-HK-000001-8 (David Kim)

- **Buying Score:** 5
- **Recommendation:** Buy ETF-HYG via selling Cash.

#### Alternative suggestion

- PROD003 US Corporate Bond Fund (fitness 4.20) lower-risk alternative.
- PROD016 Healthcare Innovation Fund (fitness 3.45) growth alternative.

---

### PB-HK-000002-6 (Sarah Chen)

- **Buying Score:** 4
- **Recommendation:** Buy ETF-HYG via selling STOCK-AMZN.

#### Alternative suggestion

- PROD014 Emerging Markets Fund (fitness 4.20) APAC exposure alternative.
- PROD001 Tech Leaders Equity Fund (fitness 4.20) technology alternative.
"""

FIT_ANALYSIS_MARKDOWN = "# Fit Analysis\n\nTest proposal from real DB"


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_crew_result(markdown: str) -> MagicMock:
    m = MagicMock()
    m.output_path.read_text.return_value = markdown
    return m


# ── _resolve_product_ids tests (pure, no DB needed) ─────────────────────


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
        result = _resolve_product_ids(["ETF"], self.CONFIG)
        self.assertEqual(result, ["VOO", "HYG", "GOVT"])

    def test_mixed_groups_and_literal_ids(self):
        result = _resolve_product_ids(
            ["bank_recommended", "ETF-CUSTOM"],
            self.CONFIG,
        )
        self.assertEqual(result, ["PROD001", "PROD002", "PROD003", "ETF-CUSTOM"])

    def test_literal_only_no_expansion(self):
        result = _resolve_product_ids(["ETF-HYG", "ETF-BND"], self.CONFIG)
        self.assertEqual(result, ["ETF-HYG", "ETF-BND"])

    def test_unknown_group_passes_through_as_literal(self):
        result = _resolve_product_ids(["unknown_group", "ETF-HYG"], self.CONFIG)
        self.assertEqual(result, ["unknown_group", "ETF-HYG"])

    def test_deduplication_across_groups(self):
        result = _resolve_product_ids(["ETF", "HYG", "GOVT"], self.CONFIG)
        self.assertEqual(result, ["VOO", "HYG", "GOVT"])

    def test_empty_product_ids(self):
        result = _resolve_product_ids([], self.CONFIG)
        self.assertEqual(result, [])

    def test_empty_config_groups(self):
        result = _resolve_product_ids(["ETF-HYG"], {"product_groups": {}})
        self.assertEqual(result, ["ETF-HYG"])
        result2 = _resolve_product_ids(["ETF-HYG"], {})
        self.assertEqual(result2, ["ETF-HYG"])


# ── _extract_top_pairs tests (pure, no DB needed) ───────────────────────


class TestExtractTopPairs(unittest.TestCase):
    """Unit tests for markdown parsing."""

    def test_extract_pairs_normal(self):
        pairs = _extract_top_pairs(SAMPLE_MATCHING_MARKDOWN, top_n=5)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0]["client_id"], "PB-HK-000001-8")
        self.assertEqual(pairs[0]["buying_score"], 5.0)
        self.assertEqual(pairs[0]["product_id"], "ETF-HYG")
        self.assertIn("Sell Cash", pairs[0]["funding_source"])
        self.assertEqual(pairs[1]["client_id"], "PB-HK-000002-6")
        self.assertEqual(pairs[1]["buying_score"], 4.0)

    def test_extract_pairs_top_n_limit(self):
        pairs = _extract_top_pairs(SAMPLE_MATCHING_MARKDOWN, top_n=1)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["client_id"], "PB-HK-000001-8")

    def test_extract_alternatives(self):
        """Alternative product IDs are extracted from per-client sections."""
        pairs = _extract_top_pairs(SAMPLE_MATCHING_MARKDOWN, top_n=5)
        self.assertEqual(
            pairs[0]["alternative_product_ids"],
            ["PROD003", "PROD016"],
        )
        self.assertEqual(
            pairs[1]["alternative_product_ids"],
            ["PROD014", "PROD001"],
        )

    def test_extract_pairs_empty(self):
        pairs = _extract_top_pairs("No client data here.", top_n=5)
        self.assertEqual(len(pairs), 0)

    def test_extract_pairs_real_llm_shape_without_summary_table(self):
        """Regression guard for refactor drift in matcher markdown shape.

        The current parser requires a strict 8-column summary table beginning
        with ``| Client ID (Name) | Buying Score | ...``. Real LLM output seen
        in slow E2E runs may instead emit per-client sections only (for example
        ``### Client ID: ...``) and omit that summary table entirely. The
        fallback parser should still extract client/product pairs from that shape.
        """
        real_llm_shape = """# Reinvestment Analysis: Client ID: PB-HK-000005-9 (Emma Thompson)

## Executive Summary

Recommendation summary text.

## Recommended Product: PROD003 - US Corporate Bond Fund

### Detailed Justification

Rationale text.

#### Alternative Products to Consider

- PROD007 - Asia Pacific Bond Fund
- PROD020 - Balanced Growth & Income Fund
"""

        pairs = _extract_top_pairs(real_llm_shape, top_n=5)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["client_id"], "PB-HK-000005-9")
        self.assertEqual(pairs[0]["product_id"], "PROD003")

    def test_extract_matching_context_prefers_detail_over_alternatives_section(self):
        """Keep the detailed client block when later client headers exist.

        Some LLM reports repeat the same client in later sections like
        "Alternative Products to Consider" using a "### Client: ..." header.
        The extractor should preserve the richer detail-analysis block.
        """
        markdown = """## Executive Summary

| Client ID (Name) | Buying Score | Suggested Product & Position | Funding Source | Fitness Score | Expected Return – Suggested | Expected Return – Source | Key Rationale |
|---:|---:|---|---:|---:|---:|---|--|
| PB-HK-000005-9 (Emma Thompson) | 4 | PROD003 US Corporate Bond Fund – USD 300,000 (9.7%) | Sell ETF-SPAXX – USD 300,000 | 6.25 | 5.2% | 4.68% | Deploy idle cash into high-quality bonds. |

## Top Clients with Detail Analysis

### PB-HK-000005-9 (Emma Thompson)

- **Suggestion:** Buy PROD003 US Corporate Bond Fund – USD 300,000 (9.7% of portfolio); fund by selling ETF-SPAXX Fidelity Government Cash Reserves – USD 300,000.
- **Financial-need fit:** Emma is risk-averse and seeks stable income.
- **Key factors:** Risk rating is 1 and product fitness is 6.25.
- **Return comparison:** PROD003 expected return is 5.2% vs. SPAXX at 4.68%.
- **Concentration impact:** No concentration is added.
- **Alternative suggestion:** PROD007 Asia Pacific Bond Fund (fitness 6.25) as a diversification option.

## Alternative Products to Consider

### Client: PB-HK-000005-9 (Emma Thompson)

- **PROD007 Asia Pacific Bond Fund:** Alternative text only.
- **PROD020 Balanced Growth & Income:** Alternative text only.
"""

        pairs = _extract_top_pairs(markdown, top_n=5)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["client_id"], "PB-HK-000005-9")
        self.assertIn("**Suggestion:** Buy PROD003", pairs[0]["matching_context"])
        self.assertIn("**Financial-need fit:**", pairs[0]["matching_context"])
        self.assertNotIn("### Client: PB-HK-000005-9", pairs[0]["matching_context"])

    def test_extract_matching_context_normalizes_heading_variants(self):
        """Normalize common LLM label variants to canonical matcher headings."""
        markdown = """## Executive Summary

| Client ID (Name) | Buying Score | Suggested Product & Position | Funding Source | Fitness Score | Expected Return – Suggested | Expected Return – Source | Key Rationale |
|---:|---:|---|---:|---:|---:|---|--|
| PB-HK-000005-9 (Emma Thompson) | 5 | PROD003 US Corporate Bond Fund – USD 173,260 (5.6%) | Sell us5yt-rr US 5-Year Treasury Yield – USD 173,260 | 6.25 | 5.2% | 3.02% | Upgrade low-yielding treasury into diversified IG corporate bonds. |

## Top Clients with Detail Analysis

### PB-HK-000005-9 (Emma Thompson)

- **Recommendation:** Buy PROD003 US Corporate Bond Fund – USD 173,260; funded by selling us5yt-rr US 5-Year Treasury Yield – USD 173,260.
- **Financial need:** Emma is a risk-averse retiree focused on capital preservation and liquidity.
- **Why this fits:** Product fitness is 6.25 and risk profile is aligned.
"""

        pairs = _extract_top_pairs(markdown, top_n=5)
        self.assertEqual(len(pairs), 1)
        ctx = pairs[0]["matching_context"]
        self.assertIn("**Suggestion:**", ctx)
        self.assertIn("**Financial-need fit:**", ctx)
        self.assertNotIn("**Recommendation:**", ctx)


# ── Pipeline tests (real DB, mock LLM only) ─────────────────────────────


class TestProductInvestorMatcher(unittest.TestCase):
    """Integration tests using real DuckDB.
    
    ``run_crew_planbot`` (the LLM call) is mocked in setUp.
    All other functions hit the real database.
    """

    def setUp(self):
        self._crew_patcher = patch(
            "src.integrations.product_investor_matcher.run_crew_planbot"
        )
        self.mock_run_crew = self._crew_patcher.start()

        self._matching_result = _make_crew_result(SAMPLE_MATCHING_MARKDOWN)
        self._fit_result = _make_crew_result(FIT_ANALYSIS_MARKDOWN)

    def tearDown(self):
        self._crew_patcher.stop()

    # ── normal flow ─────────────────────────────────────────────────

    def test_normal_flow(self):
        """Normal flow: real DB → real search/IRS/PFS → mock LLM → success."""
        self.mock_run_crew.side_effect = [
            self._matching_result,   # product_investor_matching only
        ]

        result = product_investor_matcher(
            product_ids=["bank_recommended"],
            product_source="default_yaml",
            top_n=2,
        )

        self.assertEqual(result["summary"]["status"], "success")
        self.assertGreaterEqual(result["summary"]["total_clients_retrieved"], 1)
        self.assertGreaterEqual(result["summary"]["clients_after_readiness"], 1)
        self.assertGreater(len(result["product_investor_matching_markdown"]), 0)
        self.assertGreater(len(result["final_proposals"]), 0)
        # final_proposals now carry ranking data (no proposal_markdown)
        self.assertIn("buying_score", result["final_proposals"][0])
        self.assertIn("rationale", result["final_proposals"][0])
        self.assertEqual(len(result["errors"]), 0)

    # ── empty-result paths ──────────────────────────────────────────

    def test_no_clients_retrieved(self):
        """Empty result: client API returns no clients."""
        with patch(
            "src.integrations.product_investor_matcher.search",
            return_value=[],
        ):
            result = product_investor_matcher(
                product_ids=["ETF-HYG"], top_n=5,
            )

        self.assertEqual(result["summary"]["status"], "warning")
        self.assertIn("NO_CLIENTS_RETRIEVED", result["warnings"])
        self.assertEqual(len(result["final_proposals"]), 0)

    def test_no_eligible_clients(self):
        """Empty result: clients retrieved but none eligible (disjoint IRS set)."""
        with patch(
            "src.integrations.product_investor_matcher.search",
            return_value=[
                {"client_id": "PB-HK-000099-9", "name": "Unknown", "risk_rating": 3},
            ],
        ), patch(
            "src.integrations.product_investor_matcher.search_by_investor_readiness_score",
            return_value=[
                {"rank": 1, "client_id": "PB-HK-000088-8", "name": "Other", "total_score": 20.0},
            ],
        ):
            result = product_investor_matcher(
                product_ids=["ETF-HYG"], top_n=5,
            )

        self.assertEqual(result["summary"]["status"], "warning")
        self.assertIn("NO_ELIGIBLE_CLIENTS", result["warnings"])

    # ── error paths ─────────────────────────────────────────────────

    def test_client_api_error(self):
        """Exception: client API raises an error."""
        with patch(
            "src.integrations.product_investor_matcher.search",
            side_effect=RuntimeError("Connection refused"),
        ):
            result = product_investor_matcher(
                product_ids=["ETF-HYG"], top_n=5,
            )

        self.assertEqual(result["summary"]["status"], "error")
        self.assertEqual(result["errors"][0]["code"], "CLIENT_API_ERROR")

    def test_readiness_score_error(self):
        """Exception: readiness scorecard fails."""
        with patch(
            "src.integrations.product_investor_matcher.search_by_investor_readiness_score",
            side_effect=RuntimeError("Scorecard crash"),
        ):
            result = product_investor_matcher(
                product_ids=["ETF-HYG"], top_n=5,
            )

        self.assertEqual(result["summary"]["status"], "error")
        self.assertEqual(result["errors"][0]["code"], "READINESS_SCORE_ERROR")

    def test_fitness_score_error(self):
        """Exception: product fitness scorecard fails."""
        with patch(
            "src.integrations.product_investor_matcher.search_product_by_fitness_score",
            side_effect=RuntimeError("Fitness scoring crash"),
        ):
            result = product_investor_matcher(
                product_ids=["ETF-HYG"], top_n=5,
            )

        self.assertEqual(result["summary"]["status"], "error")
        self.assertEqual(result["errors"][0]["code"], "FITNESS_SCORE_ERROR")

    def test_llm_generation_error(self):
        """Exception: CrewAI/LLM call fails."""
        self.mock_run_crew.side_effect = RuntimeError("LLM timeout")

        result = product_investor_matcher(
            product_ids=["ETF-HYG"], top_n=2,
        )

        self.assertEqual(result["summary"]["status"], "error")
        self.assertEqual(result["errors"][0]["code"], "LLM_GENERATION_ERROR")

    # ── product_source modes ────────────────────────────────────────

    def test_product_source_request_payload_no_group_expansion(self):
        """request_payload mode: group names are treated as literal IDs."""
        with patch(
            "src.integrations.product_investor_matcher.search_product_by_fitness_score",
            return_value={"results": []},
        ):
            self.mock_run_crew.side_effect = [
                _make_crew_result(SAMPLE_MATCHING_MARKDOWN),
            ]

            # "ETF" could be a group name — in request_payload mode it is NOT expanded
            result = product_investor_matcher(
                product_ids=["ETF"],
                product_source="request_payload",
                top_n=2,
            )

            # request_payload with an unknown product ID still succeeds;
            # the LLM gets an empty fitness table but the pipeline runs.
            self.assertEqual(result["summary"]["status"], "success")

    def test_product_source_default_yaml_expands_groups(self):
        """default_yaml mode: group names ARE expanded to member IDs."""
        with patch(
            "src.integrations.product_investor_matcher._resolve_product_ids",
            return_value=["PROD001", "PROD002", "PROD003"],
        ) as mock_resolve:
            with patch(
                "src.integrations.product_investor_matcher.search_product_by_fitness_score",
                return_value={"results": []},
            ):
                self.mock_run_crew.side_effect = [
                    _make_crew_result(SAMPLE_MATCHING_MARKDOWN),
                    _make_crew_result(FIT_ANALYSIS_MARKDOWN),
                    _make_crew_result(FIT_ANALYSIS_MARKDOWN),
                ]

                product_investor_matcher(
                    product_ids=["bank_recommended"],
                    product_source="default_yaml",
                    top_n=2,
                )

            mock_resolve.assert_called_once()
            self.assertEqual(mock_resolve.call_args[0][0], ["bank_recommended"])


if __name__ == "__main__":
    unittest.main()
