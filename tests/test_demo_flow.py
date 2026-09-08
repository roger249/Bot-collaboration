"""Demo-flow tests — exercise the real proposal pipeline over HTTP.

Each test is one demo scenario from docs/specification/demo/demo_flow.md:

  Demo 1 — editing the RM note (qualitative_profile) changes the recommendation.
  Demo 2 — a structured product (FX TARF) is proposed to a risk-5 client.
  Demo 3 — maturing holdings are discovered and a reinvestment is proposed.

These are marked ``demo`` + ``slow`` (real LLM); run with ``--run-slow``.
"""

from __future__ import annotations

import time

import httpx
import pytest

pytestmark = [pytest.mark.demo, pytest.mark.slow, pytest.mark.parallel]

BASE = None  # set from the proposal_server fixture via fixture injection


def _automatch(base: str, product_ids: list[str], client_id: str) -> dict:
    r = httpx.post(
        f"{base}/api/v1/product-opportunity-proposal-automatch",
        json={
            "product_source": "default_yaml",
            "product_ids": product_ids,
            "client_selection": {"client_id": [client_id]},
            "run_matcher": True,
            "max_proposals": 1,
        },
        timeout=600.0,
    )
    r.raise_for_status()
    return r.json()


@pytest.fixture
def demo_reset(proposal_server):
    """Ensure demo test data is reset to baseline after each test."""
    yield
    httpx.post(f"{proposal_server}/api/v1/demo/reset", timeout=60.0)


def test_demo1_rm_note_changes_recommendation(proposal_server, demo_reset):
    """Editing the RM note flips/changes the recommended product."""
    base = proposal_server
    client_id = "PB-HK-000001-8"  # David Kim, risk 4

    t0 = time.perf_counter()
    before = _automatch(base, ["bank_recommended"], client_id)
    before_prod = before["proposals"][0]["product_id"]
    before_md = before["proposals"][0]["proposal_markdown"]
    t_before = time.perf_counter() - t0

    # Mutate the RM note to a technology-leaning preference.
    r = httpx.patch(
        f"{base}/api/v1/demo/clients/{client_id}",
        json={
            "qualitative_profile": (
                "Experienced executive with strong income stream. Actively "
                "manages portfolio; prefers evidence-based decisions. Strongly "
                "favours the technology sector and is comfortable with "
                "high-concentration growth exposure. Two children approaching "
                "university age — education funding is a near-term priority."
            )
        },
        timeout=60.0,
    )
    r.raise_for_status()

    t1 = time.perf_counter()
    after = _automatch(base, ["bank_recommended"], client_id)
    after_prod = after["proposals"][0]["product_id"]
    after_md = after["proposals"][0]["proposal_markdown"]
    t_after = time.perf_counter() - t1

    changed = (after_prod != before_prod) or ("tech" in after_md.lower())

    print(
        f"\nDemo1: before={before_prod} ({t_before:.1f}s) -> "
        f"after={after_prod} ({t_after:.1f}s) changed={changed}"
    )

    # The recommendation must change in product or narrative after the note edit.
    assert changed, (
        f"RM note edit did not change the recommendation "
        f"(before={before_prod}, after={after_prod})"
    )


def test_demo2_structured_product_proposed(proposal_server, demo_reset):
    """A structured product (FX TARF) is proposed to a risk-5 client."""
    base = proposal_server
    client_id = "PB-HK-000002-6"  # Sarah Chen, risk 5

    t0 = time.perf_counter()
    result = _automatch(base, ["structures"], client_id)
    t = time.perf_counter() - t0

    top = result["proposals"][0]["product_id"]
    print(f"\nDemo2: top={top} ({t:.1f}s)")

    assert top.startswith("FX-TARF-"), f"expected an FX-TARF structured product, got {top}"


def test_demo3_reinvestment_discovery(proposal_server, demo_reset):
    """Maturing holdings are discovered and a reinvestment is proposed."""
    base = proposal_server

    t0 = time.perf_counter()
    r = httpx.post(
        f"{base}/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings",
        json={
            "as_of_date": "2026-08-01",
            "within_days": 60,
            "max_clients": 1,
            "response_mode": "both",
        },
        timeout=600.0,
    )
    r.raise_for_status()
    body = r.json()
    t = time.perf_counter() - t0

    results = body.get("results_by_client", [])
    print(f"\nDemo3: {len(results)} client(s) ({t:.1f}s)")

    assert len(results) >= 1, "expected ≥1 client with a maturing holding"
    assert results[0].get("proposal_markdown"), "expected a generated proposal"
