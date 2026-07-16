from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from crewai import Agent, Crew, LLM, Process, Task

from src.planbot.config import load_planbot_config
from src.planbot.input_loader import (
    ReferenceDocument,
    extract_urls_from_references,
    load_references,
)
from src.planbot.workflow import (
    PlanBotResult,
    _build_prompt_snapshot_payload,
    _build_reference_payload,
    _build_user_prompt,
    _normalize_planbot_output,
    _resolve_output_filename,
)
from src.shared.config_loader import AppConfig, BotConfig
from src.shared.io_utils import write_text
from src.shared.llm_client import (
    LLMRequest,
    _resolve_api_key,
    _sanitize_transport_body,
    build_client,
    configure_transport_logging,
)
from src.shared.logging_utils import configure_logging
from src.shared.run_utils import create_run_root

LOGGER = logging.getLogger(__name__)
CHAT_HISTORY_TRANSPORT_LOGGER = logging.getLogger("chat_history.transport")
CHAT_HISTORY_TOOL_LOGGER = logging.getLogger("chat_history.tool")


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _payload_sizes(text: str) -> tuple[int, int]:
    return len(text), len(text.encode("utf-8"))


def _build_crew_llm(app_config: AppConfig, cfg) -> LLM:
    provider = app_config.providers.get(cfg.provider)
    if provider is None:
        raise ValueError(f"Unknown provider '{cfg.provider}' in providers config.")
    api_key = _resolve_api_key(provider.api_key_env)
    # base_url = provider.base_url.rstrip("/")
    base_url = str(provider.base_url).rstrip("/")
    return LLM(
        model=f"openai/{cfg.model}",
        base_url=base_url,
        api_key=api_key,
        temperature=cfg.temperature,
        timeout=provider.timeout_seconds,
    )


def _build_tool_instance(tool_name: str) -> Any:
    normalized = str(tool_name).strip()
    if not normalized:
        raise ValueError("Agent tool name cannot be empty.")

    if normalized == "Crawl4AI":
        try:
            from src.planbot.crawl4ai_tool import Crawl4AITool
        except ImportError as exc:
            raise RuntimeError(
                "Crawl4AI dependency is missing. Install it with: uv pip install crawl4ai && crawl4ai-setup"
            ) from exc

        tool = Crawl4AITool()
        return _with_web_tool_input_guidance(tool)

    if normalized == "ScrapeWebsiteTool":
        try:
            from crewai_tools import ScrapeWebsiteTool
        except ImportError as exc:
            raise RuntimeError(
                "ScrapeWebsiteTool dependency is missing. Install it with: uv pip install crewai-tools"
            ) from exc

        tool = ScrapeWebsiteTool()
        return _with_web_tool_input_guidance(tool)

    if normalized == "ScrapflyScrapeWebsiteTool":
        scrapfly_api_key = os.getenv("SCRAPFLY_API_KEY", "").strip()
        if not scrapfly_api_key:
            raise ValueError(
                "SCRAPFLY_API_KEY is required when using ScrapflyScrapeWebsiteTool. "
                "Set it in your environment or .env file."
            )

        try:
            from crewai_tools import ScrapflyScrapeWebsiteTool
        except ImportError as exc:
            raise RuntimeError(
                "Scrapfly tool dependency is missing. Install it with: uv pip install crewai-tools"
            ) from exc

        try:
            tool = ScrapflyScrapeWebsiteTool(api_key=scrapfly_api_key)
            return _with_web_tool_input_guidance(tool)
        except TypeError:
            # Some versions read SCRAPFLY_API_KEY directly from environment.
            tool = ScrapflyScrapeWebsiteTool()
            return _with_web_tool_input_guidance(tool)

    if normalized == "YFinance":
        try:
            from src.planbot.yfinance_tool import YFinanceTool
        except ImportError as exc:
            raise RuntimeError(
                "YFinance tool dependency is missing. Install it with: uv pip install yfinance"
            ) from exc

        return _with_yfinance_tool_input_guidance(YFinanceTool())

    if normalized != "FirecrawlScrapeWebsiteTool":
        raise ValueError(f"Unsupported tool '{normalized}' in agent config.")

    firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not firecrawl_api_key:
        raise ValueError(
            "FIRECRAWL_API_KEY is required when using FirecrawlScrapeWebsiteTool. "
            "Set it in your environment or .env file."
        )

    try:
        from crewai_tools import FirecrawlScrapeWebsiteTool
    except ImportError as exc:
        raise RuntimeError(
            "Firecrawl tool dependency is missing. Install it with: uv pip install firecrawl-py crewai-tools"
        ) from exc

    try:
        tool = FirecrawlScrapeWebsiteTool(api_key=firecrawl_api_key)
        return _with_web_tool_input_guidance(tool)
    except TypeError:
        # Some versions read FIRECRAWL_API_KEY directly from environment.
        tool = FirecrawlScrapeWebsiteTool()
        return _with_web_tool_input_guidance(tool)


