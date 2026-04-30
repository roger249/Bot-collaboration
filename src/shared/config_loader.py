from __future__ import annotations

from pathlib import Path
import yaml
from typing import Any

from pydantic import BaseModel


def _resolve(root_dir: Path, raw_path: str) -> Path:
    return (root_dir / raw_path).resolve()


class ProviderConfig(BaseModel):
    api_key_env: str
    base_url: str
    timeout_seconds: int


class BotConfig(BaseModel):
    provider: str
    model: str
    prompt_file: Path
    temperature: float


class WorkflowConfig(BaseModel):
    name: str
    spec_file: Path
    guideline_file: Path | None
    output_root: Path
    overwrite_output_folder: bool
    max_rounds: int
    stop_on_no_blockers: bool


class AppConfig(BaseModel):
    root_dir: Path
    workflow: WorkflowConfig
    logging_level: str
    logging_config_file: Path | None
    logging_chat_history_enabled: bool
    logging_chat_history_max_bytes: int
    logging_chat_history_backup_count: int
    logging_chat_history_body_max_chars: int
    logging_chat_history_redact_fields: list[str]
    author: BotConfig
    reviewer: BotConfig
    providers: dict[str, ProviderConfig]


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path).resolve()
    root_dir = path.parent.parent
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))

    # Raw schema validation using Pydantic to provide clear errors before conversion.
    try:
        class RawProvider(BaseModel):
            api_key_env: str
            base_url: str
            timeout_seconds: int | None = None

        class RawBot(BaseModel):
            provider: str
            model: str
            prompt_file: str
            temperature: float | None = None

        class RawWorkflow(BaseModel):
            name: str
            spec_file: str
            guideline_file: str | None = None
            output_root: str
            overwrite_output_folder: bool | None = None
            max_rounds: int
            stop_on_no_blockers: bool | None = None

        class RawLogging(BaseModel):
            level: str | None = None
            config_file: str | None = None
            chat_history_enabled: bool | None = None
            chat_history_max_bytes: int | None = None
            chat_history_backup_count: int | None = None
            chat_history_body_max_chars: int | None = None
            chat_history_redact_fields: list[str] | None = None

        class RawApp(BaseModel):
            workflow: RawWorkflow
            logging: RawLogging | None = None
            runtime: dict | None = None
            bots: dict[str, RawBot]
            providers: dict[str, RawProvider] | None = None

        RawApp.model_validate(data)
    except Exception as exc:
        import traceback

        raise ValueError("Invalid config.yaml: " + traceback.format_exc())

    workflow = data["workflow"]
    logging_data = data.get("logging", {})
    logging_config_file = logging_data.get("config_file")
    runtime = data.get("runtime", {})
    default_timeout_seconds = int(runtime.get("default_timeout_seconds", 120))
    bots = data["bots"]
    providers = data.get("providers", {}) or {}

    parsed_providers: dict[str, ProviderConfig] = {}
    for provider_name, provider in providers.items():
        parsed_providers[provider_name] = ProviderConfig(
            api_key_env=provider["api_key_env"],
            base_url=provider["base_url"],
            timeout_seconds=int(provider.get("timeout_seconds", default_timeout_seconds)),
        )

    # Build Pydantic AppConfig with resolved Paths
    author_bot = bots["author"]
    reviewer_bot = bots["reviewer"]

    app = AppConfig(
        root_dir=root_dir,
        workflow=WorkflowConfig(
            name=workflow["name"],
            spec_file=_resolve(root_dir, workflow["spec_file"]),
            guideline_file=_resolve(root_dir, logging_config_file) if logging_config_file else None,
            output_root=_resolve(root_dir, workflow["output_root"]),
            overwrite_output_folder=bool(workflow.get("overwrite_output_folder", False)),
            max_rounds=int(workflow["max_rounds"]),
            stop_on_no_blockers=bool(workflow.get("stop_on_no_blockers", True)),
        ),
        logging_level=logging_data.get("level", "INFO"),
        logging_config_file=_resolve(root_dir, logging_config_file) if logging_config_file else None,
        logging_chat_history_enabled=bool(logging_data.get("chat_history_enabled", True)),
        logging_chat_history_max_bytes=int(logging_data.get("chat_history_max_bytes", 5_000_000)),
        logging_chat_history_backup_count=int(logging_data.get("chat_history_backup_count", 5)),
        logging_chat_history_body_max_chars=int(logging_data.get("chat_history_body_max_chars", 20_000)),
        logging_chat_history_redact_fields=[
            str(item).strip()
            for item in logging_data.get("chat_history_redact_fields", ["authorization", "api_key"])
            if str(item).strip()
        ],
        author=BotConfig(
            provider=author_bot["provider"].strip(),
            model=author_bot["model"].strip(),
            prompt_file=_resolve(root_dir, author_bot["prompt_file"]),
            temperature=float(author_bot.get("temperature", 0.2)),
        ),
        reviewer=BotConfig(
            provider=reviewer_bot["provider"].strip(),
            model=reviewer_bot["model"].strip(),
            prompt_file=_resolve(root_dir, reviewer_bot["prompt_file"]),
            temperature=float(reviewer_bot.get("temperature", 0.1)),
        ),
        providers=parsed_providers,
    )

    return app