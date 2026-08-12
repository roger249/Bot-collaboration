"""
Portfolio Review API — Generate portfolio health review for a single client.

All client and product data are retrieved through the integration APIs.
The endpoint composes reference files, invokes CrewAI, and returns proposal markdown.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import yaml

from src.planbot.crew_workflow import run_crew_planbot
from src.planbot.http_resolver import HttpApiResolver
from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_PRODUCT_CATALOG,
)
from src.shared.config_loader import load_config
from src.shared.resolver_formatters import (
    read_http_resolver_config,
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
    http_cfg = read_http_resolver_config(_CONFIG_PATH)
    if http_cfg is None:
        raise RuntimeError(
            "Portfolio review endpoint requires get_client_product_from_db=true "
            "in config_planbot.yaml common section."
        )

    # ── Fetch client data via HTTP resolver ──────────────────────────
    planbot_config = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    data_service_url = (planbot_config.get("common") or {}).get(
        "data_service_url", "http://localhost:8000/api/v1",
    )
    base_url = data_service_url.replace("/api/v1", "")

    resolver = HttpApiResolver(
        client_id=client_id,
        base_url=base_url,
        timeout=http_cfg.get("timeout_seconds", 30),
        max_retries=http_cfg.get("max_retries", 3),
        retry_backoff_factor=http_cfg.get("retry_backoff_factor", 0.5),
    )

    try:
        client_profile = resolver.client_profile
    except Exception as exc:
        raise ConnectionError(
            f"Data service unreachable at {data_service_url}: {exc}"
        ) from exc

    if client_profile is None:
        raise LookupError(f"Client not found via HTTP: {client_id}")

    # ── Build api_resolver and runtime overrides ─────────────────────
    api_resolver = resolver.as_callable()
    client_doc = api_resolver(API_CLIENT_PROFILE)
    product_doc = api_resolver(API_PRODUCT_CATALOG)

    runtime_reference_overrides: dict[str, list[str]] = {
        "client_profiles": [client_doc.content],
        "product_catalogs": [product_doc.content],
    }
    if market_outlook:
        runtime_reference_overrides["market_outlook"] = [market_outlook]

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

    return {
        "client_id": client_id,
        "output_filename": output_path,
        "proposal_markdown": markdown,
    }
