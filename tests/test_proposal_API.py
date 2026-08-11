import pytest
import httpx
import time
from pathlib import Path
from types import SimpleNamespace

from src.integrations.client_api import search_holdings_maturing
from src.planbot.input_loader import API_SUGGESTED_PRODUCTS_AND_RATIONALE


_ROOT = Path(__file__).resolve().parents[1]
_RUNS = _ROOT / "runs"


def _read_latest_prompt_snapshot(run_folder: str, started_at: float) -> str:
    snapshots = [
        path for path in (_RUNS / run_folder).rglob("prompt_snapshot.md")
        if path.stat().st_mtime >= started_at
    ]
    assert snapshots, f"No prompt snapshot created under {run_folder}"
    latest = max(snapshots, key=lambda path: path.stat().st_mtime)
    return latest.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Real end-to-end pipeline: maturing API → CrewAI LLM proposal
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_reinvestment_proposals_propose_reinvestment_for_maturing_holdings(proposal_server):
    """Real-HTTP inbound: proposal API via httpx → server in thread.

    1. Call ``POST .../propose_reinvestment_for_maturing_holdings`` over real
       TCP — discovers maturing bonds, caps at 1 client, invokes LLM.
    2. Verify the output contains required section headers.

    """
    started_at = time.time()

    response = httpx.post(
        f"{proposal_server}/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings",
        json={
            "within_days": 365 * 10,
            "max_clients": 1,
            "response_mode": "both",
            "include_debug_scores": True,
        },
        timeout=600,
    )

    assert response.status_code == 200
    result = response.json()

    # Verify output
    assert result["status"] in {"success", "partial_error"}
    assert len(result["results_by_client"]) == 1

    item = result["results_by_client"][0]
    assert "output_path" in item
    assert "markdown_output" in item
    assert len(item["markdown_output"]) > 0

    for section in ("Executive Summary", "Recommended", "Risk", "Justification"):
        assert section.lower() in item["markdown_output"].lower()

    prompt_snapshot = _read_latest_prompt_snapshot("reinvestment_proposal", started_at)
    assert "# Prompt Snapshot" in prompt_snapshot
    assert "### client_profiles" in prompt_snapshot
    assert "### product_catalogs" in prompt_snapshot
    assert "Wallet Inflow Event" in prompt_snapshot

    print(f"Output: {len(item['markdown_output'])} chars at {item['output_path']}")


# ---------------------------------------------------------------------------
# Multi-client real end-to-end: all maturing clients, max 5
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="This should be tested in test_reinvestment_proposals_propose_reinvestment_for_maturing_holdings")
def test_multi_client_reinvestment(proposal_server, fake_llm):
    """Real-HTTP inbound: POST /api/v1/reinvestment-proposals with explicit targets.

    1. Discover maturing bonds/bond funds locally.
    2. Deduplicate by client, cap at 5.
    3. Call the proposal server over real TCP with ALL targets.
    4. Verify every client gets a non-empty proposal with required sections.

    """
    # 1 ─ Discover maturing holdings ──────────────────────────────────
    maturing = search_holdings_maturing(
        product_types=["bond", "bond_fund"], within_days=30
    )

    seen_clients: set[str] = set()
    targets: list[dict[str, str]] = []
    for row in maturing:
        cid = row["client_id"]
        if cid not in seen_clients:
            seen_clients.add(cid)
            targets.append({
                "client_id": cid,
                "source_product_id": row["product_id"],
            })

    # Cap at 5 for manageable runtime
    targets = targets[:5]

    if not targets:
        targets = [
            {"client_id": "PB-HK-000010-9", "source_product_id": "ETF-HYG"},
        ]

    assert len(targets) >= 1, "Expected at least one reinvestment target"
    print(f"Processing {len(targets)} client(s): {[t['client_id'] for t in targets]}")

    # 2 ─ Call the proposal API over real HTTP ────────────────────────
    started_at = time.time()

    response = httpx.post(
        f"{proposal_server}/api/v1/reinvestment-proposals",
        json={
            "reinvestment_targets": targets,
            "response_mode": "both",
            "include_debug_scores": True,
        },
        timeout=60,
    )

    assert response.status_code == 200
    result = response.json()

    # 3 ─ Verify every client got a proposal ───────────────────────────
    assert result["status"] in {"success", "partial_error"}
    assert len(result["results_by_client"]) == len(targets)

    for item in result["results_by_client"]:
        cid = item["client_id"]
        assert "output_path" in item, f"{cid}: missing output_path"
        assert "markdown_output" in item, f"{cid}: missing markdown_output"
        assert len(item["markdown_output"]) > 0, f"{cid}: empty output"

        for section in ("Executive Summary", "Recommended", "Risk", "Justification"):
            assert section.lower() in item["markdown_output"].lower(), (
                f"{cid}: missing section '{section}'"
            )

        print(f"  {cid}: {len(item['markdown_output'])} chars at {item['output_path']}")

    prompt_snapshot = _read_latest_prompt_snapshot("reinvestment_proposal", started_at)
    assert "### client_profiles" in prompt_snapshot
    assert "### product_catalogs" in prompt_snapshot


