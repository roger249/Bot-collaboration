from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
import logging
from pydantic import BaseModel, DirectoryPath, ValidationError


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
    get_client_product_from_restapi: bool = False


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


def _try_load_pipeline_config(
    data: dict[str, Any],
    root_dir: Path,
    proposal_name: str,
) -> PlanBotConfig | None:
    """Build a PlanBotConfig from ``pipeline.<proposal_name>``.

    CrewAI keys (`task`, `crewai_config_folder`, `output_root`,
    `output_filename`, `llm_model`) are derived from the pipeline id; the
    only proposal-specific blocks are ``matcher``, ``execution``, ``inputs``,
    ``input_policy``, ``prompt_packaging``, and ``quality_gates``.

    Returns None when ``proposal_name`` is not a pipeline id (legacy top-level
    sections are handled by the original path).
    """
    pipeline = data.get("pipeline") or {}
    proposal = pipeline.get(proposal_name)
    if proposal is None:
        return None

    execution = proposal.get("execution") or {}
    output_cfg = execution.get("output") or {}

    # Reference sections: 1:1 input id → section; purpose = description.
    input_defaults = data.get("input_defaults") or {}
    by_id = input_defaults.get("by_id") or {}
    reference_sections: dict[str, ReferenceSectionConfig] = {}
    for inp in proposal.get("inputs") or []:
        input_id = inp.get("id")
        if not input_id:
            continue
        id_defaults = by_id.get(input_id) or {}
        description = str(
            inp.get("description") or id_defaults.get("description") or ""
        )
        # File inputs: globs = `paths`.  runtime_or_static inputs: globs = the
        # static (non-`request.`) entries of `source_priority`.  api inputs:
        # empty globs (the wrapper injects them via runtime_reference_overrides).
        globs = [str(p) for p in (inp.get("paths") or [])]
        if not globs:
            source_priority = inp.get("source_priority") or []
            globs = [
                str(g) for g in source_priority
                if not str(g).startswith("request.")
            ]
        reference_sections[input_id] = ReferenceSectionConfig(
            purpose=description, globs=globs
        )

    # Resolve llm_model → provider/model/temperature via top-level llm_models.
    model_key = execution.get("model")
    llm_models = data.get("llm_models") or {}
    llm_entry = llm_models.get(str(model_key)) if model_key else None
    if not llm_entry:
        available = ", ".join(sorted(llm_models.keys())) or "<none>"
        raise ValueError(
            f"Unknown model '{model_key}' in pipeline.{proposal_name}.execution.model. "
            f"Available llm_models: {available}"
        )

    common_raw = data.get("common") or {}
    shared_no_web_note_file_raw = common_raw.get("shared_no_web_note_file")
    shared_no_web_note_file = (
        _resolve(root_dir, str(shared_no_web_note_file_raw))
        if shared_no_web_note_file_raw
        else None
    )
    get_client_product_from_restapi = bool(
        common_raw.get("get_client_product_from_restapi", False)
    )

    return PlanBotConfig(
        name=proposal_name,
        task_name=f"{proposal_name}_task",
        output_root=_resolve(root_dir, str(output_cfg.get("folder", f"runs/{proposal_name}"))),
        overwrite_output_folder=bool(output_cfg.get("overwrite", False)),
        output_filename=str(output_cfg.get("filename_template", f"{proposal_name}.md")),
        crewai_config_folder=_resolve(root_dir, f"data/planbot/{proposal_name}/crewai"),
        reference_sections=reference_sections,
        shared_no_web_note_file=shared_no_web_note_file,
        provider=str(llm_entry.get("provider", "")).strip(),
        model=str(llm_entry.get("model", "")).strip(),
        temperature=float(llm_entry.get("temperature", 0.2)),
        web_access=True,
        urls=[],
        get_client_product_from_restapi=get_client_product_from_restapi,
    )


def load_planbot_config(config_path: str | Path, root_dir: Path, proposal_name: str = "portfolio_review") -> PlanBotConfig:
    """Load PlanBot config from config_planbot.yaml.
    
    Args:
        config_path: Path to config_planbot.yaml
        root_dir: Project root directory
        proposal_name: Name of the proposal section (e.g., 'portfolio_review', 'client_suitability')
    """
    path = Path(config_path).resolve()
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    # Pipeline-id path: derive CrewAI config from pipeline.<proposal_name>.
    pipeline_config = _try_load_pipeline_config(data, root_dir, proposal_name)
    if pipeline_config is not None:
        return pipeline_config

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
        data_root: DirectoryPath | None = None
        references_root: DirectoryPath | None = None
        crewai_config_folder: DirectoryPath | None = None
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

    # Extract proposal sections (top-level keys except scoring configs, common, etc.)
    _non_proposal_keys = {
        "common", "llm_models", "run_configurations",
        "investor_readiness_score", "product_fitness_score", "server",
        "product_groups", "input_defaults", "pipeline", "data_source",
    }
    proposals_raw: dict[str, Any] = {
        k: v for k, v in data.items() if k not in _non_proposal_keys
    }

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

    # Read get_client_product_from_restapi from common section (defaults to False).
    common_raw = data.get("common") or {}
    get_client_product_from_restapi = bool(common_raw.get("get_client_product_from_restapi", False))

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
        if entries is None:
            # Skip sections with a null/None value — they are placeholder
            # slots to be resolved at runtime (e.g. suggested_products_and_rationale).
            continue
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
        get_client_product_from_restapi=get_client_product_from_restapi,
    )
