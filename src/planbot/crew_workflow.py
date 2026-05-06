from __future__ import annotations

import json
import logging
from pathlib import Path

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
from src.shared.io_utils import read_text, write_text
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


def _generate_with_crew(
    app_config: AppConfig,
    cfg,
    user_prompt: str,
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

    agent = Agent(
        role=agent_def["role"],
        goal=agent_def["goal"],
        backstory=agent_def["backstory"].strip(),
        llm=llm,
        allow_delegation=False,
        verbose=False,
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
        verbose=False,
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


def run_crew_planbot(app_config: AppConfig, config_path: str | Path, proposal_name: str = "portfolio_review") -> PlanBotResult:
    """
    This function will build the prompt payload as follow.
        - The prompt will include a system prompt, a user prompt that describes the task and includes the reference materials.
        - The task definition will be loaded from the CrewAI agents.yaml and becomes the system prompt.
        - The user prompt will be constructed to include
            - the task description 
            - the reference materials as a JSON payload that contains the content of the reference documents, client profiles, product catalogs, and URLs. 
    """
    cfg = load_planbot_config(config_path, app_config.root_dir, proposal_name)

    run_root = create_run_root(cfg.output_root, cfg.name, cfg.overwrite_output_folder)
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
        docs = load_references(app_config.root_dir, section_cfg.globs)
        loaded_sections[section_name] = (section_cfg.purpose, docs)
        all_docs.extend(docs)
        LOGGER.info("Loaded %s document(s) for section '%s' using globs %s", len(docs), section_name, section_cfg.globs)

    urls_from_references = extract_urls_from_references(all_docs, url_reference_filename="websites.md")
    if not urls_from_references:
        urls_from_references = extract_urls_from_references(all_docs, url_reference_filename=None)
    urls = list(dict.fromkeys([*cfg.urls, *urls_from_references]))
    LOGGER.info("Resolved %s URL(s)", len(urls))

    no_web_note: str | None = None
    if cfg.shared_no_web_note_file and cfg.shared_no_web_note_file.exists():
        no_web_note = read_text(cfg.shared_no_web_note_file)

    reference_payload_json = _build_reference_payload(
        root_dir=app_config.root_dir,
        loaded_sections=loaded_sections,
        urls=urls,
        no_web_note=no_web_note,
        web_access=cfg.web_access,
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
        output = _generate_with_crew(app_config, cfg, user_prompt)

    output = _normalize_planbot_output(output)

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

