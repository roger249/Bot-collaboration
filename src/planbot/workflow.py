from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.shared.config_loader import AppConfig, BotConfig
from src.shared.llm_client import LLMRequest, PromptTimeoutError, build_client
from src.shared.logging_utils import configure_logging
from src.planbot.config import load_planbot_config
from src.planbot.input_loader import (
    build_reference_block,
    extract_urls_from_references,
    load_markdown_references,
)
from src.shared.io_utils import read_text, write_text
from src.shared.run_utils import create_timestamped_run_root


LOGGER = logging.getLogger(__name__)


@dataclass
class PlanBotResult:
    run_root: Path
    log_path: Path
    output_path: Path
    prompt_path: Path
    references_used: int
    urls_used: int


def _build_user_prompt(
    task_prompt: str,
    references_block: str,
    urls: list[str],
    no_web_note: str | None,
    web_access: bool,
) -> str:
    parts = [task_prompt.strip(), "", "# Local markdown references", references_block]

    if urls:
        parts.append("")
        parts.append("# URLs")
        for url in urls:
            parts.append(f"- {url}")

    if not web_access and no_web_note:
        parts.extend(["", "# Web access note", no_web_note.strip()])

    return "\n".join(parts)


def run_planbot(app_config: AppConfig, config_path: str | Path) -> PlanBotResult:
    cfg = load_planbot_config(config_path, app_config.root_dir)

    run_root = create_timestamped_run_root(cfg.output_root, cfg.name)
    logs_dir = run_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_path = logs_dir / "planbot.log"
    chat_history_log_path = logs_dir / "chat_history.log"
    configure_logging(
        app_config.logging_level,
        log_path,
        chat_history_log_path,
        app_config.logging_config_file,
    )

    task_prompt = read_text(cfg.prompt_file)
    references = load_markdown_references(app_config.root_dir, cfg.reference_glob)
    references_block = build_reference_block(references)
    urls_from_references = extract_urls_from_references(references, url_reference_filename="websites.md")
    if not urls_from_references:
        # Fallback: pick up URLs from any reference file if websites.md is absent or empty.
        urls_from_references = extract_urls_from_references(references, url_reference_filename=None)
    urls = list(dict.fromkeys([*cfg.urls, *urls_from_references]))

    no_web_note: str | None = None
    if cfg.shared_no_web_note_file and cfg.shared_no_web_note_file.exists():
        no_web_note = read_text(cfg.shared_no_web_note_file)

    user_prompt = _build_user_prompt(
        task_prompt=task_prompt,
        references_block=references_block,
        urls=urls,
        no_web_note=no_web_note,
        web_access=cfg.web_access,
    )

    system_prompt = (
        "You are PlanBot. Follow the task prompt and output template exactly. "
        "Return only the requested markdown sections with no preamble."
    )

    bot_config = BotConfig(
        provider=cfg.provider,
        model=cfg.model,
        prompt_file=cfg.prompt_file,
        temperature=cfg.temperature,
    )
    client = build_client(app_config, "planbot", bot_config)

    request = LLMRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=cfg.model,
        temperature=cfg.temperature,
    )

    try:
        output = client.generate(request)
    except PromptTimeoutError:
        LOGGER.error("PlanBot prompt timed out")
        raise

    output_path = run_root / cfg.output_filename
    write_text(output_path, output)

    prompt_snapshot = run_root / "prompt_snapshot.md"
    write_text(prompt_snapshot, user_prompt)

    return PlanBotResult(
        run_root=run_root,
        log_path=log_path,
        output_path=output_path,
        prompt_path=prompt_snapshot,
        references_used=len(references),
        urls_used=len(urls),
    )
