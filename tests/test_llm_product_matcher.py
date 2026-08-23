"""Unit tests for the LLM product matcher integration."""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from src.integrations.llm_product_matcher import propose_llm_product_matcher

MARKDOWN = """# Product Investor Matching

## Executive Summary

| Client ID (Name) | Buying Score | Suggested Product & Position | Funding Source | Fitness Score | Expected Return – Suggested | Expected Return – Source | Key Rationale |
|---:|---:|---|---:|---:|---:|---|--|
| PB-HK-000001-8 (David Kim) | 4 | ETF-VOO Vanguard S&P 500 ETF – USD 250,000 (7.8%) | Sell STOCK-AMZN Amazon.com Inc. – USD 250,000 | 4 | 20.55% | 23.88% | Reduce single-stock concentration. |

## Top clients with detail analysis

### PB-HK-000001-8 (David Kim)
- **Suggestion:** ETF-VOO Vanguard S&P 500 ETF
"""

SNAPSHOT = "# Prompt Snapshot\n\n**Model:** deepseek-v4-flash\n"


def _write_result(tmp_path: Path, markdown: str = MARKDOWN):
    out = tmp_path / "llm_product_matcher_out.md"
    out.write_text(markdown, encoding="utf-8")
    snapshot = tmp_path / "prompt_snapshot.md"
    snapshot.write_text(SNAPSHOT, encoding="utf-8")
    return out, snapshot


def _mock_crew(tmp_path: Path, monkeypatch):
    out, snapshot = _write_result(tmp_path)
    monkeypatch.setattr(
        "src.integrations.llm_product_matcher.run_crew_planbot",
        lambda **kwargs: types.SimpleNamespace(
            output_path=out, prompt_path=snapshot,
        ),
    )


def test_normal_flow(monkeypatch, tmp_path):
    """Normal flow: valid client → successful matcher report."""
    _mock_crew(tmp_path, monkeypatch)

    result = propose_llm_product_matcher(client_id="PB-HK-000001-8")

    assert result["client_id"] == "PB-HK-000001-8"
    assert "llm_product_matcher" in result["output_filename"]
    assert result["proposal_markdown"] == MARKDOWN
    # prompt_to_llm must be absent by default.
    assert "prompt_to_llm" not in result


def test_output_prompt_to_llm(monkeypatch, tmp_path):
    """output_prompt_to_llm=True returns the prompt_snapshot.md content."""
    _mock_crew(tmp_path, monkeypatch)

    result = propose_llm_product_matcher(
        client_id="PB-HK-000001-8", output_prompt_to_llm=True,
    )

    assert result["prompt_to_llm"] == SNAPSHOT


def test_client_not_found():
    """Exception: client ID not in DB → LookupError."""
    with pytest.raises(LookupError, match="Client not found"):
        propose_llm_product_matcher(client_id="PB-HK-999999-9")


@pytest.mark.slow
def test_llm_product_matcher_david_wu():
    """Real end-to-end: run the LLM product matcher for David Wu.

    Requires a live LLM + ``SERPAPI_API_KEY``.  The report is written to
    ``runs/llm_product_matcher/`` for manual inspection.
    """
    result = propose_llm_product_matcher(
        client_id="PB-HK-000020-8",
        output_prompt_to_llm=True,
    )

    assert result["client_id"] == "PB-HK-000020-8"
    assert result["proposal_markdown"].strip()
    assert result["prompt_to_llm"].startswith("# Prompt Snapshot")

    print(f"\nLLM product matcher output → {result['output_filename']}")
