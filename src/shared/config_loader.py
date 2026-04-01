from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml
from typing import Any


@dataclass
class BotConfig:
    provider: str
    model: str
    prompt_file: Path
    temperature: float


@dataclass
class WorkflowConfig:
    name: str
    spec_file: Path
    guideline_file: Path | None
    output_root: Path
    overwrite_output_folder: bool
    max_rounds: int
    stop_on_no_blockers: bool


@dataclass
class ProviderConfig:
    api_key_env: str
    base_url: str
    timeout_seconds: int


@dataclass
class AppConfig:
    root_dir: Path
    workflow: WorkflowConfig
    logging_level: str
    logging_config_file: Path | None
    author: BotConfig
    reviewer: BotConfig
    providers: dict[str, ProviderConfig]


def _resolve(root_dir: Path, raw_path: str) -> Path:
    return (root_dir / raw_path).resolve()


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path).resolve()
    root_dir = path.parent.parent
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))

    workflow = data["workflow"]
    guideline_file = workflow.get("guideline_file")
    logging_data = data.get("logging", {})
    logging_config_file = logging_data.get("config_file")
    runtime = data.get("runtime", {})
    default_timeout_seconds = int(runtime.get("default_timeout_seconds", 120))
    bots = data["bots"]
    providers = data.get("providers", {})

    parsed_providers: dict[str, ProviderConfig] = {}
    for provider_name, provider in providers.items():
        parsed_providers[provider_name] = ProviderConfig(
            api_key_env=provider["api_key_env"],
            base_url=provider["base_url"],
            timeout_seconds=int(provider.get("timeout_seconds", default_timeout_seconds)),
        )

    return AppConfig(
        root_dir=root_dir,
        workflow=WorkflowConfig(
            name=workflow["name"],
            spec_file=_resolve(root_dir, workflow["spec_file"]),
            guideline_file=_resolve(root_dir, guideline_file) if guideline_file else None,
            output_root=_resolve(root_dir, workflow["output_root"]),
            overwrite_output_folder=bool(workflow.get("overwrite_output_folder", False)),
            max_rounds=int(workflow["max_rounds"]),
            stop_on_no_blockers=bool(workflow.get("stop_on_no_blockers", True)),
        ),
        logging_level=logging_data.get("level", "INFO"),
        logging_config_file=_resolve(root_dir, logging_config_file) if logging_config_file else None,
        author=BotConfig(
            provider=bots["author"]["provider"].strip(),
            model=bots["author"]["model"].strip(),
            prompt_file=_resolve(root_dir, bots["author"]["prompt_file"]),
            temperature=float(bots["author"].get("temperature", 0.2)),
        ),
        reviewer=BotConfig(
            provider=bots["reviewer"]["provider"].strip(),
            model=bots["reviewer"]["model"].strip(),
            prompt_file=_resolve(root_dir, bots["reviewer"]["prompt_file"]),
            temperature=float(bots["reviewer"].get("temperature", 0.1)),
        ),
        providers=parsed_providers,
    )