from __future__ import annotations

import unittest

from src.shared.resolver_formatters import format_product_catalog, format_pfs_table


class TestFormatProductCatalog(unittest.TestCase):
    def test_includes_full_db_details_for_suggested_and_alternatives(self):
        suggested = {
            "product_id": "PROD053",
            "name": "US Treasury 4.375% 31Aug26",
            "ticker": "XHLF",
            "product_type": "bond",
            "vehicle": "Direct",
            "trading_currency": "USD",
            "region": "US",
            "sector": "Government",
            "risk_rating": 1,
            "expected_return": 3.7,
            "type_specific": {"coupon_rate": 0.04375, "maturity": "2026-08-31"},
            "performance_history": {
                "1y": {"return": 3.65, "cagr": 3.72, "max_drawdown": 0.0, "volatility": 0.20},
            },
            "investment_note": "Sample note",
        }
        alternatives = [
            {
                "product_id": "PROD054",
                "name": "US Treasury 3.75% 30Jun27",
                "product_type": "bond",
                "risk_rating": 1,
                "expected_return": 3.8,
                "type_specific": {"coupon_rate": 0.0375},
                "performance_history": {
                    "1y": {"return": 3.55, "cagr": 3.62, "max_drawdown": -0.01, "volatility": 0.21},
                },
            }
        ]

        output = format_product_catalog(suggested=suggested, holdings=[], alternatives=alternatives)

        self.assertIn("## Suggested Product", output)
        self.assertIn("### Performance History", output)
        self.assertIn("| Period | Return % | CAGR % | Max Drawdown % | Volatility % |", output)
        self.assertIn("| 1y | 3.65 | 3.72 | 0.00 | 0.20 |", output)
        self.assertIn("### 1. PROD054", output)
        self.assertIn("| 1y | 3.55 | 3.62 | -0.01 | 0.21 |", output)
        self.assertNotIn("### Raw DB Payload", output)
        self.assertNotIn("performance_history_json", output)

    def test_handles_missing_optional_product_fields(self):
        suggested = {
            "product_id": "PROD999",
            "name": "No Metrics Product",
            "product_type": "bond",
            "risk_rating": 2,
            "expected_return": 4.0,
            "type_specific": {},
            "performance_history": {},
        }

        output = format_product_catalog(suggested=suggested, holdings=None, alternatives=None)

        self.assertIn("- Product ID: PROD999", output)
        self.assertIn("- ISIN: N/A", output)
        self.assertIn("## Alternative Products", output)
        self.assertIn("*(none)*", output)
        self.assertNotIn("| Period | Return % | CAGR % | Max Drawdown % | Volatility % |", output)

    def test_suppresses_alternative_section_when_disabled(self):
        suggested = {
            "product_id": "PROD003",
            "name": "US Corporate Bond Fund",
            "product_type": "bond",
            "risk_rating": 2,
            "expected_return": 5.2,
            "type_specific": {},
            "performance_history": {},
        }

        output = format_product_catalog(
            suggested=suggested,
            holdings=None,
            alternatives=None,
            include_alternatives_section=False,
        )

        self.assertNotIn("## Alternative Products", output)
        self.assertNotIn("*(none)*", output)


class TestFormatPfsTable(unittest.TestCase):
    def _scores(self):
        return {
            "P1": {
                "fitness_score": 5.0,
                "risk_rating_match_score": 8.0,
                "diversification_score": 5.0,
                "has_similar_investment_experience_score": 6.0,
                "better_product_score": 4.0,
                "similarity_product_note_in_like_products": 5.0,
                "similarity_product_note_in_dislike_products": 5.0,
                "similarity_to_current_holding": 5.0,
                "similarity_to_RM_note": 5.0,
            }
        }

    def test_renders_similarity_columns(self):
        lines = format_pfs_table(self._scores())
        text = "\n".join(lines)
        self.assertIn("Like", text)
        self.assertIn("Comfort", text)
        self.assertIn("Holding Similarity", text)
        self.assertIn("RM Note Similarity", text)

    def test_degrades_with_remark_when_semantic_unavailable(self):
        lines = format_pfs_table(self._scores(), semantic_embedding_available=False)
        text = "\n".join(lines)
        self.assertIn("Semantic similarity was not available", text)

    def test_no_remark_when_semantic_available(self):
        lines = format_pfs_table(self._scores(), semantic_embedding_available=True)
        text = "\n".join(lines)
        self.assertNotIn("Semantic similarity was not available", text)


if __name__ == "__main__":
    unittest.main()
