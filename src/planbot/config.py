from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PlanBotConfig:
    name: str
    output_root: Path
    overwrite_output_folder: bool
    output_filename: str
    reference_glob: str
    system_prompt_file: Path | None
    prompt_file: Path
    shared_no_web_note_file: Path | None
    provider: str
    model: str
    temperature: float
    web_access: bool
    urls: list[str]


def _resolve(root_dir: Path, raw_path: str) -> Path:
    return (root_dir / raw_path).resolve()


def load_planbot_config(config_path: str | Path, root_dir: Path) -> PlanBotConfig:
    path = Path(config_path).resolve()
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))

    raw_planbot = data.get("planbot")
    if not raw_planbot:
        raise ValueError("Missing 'planbot' section in config file.")

    shared_no_web_note_file = raw_planbot.get("shared_no_web_note_file")
    system_prompt_file = raw_planbot.get("system_prompt_file")

    return PlanBotConfig(
        name=str(raw_planbot.get("name", "planbot")).strip(),
        output_root=_resolve(root_dir, str(raw_planbot.get("output_root", "runs/planbot"))),
        overwrite_output_folder=bool(raw_planbot.get("overwrite_output_folder", False)),
        output_filename=str(raw_planbot.get("output_filename", "output.md")).strip(),
        reference_glob=str(raw_planbot.get("reference_glob", "data/planbot/reference/*.md")).strip(),
        system_prompt_file=_resolve(root_dir, str(system_prompt_file)) if system_prompt_file else None,
        prompt_file=_resolve(root_dir, str(raw_planbot["prompt_file"])),
        shared_no_web_note_file=(
            _resolve(root_dir, str(shared_no_web_note_file)) if shared_no_web_note_file else None
        ),
        provider=str(raw_planbot.get("provider", "mock")).strip(),
        model=str(raw_planbot.get("model", "gpt-5.2")).strip(),
        temperature=float(raw_planbot.get("temperature", 0.2)),
        web_access=bool(raw_planbot.get("web_access", False)),
        urls=[str(item).strip() for item in raw_planbot.get("urls", []) if str(item).strip()],
    )
