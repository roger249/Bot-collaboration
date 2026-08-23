"""
Portfolio Review API — Generate portfolio health review for a single client.

All client and product data are retrieved through the integration APIs.
The endpoint composes reference files, invokes CrewAI, and returns proposal markdown.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from src.integrations.client_api import search_by_id
from src.planbot.crew_workflow import run_crew_planbot
from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_PRODUCT_CATALOG,
)
from src.planbot.pipeline_engine import get_input_default_sources
from src.planbot.workflow import read_prompt_snapshot
from src.shared.config_loader import load_config
from src.shared.market_outlook_utils import (
    API_MARKET_OUTLOOK,
    resolve_market_outlook,
)
from src.shared.resolver_formatters import (
    build_proposal_resolver,
    format_client_and_holdings,
    format_product_catalog,
    resolve_holdings_to_products,
)

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def propose_portfolio_review(
    client_id: str,
    *,
    market_outlook: str | None = None,
    market_outlook_source: str | None = None,
    output_prompt_to_llm: bool = False,
) -> dict:
    """Generate a portfolio health review for a single client.

    Parameters
    ----------
    client_id : str
        Client identifier.
    market_outlook : str | None
        Market narrative for LLM context.  If None, the pipeline
        falls back to static market outlook files.
    market_outlook_source : str | None
        ``"request"`` or ``"static"``.  ``static`` ignores ``market_outlook``
        and always uses the static default.
    output_prompt_to_llm : bool
        Whether to return the exact prompt sent to the LLM as ``prompt_to_llm``.

    Returns
    -------
    dict
        Response with client_id, output_filename, proposal_markdown,
        and optionally prompt_to_llm.
    """
    client_profile = search_by_id(client_id)
    if client_profile is None:
        raise LookupError(f"Client not found: {client_id}")

    effective_market_outlook = resolve_market_outlook(
        market_outlook,
        market_outlook_source,
        get_input_default_sources(_CONFIG_PATH).get("market_outlook", "request"),
    )

    # Resolve the client's existing holdings to full product dicts for the
    # catalog reference (the LLM needs product details to review the portfolio).
    holdings_products = resolve_holdings_to_products(client_profile.get("holdings", []))

    api_resolver = build_proposal_resolver(
        client_content=format_client_and_holdings(client_profile),
        product_content=format_product_catalog(
            holdings=holdings_products or None,
        ),
        market_outlook=effective_market_outlook,
    )

    runtime_reference_overrides: dict[str, list[str]] = {
        "client_profile": [API_CLIENT_PROFILE],
        "product_catalog": [API_PRODUCT_CATALOG],
    }
    if effective_market_outlook is not None:
        runtime_reference_overrides["market_outlook"] = [API_MARKET_OUTLOOK]

    # ── Invoke CrewAI ───────────────────────────────────────────────
    date_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file_override = (
        _ROOT_DIR / "runs" / "portfolio_review"
        / f"portfolio_review_{client_id}_{date_tag}.md"
    )

    app_config = load_config(str(_ROOT_DIR / "config" / "config.yaml"))
    result = run_crew_planbot(
        app_config=app_config,
        config_path=str(_CONFIG_PATH),
        proposal_name="portfolio_review",
        runtime_reference_overrides=runtime_reference_overrides,
        output_file_override=output_file_override,
        api_resolver=api_resolver,
    )

    output_path = result.output_path
    if isinstance(output_path, Path):
        output_path = str(output_path)

    markdown = ""
    if output_path and Path(output_path).exists():
        markdown = Path(output_path).read_text(encoding="utf-8")

    response: dict = {
        "client_id": client_id,
        "output_filename": output_path,
        "proposal_markdown": markdown,
    }

    if output_prompt_to_llm:
        response["prompt_to_llm"] = read_prompt_snapshot(result.prompt_path)

    return response
