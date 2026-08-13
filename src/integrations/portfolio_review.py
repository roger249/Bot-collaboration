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
from src.planbot.pipeline_engine import get_input_descriptions
from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_PRODUCT_CATALOG,
)
from src.shared.config_loader import load_config
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
) -> dict:
    """Generate a portfolio health review for a single client.

    Parameters
    ----------
    client_id : str
        Client identifier.
    market_outlook : str | None
        Market narrative for LLM context.  If None, the pipeline
        falls back to static market outlook files.

    Returns
    -------
    dict
        Response with client_id, output_filename, proposal_markdown.
    """
    client_profile = search_by_id(client_id)
    if client_profile is None:
        raise LookupError(f"Client not found: {client_id}")

    # Resolve the client's existing holdings to full product dicts for the
    # catalog reference (the LLM needs product details to review the portfolio).
    holdings_products = resolve_holdings_to_products(client_profile.get("holdings", []))

    api_resolver = build_proposal_resolver(
        client_content=format_client_and_holdings(client_profile),
        product_content=format_product_catalog(
            holdings=holdings_products or None,
        ),
        market_outlook=market_outlook,
    )

    client_doc = api_resolver(API_CLIENT_PROFILE)
    product_doc = api_resolver(API_PRODUCT_CATALOG)

    runtime_reference_overrides: dict[str, list[str]] = {
        "client_profiles": [client_doc.content],
        "product_catalogs": [product_doc.content],
    }
    if market_outlook:
        runtime_reference_overrides["market_outlook"] = [market_outlook]

    descriptions = get_input_descriptions(_CONFIG_PATH)
    runtime_section_purposes = {
        "client_profiles": descriptions.get("client_profile", ""),
        "product_catalogs": descriptions.get("product_catalog", ""),
    }

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
        runtime_section_purposes=runtime_section_purposes,
        output_file_override=output_file_override,
        api_resolver=api_resolver,
    )

    output_path = result.output_path
    if isinstance(output_path, Path):
        output_path = str(output_path)

    markdown = ""
    if output_path and Path(output_path).exists():
        markdown = Path(output_path).read_text(encoding="utf-8")

    return {
        "client_id": client_id,
        "output_filename": output_path,
        "proposal_markdown": markdown,
    }
