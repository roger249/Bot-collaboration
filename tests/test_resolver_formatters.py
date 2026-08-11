from __future__ import annotations

import unittest

from src.shared.resolver_formatters import format_product_catalog


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
        self.assertIn("performance_history_json", output)

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


if __name__ == "__main__":
    unittest.main()
