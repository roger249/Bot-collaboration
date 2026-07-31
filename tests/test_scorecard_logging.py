"""
Unit test: scorecard logging via real proposal server (LLM bypassed).

Verifies that the scorecard log entries (IRS, PFS, readiness, fitness)
are written to ``log/planbot.log`` when the product-investor-matcher
endpoint is called through a live HTTP server.

LLM invocations are mocked so the test runs in <5 seconds.
"""

from __future__ import annotations

import logging
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import uvicorn

_ROOT = Path(__file__).resolve().parents[1]
_LOG_PATH = _ROOT / "log" / "planbot.log"
_INI_PATH = _ROOT / "config" / "logging_config.ini"

# ── Mock LLM outputs (no CrewAI/LLM invocation) ───────────────────────

_MATCHING_MARKDOWN = """# Product-Investor Matching Report

## Rank 1 – Client PB-HK-000001-8 — Buying Score: 4.5

- **Product ID:** ETF-HYG
- **Rationale:** Strong alignment with income objective.
"""

_FIT_MARKDOWN = "# Fit Analysis\n\nTest proposal with mock LLM.\n"


def _make_crew_result(markdown: str) -> MagicMock:
    m = MagicMock()
    m.output_path.read_text.return_value = markdown
    return m


# ── Helpers ────────────────────────────────────────────────────────────


def _reset_and_init_logging() -> None:
    """Force re-initialize logging from the ini file."""
    import src.shared.logging_utils as lu
    lu._INITIALIZED = False
    root = logging.getLogger()
    root.handlers.clear()
    lu.init_logging(str(_INI_PATH))


def _flush_and_read_log() -> str:
    """Flush all handlers and return contents of ``log/planbot.log`` WITHOUT truncating."""
    # Flush all handlers so buffered writes hit disk
    for handler in logging.getLogger().handlers:
        handler.flush()
    # Also flush the src.integrations logger's handlers
    for logger_name in ["src.integrations", "src.integrations.product_tool",
                        "src.integrations.client_api", "src.integrations.product_investor_matcher"]:
        for handler in logging.getLogger(logger_name).handlers:
            handler.flush()

    assert _LOG_PATH.exists(), f"Log file missing: {_LOG_PATH}"
    return _LOG_PATH.read_text(encoding="utf-8")


def _assert_scorecard_in_log(text: str) -> None:
    """Assert the four INFO-level scorecard entries are in the log."""
    # IRS (client_api.py)
    assert "IRS:" in text and "clients scored" in text, (
        f"IRS scorecard missing from log:\n{text[:500]}"
    )
    # Readiness scorecard (product_investor_matcher.py)
    assert "Readiness scorecard:" in text and "clients scored" in text, (
        f"Readiness scorecard missing from log:\n{text[:500]}"
    )
    # PFS request (product_tool.py)
    assert "PFS request:" in text, (
        f"PFS request missing from log:\n{text[:500]}"
    )
    # Fitness scorecard (product_investor_matcher.py)
    assert "Fitness scorecard:" in text and "clients scored" in text, (
        f"Fitness scorecard missing from log:\n{text[:500]}"
    )


# ── Server helper ──────────────────────────────────────────────────────


def _start_proposal_server() -> tuple[str, uvicorn.Server, threading.Thread]:
    """Start the proposal server on an OS-assigned port in a daemon thread.

    Returns (base_url, server, thread).
    """
    from src.integrations.proposal_server import app

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to bind
    deadline = time.monotonic() + 10.0
    port: int | None = None
    while time.monotonic() < deadline:
        if server.started and server.servers:
            sock = server.servers[0].sockets[0]
            port = sock.getsockname()[1]
            break
        time.sleep(0.05)

    if port is None:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Proposal server did not start within 10 s")

    base_url = f"http://127.0.0.1:{port}"

    # Poll until responsive
    for _ in range(50):
        try:
            httpx.get(f"{base_url}/docs", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError(f"Proposal server not responding at {base_url}")

    return base_url, server, thread


# ═══════════════════════════════════════════════════════════════════════════
#  Test: real HTTP server, mock LLM, verify scorecard in disk log
# ═══════════════════════════════════════════════════════════════════════════


class TestScorecardLogging(unittest.TestCase):
    """Start real proposal server, mock LLM, verify scorecard logged to file."""

    @classmethod
    def setUpClass(cls):
        # Ensure clean logging state before starting the server
        _reset_and_init_logging()

    def setUp(self):
        # Start the proposal server
        self._base_url, self._server, self._thread = _start_proposal_server()

        # Patch run_crew_planbot to avoid LLM calls
        self._crew_patcher = patch(
            "src.integrations.product_investor_matcher.run_crew_planbot"
        )
        self.mock_run_crew = self._crew_patcher.start()
        self.mock_run_crew.side_effect = [
            _make_crew_result(_MATCHING_MARKDOWN),
            _make_crew_result(_FIT_MARKDOWN),
            _make_crew_result(_FIT_MARKDOWN),
        ]

    def tearDown(self):
        self._crew_patcher.stop()
        self._server.should_exit = True
        self._thread.join(timeout=5)

    def test_scorecard_logged_to_disk(self):
        """POST to matcher endpoint → verify scorecard entries in planbot.log."""
        response = httpx.post(
            f"{self._base_url}/api/v1/product-investor-matcher",
            json={
                "product_source": "default_yaml",
                "product_ids": ["bank_recommended"],
                "top_n": 2,
            },
            timeout=30,
        )

        # 1. HTTP response must be 200
        self.assertEqual(response.status_code, 200, f"HTTP {response.status_code}: {response.text[:300]}")
        body = response.json()
        self.assertEqual(body["summary"]["status"], "success")
        self.assertGreaterEqual(body["summary"]["total_clients_retrieved"], 1)
        self.assertGreater(len(body["final_proposals"]), 0)
        self.assertEqual(len(body["errors"]), 0)

        # 2. Disk log must contain scorecard entries
        log_text = _flush_and_read_log()
        _assert_scorecard_in_log(log_text)


if __name__ == "__main__":
    unittest.main()
