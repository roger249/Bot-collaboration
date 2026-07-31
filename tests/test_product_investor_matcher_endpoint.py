"""
Tests for the product-investor matcher endpoint /api/v1/product-investor-matcher.

- ``TestMatcherFast`` — direct function call, mock LLM, verifies disk log
- ``test_scorecard_logged_to_disk`` — real HTTP server, mock LLM, verifies disk log
- ``test_matcher_endpoint_real_http`` — real HTTP, real LLM (slow)

All logging follows ``config/logging_config.ini`` — the ini is the truth.
"""

from __future__ import annotations

import logging
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_LOG_PATH = _ROOT / "log" / "planbot.log"
_INI_PATH = _ROOT / "config" / "logging_config.ini"

FIT_MARKDOWN = "# Fit Analysis\n\nTest proposal from real DB."
MATCHING_MARKDOWN = """# Product-Investor Matching Report

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


def _make_crew_result(markdown: str) -> MagicMock:
    m = MagicMock()
    m.output_path.read_text.return_value = markdown
    return m


def _init_logging_from_ini() -> None:
    """Configure logging from ``config/logging_config.ini``, once per process."""
    import src.shared.logging_utils as lu
    lu._INITIALIZED = False
    logging.getLogger().handlers.clear()
    lu.init_logging(str(_INI_PATH))


def _read_disk_log() -> str:
    """Flush and return contents of ``log/planbot.log``."""
    logging.shutdown()
    assert _LOG_PATH.exists(), f"Log file missing: {_LOG_PATH}"
    return _LOG_PATH.read_text(encoding="utf-8")


def _assert_scorecard_in_log(text: str) -> None:
    """Verify IRS and PFS scorecard INFO lines appear in the log.

    The ini controls the level — if it says DEBUG, debug lines are expected.
    We only assert that the INFO-level scorecard summaries are present.
    """
    assert "IRS:" in text and "clients scored" in text, (
        f"IRS scorecard missing from log:\n{text[:500]}"
    )
    assert "PFS:" in text and "pairs scored" in text, (
        f"PFS scorecard missing from log:\n{text[:500]}"
    )
    assert "Scorecard request: search_by_investor_readiness_score" in text
    assert "Readiness scorecard:" in text and "clients scored" in text
    assert "Scorecard request: search_product_by_fitness_score" in text
    assert "Fitness scorecard:" in text and "clients scored" in text


# ── Fast: direct function call, mock LLM, verify disk log ─────────────


class TestMatcherFast(unittest.TestCase):
    """Direct function call with mock LLM.  Logging follows the ini."""

    @classmethod
    def setUpClass(cls):
        _init_logging_from_ini()

    def setUp(self):
        self._crew_patcher = patch(
            "src.integrations.product_investor_matcher.run_crew_planbot"
        )
        self.mock_run_crew = self._crew_patcher.start()

    def tearDown(self):
        self._crew_patcher.stop()

    def test_default_payload_returns_success(self):
        """bank_recommended product group (10 products): real search/IRS/PFS → mock LLM → success."""
        self.mock_run_crew.side_effect = [
            _make_crew_result(MATCHING_MARKDOWN),
            _make_crew_result(FIT_MARKDOWN),
            _make_crew_result(FIT_MARKDOWN),
        ]

        from src.integrations.product_investor_matcher import match_products_to_investors

        result = match_products_to_investors(
            product_ids=["bank_recommended"],
            product_source="default_yaml",
            top_n=2,
        )

        # ── Result assertions ───────────────────────────────────────
        self.assertEqual(result["summary"]["status"], "success")
        self.assertGreaterEqual(result["summary"]["total_clients_retrieved"], 1)
        self.assertGreaterEqual(result["summary"]["clients_after_readiness"], 1)
        self.assertGreater(len(result["product_investor_matching_markdown"]), 0)
        self.assertGreater(len(result["final_proposals"]), 0)
        self.assertEqual(len(result["errors"]), 0)

        # ── Disk log assertions ─────────────────────────────────────
        _assert_scorecard_in_log(_read_disk_log())


# ── HTTP fast: real server, mock LLM, verify disk log ─────────────────


def test_scorecard_logged_to_disk(proposal_server):
    """Real HTTP server, mock LLM → verify scorecard in ``log/planbot.log``."""
    crew_patcher = patch(
        "src.integrations.product_investor_matcher.run_crew_planbot"
    )
    mock_run_crew = crew_patcher.start()
    try:
        mock_run_crew.side_effect = [
            _make_crew_result(MATCHING_MARKDOWN),
            _make_crew_result(FIT_MARKDOWN),
            _make_crew_result(FIT_MARKDOWN),
        ]

        _init_logging_from_ini()

        response = httpx.post(
            f"{proposal_server}/api/v1/product-investor-matcher",
            json={
                "product_source": "default_yaml",
                "product_ids": ["bank_recommended"],
                "top_n": 2,
            },
            timeout=30,
        )
        assert response.status_code == 200, response.text

        _assert_scorecard_in_log(_read_disk_log())

    finally:
        crew_patcher.stop()


# ── Slow: real HTTP via proposal_server, real LLM ─────────────────────


@pytest.mark.slow
def test_matcher_endpoint_real_http(proposal_server):
    """Real HTTP: POST /api/v1/product-investor-matcher → full pipeline with LLM.

    Uses default payload — no product_ids, no client_selection.
    The server uses real DuckDB + real CrewAI/LLM.
    """
    response = httpx.post(
        f"{proposal_server}/api/v1/product-investor-matcher",
        json={
            "product_source": "default_yaml",
            "product_ids": ["bank_recommended"],
            "top_n": 2,
        },
        timeout=600,
    )

    assert response.status_code == 200
    body = response.json()

    assert body["summary"]["status"] == "success", f"Unexpected status: {body['summary']}"
    assert body["summary"]["total_clients_retrieved"] >= 1
    assert body["summary"]["clients_after_readiness"] >= 1
    assert len(body["product_investor_matching_markdown"]) > 0, (
        "Expected non-empty matching markdown"
    )
    assert len(body["final_proposals"]) >= 1
    assert len(body["errors"]) == 0


if __name__ == "__main__":
    unittest.main()