def _with_web_tool_input_guidance(tool: Any) -> Any:
    """Append strict Action Input guidance to web-retrieval tool descriptions."""
    guidance = (
        " Action Input format rule: provide a single key-value dictionary per tool call."
        " For web scraping tools, pass exactly one URL in one call, for example"
        " {\"website_url\": \"https://example.com\"} or {\"url\": \"https://example.com\"}."
        " Do not pass a list of dictionaries in one call."
    )

    description = str(getattr(tool, "description", "") or "")
    if guidance.strip() not in description:
        setattr(tool, "description", (description + guidance).strip())
    return tool


def _with_yfinance_tool_input_guidance(tool: Any) -> Any:
    """Append strict Action Input guidance to YFinance tool description."""
    guidance = (
        " Action Input format rule: provide a single key-value dictionary per tool call."
        " Pass exactly one ticker in one call, for example {\"ticker\": \"9988.HK\"}."
        " Do not pass a list of dictionaries or mixed narrative text in Action Input."
        " Set include_financial_statement/include_price_history only when needed."
    )

    description = str(getattr(tool, "description", "") or "")
    if guidance.strip() not in description:
        setattr(tool, "description", (description + guidance).strip())
    return tool


def _serialize_tool_log_payload(value: object) -> str:
    try:
        return _sanitize_transport_body(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return _sanitize_transport_body(str(value))


def _instrument_tool(tool: Any, configured_name: str) -> Any:
    tool_cls = tool.__class__

    def _wrap_class_method(method_name: str) -> None:
        original = getattr(tool_cls, method_name, None)
        if not callable(original) or getattr(original, "_tool_logging_wrapped", False):
            return

        def _logged(self, *args, **kwargs):
            call_id = uuid.uuid4().hex[:12]
            started = time.perf_counter()
            runtime_tool_name = str(getattr(self, "name", configured_name) or configured_name)
            CHAT_HISTORY_TOOL_LOGGER.debug(
                "tool invoke\n=== id ===\n%s\n=== tool ===\n%s\n=== method ===\n%s\n=== params ===\n%s",
                call_id,
                runtime_tool_name,
                method_name,
                _serialize_tool_log_payload({"args": args, "kwargs": kwargs}),
            )
            try:
                result = original(self, *args, **kwargs)
            except Exception as exc:
                duration_ms = (time.perf_counter() - started) * 1000
                CHAT_HISTORY_TOOL_LOGGER.debug(
                    "tool return\n=== id ===\n%s\n=== tool ===\n%s\n=== method ===\n%s\n=== status ===\nerror\n=== duration_ms ===\n%.2f\n=== response ===\n%s",
                    call_id,
                    runtime_tool_name,
                    method_name,
                    duration_ms,
                    _serialize_tool_log_payload({"error_type": type(exc).__name__, "error": str(exc)}),
                )
                raise

            duration_ms = (time.perf_counter() - started) * 1000
            CHAT_HISTORY_TOOL_LOGGER.debug(
                "tool return\n=== id ===\n%s\n=== tool ===\n%s\n=== method ===\n%s\n=== status ===\nsuccess\n=== duration_ms ===\n%.2f\n=== response ===\n%s",
                call_id,
                runtime_tool_name,
                method_name,
                duration_ms,
                _serialize_tool_log_payload({"result": result}),
            )
            return result

        setattr(_logged, "_tool_logging_wrapped", True)
        setattr(tool_cls, method_name, _logged)

    # CrewAI tools may execute through either run or _run depending on version.
    _wrap_class_method("run")
    _wrap_class_method("_run")
    return tool


_ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", re.ASCII)


@contextlib.contextmanager
def _tee_stdout_to_log(log_path: Path):
    """Tee sys.stdout to log_path (ANSI codes stripped) while keeping live console output."""
    original_stdout = sys.stdout
    with log_path.open("a", encoding="utf-8") as _log_file:

        class _TeeStream:
            def write(self, text: str) -> int:
                original_stdout.write(text)
                clean = _ANSI_ESCAPE.sub("", text)
                if clean and not _log_file.closed:
                    try:
                        _log_file.write(clean)
                    except ValueError:
                        pass  # file closed by context manager before deferred event fired
                return len(text)

            def flush(self) -> None:
                original_stdout.flush()
                if not _log_file.closed:
                    try:
                        _log_file.flush()
                    except ValueError:
                        pass

            def isatty(self) -> bool:
                return False

            @property
            def encoding(self) -> str:
                return getattr(original_stdout, "encoding", "utf-8")

            @property
            def errors(self) -> str | None:
                return getattr(original_stdout, "errors", None)

        sys.stdout = _TeeStream()  # type: ignore[assignment]
        try:
            yield
        finally:
            sys.stdout = original_stdout


def _resolve_agent_tools(agent_def: dict[str, Any]) -> list[Any]:
    tool_names = agent_def.get("tools")
    if not tool_names:
        return []

    if not isinstance(tool_names, list):
        raise ValueError("Agent 'tools' field must be a list of tool names.")

    # Add logging for tool resolution
    LOGGER.info("Resolving tools: %s", tool_names)

    return [_instrument_tool(_build_tool_instance(name), str(name)) for name in tool_names]


def _generate_with_crew(
    app_config: AppConfig,
    cfg,
    user_prompt: str,
    crewai_verbose: bool = False,
    log_path: Path | None = None,
) -> str:
    agents_cfg = _load_yaml(cfg.crewai_config_folder / "agents.yaml")
    tasks_cfg = _load_yaml(cfg.crewai_config_folder / "tasks.yaml")

    llm = _build_crew_llm(app_config, cfg)

    task_def = tasks_cfg.get(cfg.task_name)
    if not task_def:
        available_tasks = ", ".join(sorted(tasks_cfg.keys())) or "<none>"
        raise ValueError(
            f"Task '{cfg.task_name}' not found in {cfg.crewai_config_folder / 'tasks.yaml'}. "
            f"Available tasks: {available_tasks}"
        )

    agent_name = str(task_def.get("agent", "")).strip()
    agent_def = agents_cfg.get(agent_name) if agent_name else None
    if agent_def is None:
        agent_def = next(iter(agents_cfg.values()), None)
    if agent_def is None:
        raise ValueError("No agent definitions found in CrewAI agents config.")

    agent_tools = _resolve_agent_tools(agent_def)
    if agent_tools:
        LOGGER.info("Resolved %s tool(s) for agent '%s'", len(agent_tools), agent_name or "<default>")

    agent = Agent(
        role=agent_def["role"],
        goal=agent_def["goal"],
        backstory=agent_def["backstory"].strip(),
        llm=llm,
        tools=agent_tools,
        allow_delegation=False,
        verbose=crewai_verbose,
    )

    task = Task(
        description=user_prompt,
        expected_output=task_def["expected_output"],
        agent=agent,
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=crewai_verbose,
    )

    transport_payload = json.dumps(
        {
            "provider": cfg.provider,
            "model": cfg.model,
            "temperature": cfg.temperature,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
            "task_expected_output": task_def["expected_output"],
        },
        ensure_ascii=False,
    )
    request_chars, request_bytes = _payload_sizes(transport_payload)
    CHAT_HISTORY_TRANSPORT_LOGGER.debug(
        "transport request\n=== route ===\ncrewai.kickoff\n=== size ===\nchars=%s bytes=%s\n=== body ===\n%s",
        request_chars,
        request_bytes,
        _sanitize_transport_body(transport_payload),
    )

    LOGGER.info("Sending request via CrewAI (model=%s, provider=%s)", cfg.model, cfg.provider)
    try:
        if crewai_verbose and log_path is not None:
            with _tee_stdout_to_log(log_path):
                result = crew.kickoff()
        else:
            result = crew.kickoff()
    except Exception as exc:
        CHAT_HISTORY_TRANSPORT_LOGGER.debug(
            "transport response\n=== status ===\nerror\n=== body ===\n%s",
            str(exc),
        )
        raise

    output = str(result.raw) if hasattr(result, "raw") else str(result)
    response_chars, response_bytes = _payload_sizes(output)
    CHAT_HISTORY_TRANSPORT_LOGGER.debug(
        "transport response\n=== status ===\nsuccess\n=== size ===\nchars=%s bytes=%s\n=== body ===\n%s",
        response_chars,
        response_bytes,
        _sanitize_transport_body(output),
    )
    LOGGER.info("Response received from CrewAI crew")
    return output


def run_crew_planbot(
    app_config: AppConfig,
    config_path: str | Path,
    proposal_name: str = "portfolio_review",
    runtime_reference_overrides: dict[str, list[str]] | None = None,
    output_file_override: str | Path | None = None,
) -> PlanBotResult:
    """
    This function will build the prompt payload as follow.
        - The prompt will include a system prompt, a user prompt that describes the task and includes the reference materials.
        - The task definition will be loaded from the CrewAI agents.yaml and becomes the system prompt.
        - The user prompt will be constructed to include
            - the task description 
            - the reference materials as a JSON payload that contains the content of the reference documents, client profiles, product catalogs, and URLs. 
    """
    cfg = load_planbot_config(config_path, app_config.root_dir, proposal_name)

    preserve_existing_run_root = output_file_override is not None
    run_root = create_run_root(
        cfg.output_root,
        cfg.name,
        cfg.overwrite_output_folder,
        preserve_existing=preserve_existing_run_root,
    )
    logs_dir = run_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_path = logs_dir / "planbot.log"
    chat_history_log_path = logs_dir / "chat_history.log"
    configure_logging(
        app_config.logging_level,
        log_path,
        chat_history_log_path,
        app_config.logging_config_file,
        chat_history_enabled=app_config.logging_chat_history_enabled,
        chat_history_max_bytes=app_config.logging_chat_history_max_bytes,
        chat_history_backup_count=app_config.logging_chat_history_backup_count,
        api_debug_level=app_config.logging_api_debug_level,
    )
    configure_transport_logging(
        body_max_chars=app_config.logging_chat_history_body_max_chars,
        redact_fields=app_config.logging_chat_history_redact_fields,
    )

    LOGGER.info("PlanBot crew run starting: config=%s", config_path)
    LOGGER.info("Using crewai config folder: %s", cfg.crewai_config_folder)

    loaded_sections: dict[str, tuple[str, list[ReferenceDocument]]] = {}
    all_docs: list[ReferenceDocument] = []
    for section_name, section_cfg in cfg.reference_sections.items():
        effective_globs = section_cfg.globs
        if runtime_reference_overrides and section_name in runtime_reference_overrides:
            # Per-invocation override replaces static section globs for deterministic fan-out inputs.
            override_globs = runtime_reference_overrides[section_name]
            effective_globs = override_globs or section_cfg.globs
            LOGGER.info(
                "Using runtime reference override for section '%s': %s",
                section_name,
                effective_globs,
            )

        docs = load_references(app_config.root_dir, effective_globs)
        loaded_sections[section_name] = (section_cfg.purpose, docs)
        all_docs.extend(docs)
        LOGGER.info("Loaded %s document(s) for section '%s' using globs %s", len(docs), section_name, effective_globs)

    urls_from_references = extract_urls_from_references(all_docs, url_reference_filename="websites.md")
    if not urls_from_references:
        urls_from_references = extract_urls_from_references(all_docs, url_reference_filename=None)
    urls = list(dict.fromkeys([*cfg.urls, *urls_from_references]))
    LOGGER.info("Resolved %s URL(s)", len(urls))

    reference_payload_json = _build_reference_payload(
        root_dir=app_config.root_dir,
        loaded_sections=loaded_sections,
    )

    tasks_cfg = _load_yaml(cfg.crewai_config_folder / "tasks.yaml")
    task_def = tasks_cfg.get(cfg.task_name)
    if not task_def:
        available_tasks = ", ".join(sorted(tasks_cfg.keys())) or "<none>"
        raise ValueError(
            f"Task '{cfg.task_name}' not found in {cfg.crewai_config_folder / 'tasks.yaml'}. "
            f"Available tasks: {available_tasks}"
        )
    task_prompt = str(task_def.get("description", "")).strip()

    user_prompt = _build_user_prompt(
        task_prompt=task_prompt,
        reference_payload_json=reference_payload_json,
    )

    total_docs = sum(len(docs) for _, docs in loaded_sections.values())
    LOGGER.info(
        "Payload composed: model=%s, total_documents=%s, sections=%s, urls=%s",
        cfg.model,
        total_docs,
        list(loaded_sections.keys()),
        len(urls),
    )

    if cfg.provider == "mock":
        LOGGER.info("Mock provider: using direct client (CrewAI path skipped for mock)")
        bot_config = BotConfig(
            provider=cfg.provider,
            model=cfg.model,
            prompt_file=Path("."),
            temperature=cfg.temperature,
        )
        request = LLMRequest(
            system_prompt="",
            user_prompt=user_prompt,
            model=cfg.model,
            temperature=cfg.temperature,
        )
        output = build_client(app_config, "planbot", bot_config).generate(request)
    else:
        output = _generate_with_crew(app_config, cfg, user_prompt, crewai_verbose=app_config.logging_crewai_verbose, log_path=log_path)

    output = _normalize_planbot_output(output)

    if output_file_override:
        output_override_path = Path(output_file_override)
        output_path = (
            output_override_path
            if output_override_path.is_absolute()
            else (app_config.root_dir / output_override_path)
        )
    else:
        output_path = run_root / _resolve_output_filename(cfg.output_filename, cfg.model)

    write_text(output_path, output)
    LOGGER.info("Output written to %s", output_path)

    prompt_snapshot = run_root / "prompt_snapshot.md"
    write_text(
        prompt_snapshot,
        _build_prompt_snapshot_payload(user_prompt, cfg.model, cfg.temperature),
    )

    LOGGER.info(
        "Run complete: total_documents=%s, urls_used=%s, run_root=%s",
        total_docs,
        len(urls),
        run_root,
    )

    return PlanBotResult(
        run_root=run_root,
        log_path=log_path,
        output_path=output_path,
        prompt_path=prompt_snapshot,
        references_used=total_docs,
        urls_used=len(urls),
    )

