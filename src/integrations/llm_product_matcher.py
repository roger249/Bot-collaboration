"""
LLM Product Matcher API — let the LLM discover and match products via tools.

POC proposal (see docs/specification/proposal/llm_product_matcher.md): unlike
``product_investor_matcher``, there is **no pre-computed Product Fitness Score
(PFS)** and **no investor-readiness (IRS) gate**.  The client is supplied
directly, and the LLM discovers candidate products itself through the
``ProductSearchTool`` tool (backed by ``search_similar``) and researches context
via web search.  The report reuses the ``product_investor_matching`` output
format.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from src.integrations.client_api import search_by_id
from src.planbot.crew_workflow import run_crew_planbot
from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    ReferenceDocument,
)
from src.planbot.pipeline_engine import (
    PipelineEngine,
    get_input_default_sources,
)
from src.planbot.workflow import read_prompt_snapshot
from src.shared.config_loader import load_config
from src.shared.market_outlook_utils import (
    API_MARKET_OUTLOOK,
    format_market_outlook_section,
    resolve_market_outlook,
)
from src.shared.resolver_formatters import (
    build_api_resolver,
    format_client_and_holdings,
    format_irs_section,
)

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def propose_llm_product_matcher(
    client_id: str,
    *,
    market_outlook: str | None = None,
    market_outlook_source: str | None = None,
    output_prompt_to_llm: bool = False,
) -> dict:
    """Run the LLM product matcher for a single client.

    Parameters
    ----------
    client_id : str
        Client identifier, supplied directly (no IRS gate).
    market_outlook : str | None
        Market narrative for LLM context.  When None, falls back to the
        file-globbed market outlook.
    market_outlook_source : str | None
        ``"request"`` or ``"static"``.  ``static`` ignores ``market_outlook``
        and always uses the static default.
    output_prompt_to_llm : bool
        When True, include the exact ``prompt_snapshot.md`` content (task
        prompt + reference sections) as ``prompt_to_llm`` in the response.

    Returns
    -------
    dict
        Response with ``client_id``, ``output_filename``, ``proposal_markdown``,
        and optionally ``prompt_to_llm``.
    """
    app_config = load_config(str(_ROOT_DIR / "config" / "config.yaml"))

    # Load pipeline config once — exposes input defs including the composite
    # `include` flags that drive client-profile assembly below.
    pipeline_engine = PipelineEngine(
        app_config, config_path=_CONFIG_PATH, proposal_id="llm_product_matcher"
    ).load()
    include_by_id = {inp.id: inp.include for inp in pipeline_engine.inputs}

    client_profile = search_by_id(client_id)
    if client_profile is None:
        raise LookupError(f"Client not found: {client_id}")

    effective_market_outlook = resolve_market_outlook(
        market_outlook,
        market_outlook_source,
        get_input_default_sources(_CONFIG_PATH).get("market_outlook", "request"),
    )

    # ── Build client content (with optional IRS reference section) ──
    extra: list[str] = []
    if include_by_id.get("client_profile", {}).get("investor_readiness_score"):
        irs_text = format_irs_section(
            total=client_profile.get("investor_readiness_score"),
            cash_drag=client_profile.get("cash_score"),
            concentration=client_profile.get("concentration_score"),
            active_management=client_profile.get("active_score"),
            life_stage=client_profile.get("life_stage_score"),
        )
        if irs_text:
            extra.append(irs_text)
    client_content = format_client_and_holdings(client_profile, extra_sections=extra)

    # ── Build api_resolver (client + market outlook; no product catalog) ──
    # Product discovery is done by the LLM via ProductSearchTool, so there is no
    # pre-rendered product universe fed as a reference.
    docs: dict[str, ReferenceDocument] = {
        API_CLIENT_PROFILE: ReferenceDocument(
            path=Path(API_CLIENT_PROFILE),
            content=client_content,
            source_type="markdown",
        ),
    }
    if effective_market_outlook is not None:
        docs[API_MARKET_OUTLOOK] = ReferenceDocument(
            path=Path(API_MARKET_OUTLOOK),
            content=format_market_outlook_section(effective_market_outlook),
            source_type="markdown",
        )
    api_resolver = build_api_resolver(docs)

    runtime_reference_overrides: dict[str, list[str]] = {
        "client_profile": [API_CLIENT_PROFILE],
    }
    if effective_market_outlook is not None:
        runtime_reference_overrides["market_outlook"] = [API_MARKET_OUTLOOK]

    # ── Invoke CrewAI ───────────────────────────────────────────────
    date_tag = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_file_override = (
        _ROOT_DIR / "runs" / "llm_product_matcher"
        / f"llm_product_matcher_{client_id}_{date_tag}.md"
    )

    result = run_crew_planbot(
        app_config=app_config,
        config_path=str(_CONFIG_PATH),
        proposal_name="llm_product_matcher",
        runtime_reference_overrides=runtime_reference_overrides,
        output_file_override=output_file_override,
        api_resolver=api_resolver,
    )

    output_path = str(result.output_path)
    proposal_markdown = ""
    if result.output_path and Path(result.output_path).exists():
        proposal_markdown = Path(result.output_path).read_text(encoding="utf-8")

    response: dict = {
        "client_id": client_id,
        "output_filename": output_path,
        "proposal_markdown": proposal_markdown,
    }

    if output_prompt_to_llm:
        response["prompt_to_llm"] = read_prompt_snapshot(result.prompt_path)

    return response