# ---------------------------------------------------------------------------
# Slow HTTP: product opportunity proposal endpoints
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_product_opportunity_proposal(proposal_server):
    """HTTP regression: POST /api/v1/product-opportunity-proposal builds the prompt and returns 200."""
    started_at = time.time()

    response = httpx.post(
        f"{proposal_server}/api/v1/product-opportunity-proposal",
        json={
            "client_id": "PB-HK-000001-8",
            "product_id": "PROD016",
        },
        timeout=600,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["client_id"] == "PB-HK-000001-8"
    assert body["product_id"] == "PROD016"
    assert body["output_filename"].endswith(".md")
    assert "Executive Summary" in body["proposal_markdown"]
    assert "Detailed Justification" in body["proposal_markdown"]

    prompt_snapshot = _read_latest_prompt_snapshot("product_opportunity_proposal", started_at)
    assert "# Prompt Snapshot" in prompt_snapshot
    assert "### client_profiles" in prompt_snapshot
    assert "### product_catalogs" in prompt_snapshot
    assert "PB-HK-000001-8" in prompt_snapshot
    assert "PROD016" in prompt_snapshot


@pytest.mark.slow
def test_product_opportunity_proposal_automatch(proposal_server):
    """HTTP regression: POST /api/v1/product-opportunity-proposal-automatch builds matcher and proposal prompts."""
    started_at = time.time()

    response = httpx.post(
        f"{proposal_server}/api/v1/product-opportunity-proposal-automatch",
        json={
            "product_source": "default_yaml",
            "product_ids": ["bank_recommended"],
            "client_selection": {"risk_rating": [1, 5]},
            "run_matcher": True,
            "max_proposals": 1,
        },
        timeout=600,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["matcher_run_id"]
    assert body["total_clients_matched"] >= 0
    assert body["total_proposals_generated"] == 1
    assert len(body["proposals"]) == 1
    assert body["proposals"][0]["proposal_markdown"]

    matcher_prompt = _read_latest_prompt_snapshot("product_investor_matching", started_at)
    proposal_prompt = _read_latest_prompt_snapshot("product_opportunity_proposal", started_at)
    assert "### client_profiles" in matcher_prompt
    assert "### product_catalogs" in matcher_prompt
    assert "PB-HK-000001-8" in proposal_prompt
    assert "PROD016" in proposal_prompt


def test_product_opportunity_proposal_automatch_prompt_handoff_mocked(
    proposal_server,
    monkeypatch,
    tmp_path,
):
    """Fast regression: verify matcher note flows into the proposal prompt path without the real LLM.

    This keeps prompt-data validation lightweight while still exercising the
    endpoint wiring, matcher handoff, and proposal resolver assembly.
    """
    matcher_context = """### PB-HK-000005-9 (Emma Thompson)

- **Suggestion:** Buy PROD003 US Corporate Bond Fund – USD 173,260 (5.6% of portfolio); funded by selling us5yt-rr US 5-Year Treasury Yield – USD 173,260.
- **Financial need:** Emma is a risk-averse retiree focused on capital preservation and a 12-month liquidity buffer.
- **Key factors:** Her risk rating of 1 is matched by the low-risk fixed-income profile of PROD003.
- **Return comparison:** The recommended product's expected return is 5.2% versus 3.02% for the existing us5yt-rr Treasury position.
- **Concentration impact:** The trade reduces single-maturity duration concentration while the 32% cash buffer remains unchanged.
"""

    fake_matcher_result = {
        "run_id": "run-mocked",
        "summary": {"status": "success"},
        "final_proposals": [
            {
                "client_id": "PB-HK-000005-9",
                "product_id": "PROD003",
                "investment_amount": "173,260",
                "funding_source": "us5yt-rr",
                "buying_score": 4.0,
                "rationale": "Reduce cash drag and add investment-grade income without equity risk.",
                "alternative_product_ids": ["PROD007", "PROD020"],
                "matching_context": matcher_context,
            }
        ],
        "warnings": [],
        "errors": [],
    }

    monkeypatch.setattr(
        "src.integrations.product_investor_matcher.product_investor_matcher",
        lambda **kwargs: fake_matcher_result,
    )

    captured: dict = {}

    def fake_run_crew_planbot(**kwargs):
        captured["runtime_reference_overrides"] = kwargs.get("runtime_reference_overrides")
        api_resolver = kwargs["api_resolver"]
        captured["suggested_doc"] = api_resolver(API_SUGGESTED_PRODUCTS_AND_RATIONALE).content
        output_path = tmp_path / "proposal.md"
        output_path.write_text("# mock proposal\n", encoding="utf-8")
        return SimpleNamespace(output_path=output_path)

    monkeypatch.setattr(
        "src.integrations.product_opportunity_proposal.run_crew_planbot",
        fake_run_crew_planbot,
    )

    response = httpx.post(
        f"{proposal_server}/api/v1/product-opportunity-proposal-automatch",
        json={
            "product_source": "default_yaml",
            "product_ids": ["bank_recommended"],
            "client_selection": {"risk_rating": [1, 5]},
            "market_outlook": "string",
            "run_matcher": True,
            "max_proposals": 1,
        },
        timeout=60,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_proposals_generated"] == 1
    assert body["proposals"][0]["client_id"] == "PB-HK-000005-9"
    assert body["proposals"][0]["product_id"] == "PROD003"
    assert "suggested_products_and_rationale" in captured["runtime_reference_overrides"]
    assert "Emma Thompson" in captured["suggested_doc"]
    assert "PROD003" in captured["suggested_doc"]
    assert "**Suggestion:** Buy PROD003 US Corporate Bond Fund" in captured["suggested_doc"]
    assert "**Financial need:** Emma is a risk-averse retiree" in captured["suggested_doc"]
