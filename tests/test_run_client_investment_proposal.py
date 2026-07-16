import pytest

from src import main
from src.integrations.client_api import search_holdings_maturing
from src.integrations.reinvestment_proposal import (
    propose_reinvestment,
    propose_reinvestment_for_maturing_holdings,
)


def test_run_client_product_fit_analysis_monkeypatched(monkeypatch):
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
        proposal='client_product_fit_analysis',
    )

    assert 'args' in called
    assert called['args'][1] == 'config/config_planbot.yaml'
    assert called['args'][2] == 'client_product_fit_analysis'
    assert result is not None


# ---------------------------------------------------------------------------
# Real end-to-end pipeline: maturing API → CrewAI LLM proposal
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_propose_reinvestment_for_maturing_holdings():
    """The convenience API discovers maturing holdings and generates one proposal.

    1. Call ``propose_reinvestment_for_maturing_holdings`` — discovers
       maturing bonds, caps at 1 client, and invokes the LLM.
    2. Verify the output file exists and contains required section headers.
    """
    result = propose_reinvestment_for_maturing_holdings(
        within_days=365 * 10,
        max_clients=1,
        response_mode="both",
        include_debug_scores=True,
    )

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
def test_multi_client_propose_reinvestment_for_maturing_holdings():
    """Chain all clients with maturing bonds, up to 5, through the API at once.

    1. Discover all maturing bonds/bond funds.
    2. Deduplicate by client, cap at 5.
    3. Call ``generate_reinvestment_proposal`` with ALL targets.
    4. Verify every client gets a non-empty proposal with required sections.
    """
    # 1 ─ Discover maturing holdings ──────────────────────────────────
    maturing = search_holdings_maturing(
        product_types=["bond", "bond_fund"], within_days=365 * 10
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

    # 2 ─ Call the API with ALL targets ────────────────────────────────
    result = propose_reinvestment(
        reinvestment_targets=targets,
        response_mode="both",
        include_debug_scores=True,
    )

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
