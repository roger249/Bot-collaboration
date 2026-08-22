"""Unit tests for the shared market-outlook helpers."""

from __future__ import annotations

import unittest

from src.shared.market_outlook_utils import (
    format_market_outlook_section,
    resolve_market_outlook,
)


class TestResolveMarketOutlook(unittest.TestCase):
    """Tests for `resolve_market_outlook` source selection."""

    def test_request_returns_market_outlook(self):
        """`request` (default) returns the provided market outlook."""
        self.assertEqual(
            resolve_market_outlook("Bullish."),
            "Bullish.",
        )
        self.assertEqual(
            resolve_market_outlook("Bullish.", market_outlook_source="request"),
            "Bullish.",
        )

    def test_static_ignores_market_outlook(self):
        """`static` returns None even when a market outlook is provided."""
        self.assertIsNone(
            resolve_market_outlook("Bullish.", market_outlook_source="static"),
        )

    def test_default_source_fallback(self):
        """When no request source, the default_source is used."""
        self.assertIsNone(
            resolve_market_outlook("Bullish.", default_source="static"),
        )
        self.assertEqual(
            resolve_market_outlook("Bullish.", default_source="request"),
            "Bullish.",
        )


class TestFormatMarketOutlookSection(unittest.TestCase):
    """Tests for `format_market_outlook_section`."""

    def test_formats_provided_outlook(self):
        """Provided outlook is rendered under a `# Market Outlook` heading."""
        section = format_market_outlook_section("Rates stay elevated.")
        self.assertIn("# Market Outlook", section)
        self.assertIn("Rates stay elevated.", section)

    def test_formats_placeholder_when_missing(self):
        """None renders the `(not provided)` placeholder."""
        section = format_market_outlook_section(None)
        self.assertIn("(not provided)", section)


if __name__ == "__main__":
    unittest.main()
