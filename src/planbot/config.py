from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
import logging
from pydantic import BaseModel, ValidationError


class ReferenceSectionConfig(BaseModel):
    """One named reference section: a purpose description and a list of glob patterns."""
    purpose: str = ""
    globs: list[str]


class PlanBotConfig(BaseModel):
    name: str
    task_name: str
    output_root: Path
    overwrite_output_folder: bool = True
    output_filename: str
    crewai_config_folder: Path
    reference_sections: dict[str, ReferenceSectionConfig]
    shared_no_web_note_file: Path | None
    provider: str
    model: str
    temperature: float = 0.2
    web_access: bool = True
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
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    # Pydantic models for full validation of the PlanBot YAML
    class LLMEntry(BaseModel):
        provider: str
        model: str
        temperature: float = 0.2

    class CommonModel(BaseModel):
        crewai_config_folder: Path | str | None = "config/crewai/planbot"
        shared_no_web_note_file: str | None = None

    class ProposalModel(BaseModel):
        task: str | None = None
        output_root: Path | str | None = None
        data_root: Path | str | None = None
        references_root: Path | str | None = None
        crewai_config_folder: Path | str | None = None
        output_filename: str | None = None
        # Structured references dict: section_name -> list of {name, purpose}
        references: dict[str, Any]
        overwrite_output_folder: bool = True
        llm_model: str
        temperature: float = 0.2
        # Prompt-level flag passed to the LLM via the JSON payload. Does not gate any
        # runtime behaviour — it signals to the LLM whether it may browse the internet.
        # When False, the no_web_note text (e.g. "Do not access the internet") is also
        # injected into the payload to reinforce the restriction.
        web_access: bool = True
        urls: list[str] | None = None
        shared_no_web_note_file: Path | str | None = None

    class PlanBotFile(BaseModel):
        common: CommonModel | None = None
        llm_models: dict[str, LLMEntry] | None = None
        proposals: dict[str, ProposalModel]

    # Extract proposal sections (top-level keys except 'common' and 'llm_models')
    proposals_raw: dict[str, Any] = {k: v for k, v in data.items() if k not in ("common", "llm_models")}

    try:
        parsed = PlanBotFile(
            common=data.get("common"),
            llm_models=data.get("llm_models"),
            proposals=proposals_raw,
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid config_planbot.yaml: {exc}") from exc

    common = parsed.common or CommonModel()
    common_shared_no_web_note_file = common.shared_no_web_note_file
    common_crewai_config_folder = common.crewai_config_folder or "config/crewai/planbot"

    llm_models: dict[str, Any] = {k: v.dict() for k, v in (parsed.llm_models or {}).items()}

    raw_proposal = parsed.proposals.get(proposal_name)
    if not raw_proposal:
        available = ", ".join(sorted(parsed.proposals.keys())) or "<none>"
        raise ValueError(f"Missing '{proposal_name}' section in {config_path}. Available proposals: {available}")

    proposal_shared_no_web_note_file = raw_proposal.shared_no_web_note_file or common_shared_no_web_note_file
    proposal_crewai_explicitly_set = raw_proposal.crewai_config_folder is not None
    proposal_crewai_config_folder_raw = str(raw_proposal.crewai_config_folder or common_crewai_config_folder).strip()

    # Resolve base path for local reference globs.
    # Prefer explicit references_root, then data_root, then default proposal folder.
    if raw_proposal.references_root is not None:
        references_base_path = str(raw_proposal.references_root).strip()
    elif raw_proposal.data_root is not None:
        references_base_path = str(raw_proposal.data_root).strip()
    else:
        references_base_path = f"data/planbot/{proposal_name}"

    reference_sections: dict[str, ReferenceSectionConfig] = {}
    for section_name, entries in raw_proposal.references.items():
        if not isinstance(entries, list):
            raise ValueError(
                f"Section '{section_name}' under references in '{proposal_name}' must be a list of {{name, purpose}} entries."
            )
        globs: list[str] = []
        purposes: list[str] = []
        for entry in entries:
            if isinstance(entry, dict):
                glob_raw = str(entry.get("name", "")).strip()
                purpose_raw = str(entry.get("purpose", "")).strip()
            else:
                raise ValueError(
                    f"Entry under references.{section_name} in '{proposal_name}' must be a mapping with 'name' and optional 'purpose'."
                )
            if not glob_raw:
                raise ValueError(
                    f"Entry under references.{section_name} in '{proposal_name}' has empty 'name'."
                )
            globs.append(f"{references_base_path}/{glob_raw}")
            if purpose_raw:
                purposes.append(purpose_raw)

        section_purpose = "; ".join(purposes) if purposes else ""
        reference_sections[section_name] = ReferenceSectionConfig(purpose=section_purpose, globs=globs)

    # Resolve llm_model reference from top-level `llm_models` mapping.
    llm_model_ref = raw_proposal.llm_model
    if not llm_model_ref:
        raise ValueError(
            f"Missing 'llm_model' in '{proposal_name}' section of {config_path}; expected a reference to a top-level llm_models mapping."
        )

    llm_entry = llm_models.get(str(llm_model_ref))
    if not llm_entry:
        available = ", ".join(sorted(llm_models.keys())) or "<none>"
        raise ValueError(
            f"Unknown llm_model '{llm_model_ref}' referenced in {config_path}. Available llm_models: {available}"
        )

    provider_val = str(llm_entry.get("provider", "")).strip()
    model_val = str(llm_entry.get("model", "")).strip()
    temperature_val = float(llm_entry.get("temperature", raw_proposal.temperature or 0.2))

    logging.getLogger(__name__).debug(
        "Resolved llm_model '%s' -> provider=%s model=%s temperature=%s",
        llm_model_ref,
        provider_val,
        model_val,
        temperature_val,
    )

    return PlanBotConfig(
        name=proposal_name,
        task_name=str(raw_proposal.task or f"{proposal_name}_task").strip(),
        output_root=_resolve(root_dir, str(raw_proposal.output_root or f"runs/{proposal_name}")),
        overwrite_output_folder=bool(raw_proposal.overwrite_output_folder) if raw_proposal.overwrite_output_folder is not None else False,
        output_filename=str(raw_proposal.output_filename or "output.md").strip(),
        crewai_config_folder=_resolve_crewai_folder(
            root_dir=root_dir,
            proposal_base_path=references_base_path,
            common_folder_raw=str(common_crewai_config_folder),
            proposal_folder_raw=proposal_crewai_config_folder_raw,
            proposal_explicitly_set=proposal_crewai_explicitly_set,
        ),
        reference_sections=reference_sections,
        shared_no_web_note_file=(
            _resolve(root_dir, str(proposal_shared_no_web_note_file)) if proposal_shared_no_web_note_file else None
        ),
        provider=provider_val,
        model=model_val,
        temperature=temperature_val,
        web_access=bool(raw_proposal.web_access) if raw_proposal.web_access is not None else False,
        urls=[str(item).strip() for item in (raw_proposal.urls or []) if str(item).strip()],
    )
