import pytest
import httpx

from src import main
from src.integrations.client_api import search_holdings_maturing


def test_run_product_opportunity_proposal_monkeypatched(monkeypatch):
    called = {}

    def fake_run(app_config, cfg_path, proposal):
        called['args'] = (app_config, cfg_path, proposal)
        class Dummy:
            pass

        return Dummy()

    monkeypatch.setattr(main, 'run_crew_planbot', fake_run)

    result = main.run_planbot_programmatically(
        config_path='config/config.yaml',
        planbot_config='config/config_planbot.yaml',
        proposal='product_opportunity_proposal',
    )

    assert 'args' in called
    assert called['args'][1] == 'config/config_planbot.yaml'
    assert called['args'][2] == 'product_opportunity_proposal'
    assert result is not None


# ---------------------------------------------------------------------------
# Real end-to-end pipeline: maturing API → CrewAI LLM proposal
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_propose_reinvestment_for_maturing_holdings(monkeypatch, proposal_server):
    """Real-HTTP inbound: proposal API via httpx → server in thread.

    1. Call ``POST .../propose_reinvestment_for_maturing_holdings`` over real
       TCP — discovers maturing bonds, caps at 1 client, invokes LLM.
    2. Verify the output contains required section headers.

    Data lookups use the adapter (DuckDB by default; REST via the config flag).
    """
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
    assert result["status"] == "success"
    assert len(result["results_by_client"]) == 1

    item = result["results_by_client"][0]
    assert "output_path" in item
    assert "markdown_output" in item
    assert len(item["markdown_output"]) > 0

    for section in ("Executive Summary", "Recommended", "Risk", "Justification"):
        assert section.lower() in item["markdown_output"].lower()

    print(f"Output: {len(item['markdown_output'])} chars at {item['output_path']}")


# ---------------------------------------------------------------------------
# Multi-client real end-to-end: all maturing clients, max 5
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_multi_client_propose_reinvestment(monkeypatch, proposal_server):
    """Real-HTTP inbound: POST /api/v1/reinvestment-proposals with explicit targets.

    1. Discover maturing bonds/bond funds locally.
    2. Deduplicate by client, cap at 5.
    3. Call the proposal server over real TCP with ALL targets.
    4. Verify every client gets a non-empty proposal with required sections.

    Data lookups use the adapter (DuckDB by default; REST via the config flag).
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
    response = httpx.post(
        f"{proposal_server}/api/v1/reinvestment-proposals",
        json={
            "reinvestment_targets": targets,
            "response_mode": "both",
            "include_debug_scores": True,
        },
        timeout=600,
    )

    assert response.status_code == 200
    result = response.json()

    # 3 ─ Verify every client got a proposal ───────────────────────────
    assert result["status"] == "success"
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


# ---------------------------------------------------------------------------
# Fast HTTP: product opportunity proposal endpoints
# ---------------------------------------------------------------------------


def test_product_opportunity_proposal(monkeypatch, proposal_server):
    """HTTP regression: POST /api/v1/product-opportunity-proposal returns 200."""
    monkeypatch.setattr(
        "src.integrations.proposal_server.propose_product_opportunity",
        lambda **kwargs: {
            "client_id": kwargs["client_id"],
            "product_id": kwargs["product_id"],
            "output_filename": "runs/product_opportunity_proposal/test.md",
            "proposal_markdown": "# Product Opportunity Proposal\n\n## Investment Recommendation\n",
            "metadata": {"product_fitness_scores": []},
        },
    )

    response = httpx.post(
        f"{proposal_server}/api/v1/product-opportunity-proposal",
        json={
            "client_id": "PB-HK-000001-8",
            "product_id": "PROD016",
            "rationale": "Test rationale for proposal generation.",
        },
        timeout=30,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["client_id"] == "PB-HK-000001-8"
    assert body["product_id"] == "PROD016"
    assert body["output_filename"].endswith("test.md")
    assert "Investment Recommendation" in body["proposal_markdown"]


def test_product_opportunity_proposal_automatch(monkeypatch, proposal_server):
    """HTTP regression: POST /api/v1/product-opportunity-proposal-automatch returns 200."""
    monkeypatch.setattr(
        "src.integrations.proposal_server.propose_product_opportunity_automatch",
        lambda **kwargs: {
            "matcher_run_id": "run-20260810-120000",
            "total_clients_matched": 1,
            "total_proposals_generated": 1,
            "proposals": [
                {
                    "client_id": "PB-HK-000001-8",
                    "product_id": "PROD016",
                    "output_filename": "runs/product_opportunity_proposal/test_automatch.md",
                    "proposal_markdown": "# Product Opportunity Proposal\n\n## Investment Recommendation\n",
                    "metadata": {"product_fitness_scores": []},
                }
            ],
            "errors": [],
        },
    )

    response = httpx.post(
        f"{proposal_server}/api/v1/product-opportunity-proposal-automatch",
        json={
            "product_source": "default_yaml",
            "product_ids": ["bank_recommended"],
            "client_selection": {"risk_rating": [1, 5]},
            "run_matcher": False,
            "max_proposals": 1,
        },
        timeout=30,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["matcher_run_id"] == "run-20260810-120000"
    assert body["total_clients_matched"] == 1
    assert body["total_proposals_generated"] == 1
    assert len(body["proposals"]) == 1
    assert body["errors"] == []
