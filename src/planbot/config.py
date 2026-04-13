from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PlanBotConfig:
    name: str
    task_name: str
    output_root: Path
    overwrite_output_folder: bool
    output_filename: str
    crewai_config_folder: Path
    reference_glob: list[str]
    client_glob: list[str]
    product_catalog_glob: list[str]
    shared_no_web_note_file: Path | None
    provider: str
    model: str
    temperature: float
    web_access: bool
    urls: list[str]


def _resolve(root_dir: Path, raw_path: str) -> Path:
    return (root_dir / raw_path).resolve()


def _resolve_crewai_folder(
    root_dir: Path,
    proposal_base_path: str,
    common_folder_raw: str,
    proposal_folder_raw: str,
    proposal_explicitly_set: bool,
) -> Path:
    common_folder = _resolve(root_dir, common_folder_raw)

    # Prefer proposal-specific folder if it looks valid.
    if proposal_folder_raw.strip():
        proposal_raw = proposal_folder_raw.strip()
        candidates = [
            _resolve(root_dir, proposal_raw),
            _resolve(root_dir, f"{proposal_base_path}/{proposal_raw}"),
            (common_folder / proposal_raw).resolve(),
        ]
        for candidate in candidates:
            if (candidate / "agents.yaml").exists() and (candidate / "tasks.yaml").exists():
                return candidate

        if proposal_explicitly_set:
            raise FileNotFoundError(
                f"crewai_config_folder '{proposal_raw}' specified in proposal config, "
                f"but no valid agents.yaml + tasks.yaml found in any of:\n"
                + "\n".join(f"  {c}" for c in candidates)
            )

    return common_folder


def load_planbot_config(config_path: str | Path, root_dir: Path, proposal_name: str = "portfolio_review") -> PlanBotConfig:
    """Load PlanBot config from config_planbot.yaml.
    
    Args:
        config_path: Path to config_planbot.yaml
        root_dir: Project root directory
        proposal_name: Name of the proposal section (e.g., 'portfolio_review', 'client_suitability')
    """
    path = Path(config_path).resolve()
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))

    # Load common config
    common = data.get("common", {})
    common_shared_no_web_note_file = common.get("shared_no_web_note_file")
    common_crewai_config_folder = common.get("crewai_config_folder", "config/crewai/planbot")

    # Load proposal-specific config
    raw_proposal = data.get(proposal_name)
    if not raw_proposal:
        raise ValueError(f"Missing '{proposal_name}' section in {config_path}")

    # Per-proposal value overrides common default when provided.
    proposal_shared_no_web_note_file = raw_proposal.get("shared_no_web_note_file", common_shared_no_web_note_file)
    proposal_crewai_explicitly_set = "crewai_config_folder" in raw_proposal
    proposal_crewai_config_folder_raw = str(raw_proposal.get(
        "crewai_config_folder",
        common_crewai_config_folder,
    )).strip()

    # Resolve paths
    prompt_root_rel = str(raw_proposal.get("prompt_root", f"data/planbot/{proposal_name}/prompts")).strip()

    # Extract proposal base path from prompt_root (remove /prompts suffix)
    # e.g., "data/planbot/portfolio_review/prompts" -> "data/planbot/portfolio_review"
    proposal_base_path = prompt_root_rel.rsplit("/prompts", 1)[0] if prompt_root_rel.endswith("/prompts") else prompt_root_rel.rsplit("/", 1)[0]

    # Construct glob patterns by concatenating proposal base path with relative globs from config.
    # Each glob key may be a string or a YAML list of strings.
    def _to_glob_list(raw_value: Any, default: str) -> list[str]:
        if raw_value is None:
            raw_value = default
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        return [f"{proposal_base_path}/{str(v).strip()}" for v in values]

    reference_glob_rel = _to_glob_list(raw_proposal.get('reference_glob'), 'references/*.md')
    client_glob_rel = _to_glob_list(raw_proposal.get('client_glob'), 'clients/*.md')
    product_catalog_glob_rel = _to_glob_list(raw_proposal.get('product_catalog_glob'), 'product_catalog/*.md')

    return PlanBotConfig(
        name=proposal_name,
        task_name=str(raw_proposal.get("task", f"{proposal_name}_task")).strip(),
        output_root=_resolve(root_dir, str(raw_proposal.get("output_root", f"runs/{proposal_name}"))),
        overwrite_output_folder=bool(raw_proposal.get("overwrite_output_folder", False)),
        output_filename=str(raw_proposal.get("output_filename", "output.md")).strip(),
        crewai_config_folder=_resolve_crewai_folder(
            root_dir=root_dir,
            proposal_base_path=proposal_base_path,
            common_folder_raw=str(common_crewai_config_folder),
            proposal_folder_raw=proposal_crewai_config_folder_raw,
            proposal_explicitly_set=proposal_crewai_explicitly_set,
        ),
        reference_glob=reference_glob_rel,
        client_glob=client_glob_rel,
        product_catalog_glob=product_catalog_glob_rel,
        shared_no_web_note_file=(
            _resolve(root_dir, str(proposal_shared_no_web_note_file)) if proposal_shared_no_web_note_file else None
        ),
        provider=str(raw_proposal.get("provider", "mock")).strip(),
        model=str(raw_proposal.get("model", "gpt-5.2")).strip(),
        temperature=float(raw_proposal.get("temperature", 0.2)),
        web_access=bool(raw_proposal.get("web_access", False)),
        urls=[str(item).strip() for item in raw_proposal.get("urls", []) if str(item).strip()],
    )
