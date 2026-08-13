"""
Proposal Pipeline Engine — configuration-driven proposal prompt assembly.

Reads proposal YAML configuration and input_defaults, resolves all inputs
(file globs, API calls, runtime_or_static fallback chains), builds the
``api_resolver`` and ``reference_sections`` config, and invokes
``run_crew_planbot`` with the compiled payload.

Architecture:
    PipelineEngine
        ├── _load_pipeline_config()     → reads proposal YAML + input_defaults
        ├── _resolve_inputs()            → resolves each input per its source
        ├── _run_pipeline()              → builds resolver + calls run_crew_planbot
        └── run()                        → public entry point
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.planbot.crew_workflow import run_crew_planbot
from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_PRODUCT_CATALOG,
    API_SUGGESTED_PRODUCTS_AND_RATIONALE,
    ReferenceDocument,
    load_references,
    read_text,
)
from src.shared.config_loader import AppConfig
from src.shared.market_outlook_utils import (
    API_MARKET_OUTLOOK,
    format_market_outlook_section,
)
from src.shared.resolver_formatters import build_api_resolver

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"

# ── Public data types ────────────────────────────────────────────────────


@dataclass
class PipelineResult:
    """Result of a pipeline run."""
    status: str  # "success", "partial_error", "error"
    output_path: str  # path to generated markdown
    diagnostics: dict = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)


@dataclass
class PipelinePrep:
    """Prepared pipeline context for wrapper consumption.

    The wrapper uses this to build its api_resolver and invoke
    ``run_crew_planbot`` with the correct runtime overrides.
    """
    resolved_inputs: dict[str, str]
    """All resolved non-API input content.  API inputs are empty strings."""
    api_input_ids: list[str]
    """Input IDs that need runtime API resolution by the wrapper."""
    file_reference_docs: list[ReferenceDocument]
    """Pre-resolved file-glob content as ReferenceDocuments."""
    decision_context_order: list[str]
    """Ordered list of decision_context input IDs."""
    references_order: list[str]
    """Ordered list of references input IDs."""
    execution: dict
    """Execution settings from YAML."""


# ── Internal data types ──────────────────────────────────────────────────


@dataclass
class _InputDef:
    """Resolved input definition after merging defaults."""
    id: str
    source: str  # "file", "api", "runtime_or_static"
    paths: list[str] = field(default_factory=list)
    prompt_section: str = "references"  # "decision_context" or "references"
    required: bool = False
    source_priority: list[str] = field(default_factory=list)
    description: str = ""


def get_input_descriptions(config_path: str | Path) -> dict[str, str]:
    """Read input ``description`` fields from ``input_defaults.by_id``.

    Used by callers that build runtime section purposes without a full
    ``PipelineEngine`` instance (e.g. portfolio_review).
    """
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    by_id = raw.get("input_defaults", {}).get("by_id", {}) or {}
    return {
        str(key): str(value.get("description", "") or "")
        for key, value in by_id.items()
        if isinstance(value, dict)
    }


# ── Pipeline Engine ──────────────────────────────────────────────────────


class PipelineEngine:
    """Configuration-driven proposal pipeline engine.

    Parameters
    ----------
    app_config : AppConfig
        Application configuration.
    config_path : str | Path
        Path to ``config_planbot.yaml``.
    proposal_id : str
        Proposal identifier (e.g. ``"reinvestment"``, ``"product_opportunity"``).
    """

    # Maps source values to their resolution strategy names (for logging).
    _VALID_SOURCES = frozenset({"file", "api", "runtime_or_static"})
    _VALID_SECTIONS = frozenset({"decision_context", "references"})

    def __init__(
        self,
        app_config: AppConfig,
        config_path: str | Path = _DEFAULT_CONFIG_PATH,
        proposal_id: str = "reinvestment",
    ):
        self._app_config = app_config
        self._root_dir = app_config.root_dir
        self._config_path = Path(config_path)
        self._proposal_id = proposal_id
        self._raw_config: dict[str, Any] = {}
        self._inputs: list[_InputDef] = []
        self._input_policy: dict[str, Any] = {}
        self._prompt_packaging: dict[str, Any] = {}
        self._execution: dict[str, Any] = {}
        self._quality_gates: dict[str, Any] = {}

    # ── Public API ──────────────────────────────────────────────────

    def run(
        self,
        *,
        client_id: str | None = None,
        source_product_id: str | None = None,
        product_id: str | None = None,
        client_selection: dict | None = None,
        product_ids: list[str] | None = None,
        market_outlook_text: str | None = None,
        suggested_products_and_rationale: str | None = None,
        runtime_context: dict[str, Any] | None = None,
        api_resolver_factory: Callable[..., Callable[[str], ReferenceDocument]] | None = None,
        output_file_override: str | Path | None = None,
    ) -> PipelineResult:
        """Run the proposal pipeline.

        Parameters
        ----------
        client_id, source_product_id, product_id, etc. :
            Seed identifiers passed through to the proposal resolver factory.
        runtime_context : dict | None
            Arbitrary runtime context passed to the resolver factory.
        api_resolver_factory : callable | None
            Factory that builds the ``api_resolver`` from resolved inputs.
            When None, a default resolver is built from the resolved
            ``decision_context`` inputs.  Must accept keyword arguments
            matching the runtime seed identifiers plus ``resolved``
            (a dict of input_id → resolved string content).
        output_file_override : str | Path | None
            Override output path.
        """
        diagnostics: dict[str, Any] = {}
        errors: list[dict] = []

        # ── Stage A: Load and validate ───────────────────────────
        try:
            self._load_and_validate()
        except Exception as exc:
            LOGGER.error("Pipeline config validation failed: %s", exc)
            return PipelineResult(
                status="error",
                output_path="",
                diagnostics={"stage": "A"},
                errors=[{"code": "CONFIG_VALIDATION_ERROR", "message": str(exc)}],
            )

        # ── Stage B: Build runtime request context ───────────────
        request_ctx: dict[str, Any] = {
            "client_id": client_id,
            "source_product_id": source_product_id,
            "product_id": product_id,
            "client_selection": client_selection,
            "product_ids": product_ids,
            "market_outlook_text": market_outlook_text,
            "suggested_products_and_rationale": suggested_products_and_rationale,
        }
        if runtime_context:
            request_ctx.update(runtime_context)

        # ── Stage C: Resolve inputs ──────────────────────────────
        resolved, resolution_log = self._resolve_inputs(request_ctx)
        diagnostics["resolution"] = resolution_log

        # ── Stage D: Quality gate check ──────────────────────────
        quality_errors = self._check_quality_gates(resolved)
        if quality_errors:
            return PipelineResult(
                status="error",
                output_path="",
                diagnostics=diagnostics,
                errors=quality_errors,
            )

        # ── Stage E: Build resolver + invoke CrewAI ──────────────
        try:
            if api_resolver_factory is not None:
                api_resolver = api_resolver_factory(
                    **(request_ctx | {"resolved": resolved}),
                )
            else:
                api_resolver = self._build_default_resolver(resolved)

            output_path = self._run_pipeline(
                resolved=resolved,
                api_resolver=api_resolver,
                output_file_override=output_file_override,
            )
        except Exception as exc:
            LOGGER.error("Pipeline generation failed: %s", exc)
            return PipelineResult(
                status="error",
                output_path="",
                diagnostics=diagnostics,
                errors=[{"code": "GENERATION_ERROR", "message": str(exc)}],
            )

        return PipelineResult(
            status="success",
            output_path=output_path,
            diagnostics=diagnostics,
            errors=errors,
        )

    def prepare(
        self,
        *,
        client_id: str | None = None,
        source_product_id: str | None = None,
        product_id: str | None = None,
        client_selection: dict | None = None,
        product_ids: list[str] | None = None,
        market_outlook_text: str | None = None,
        suggested_products_and_rationale: str | None = None,
        runtime_context: dict[str, Any] | None = None,
    ) -> PipelinePrep:
        """Resolve non-API inputs and return a PipelinePrep for wrapper use.

        The wrapper is responsible for fetching API data and building the
        ``api_resolver``.  This method handles everything else—file globs,
        ``runtime_or_static`` chains, fallback policies, and quality gates
        for non-API inputs.

        Returns
        -------
        PipelinePrep
            Resolved inputs, file content, packaging metadata.
        """
        self._load_and_validate()

        request_ctx: dict[str, Any] = {
            "client_id": client_id,
            "source_product_id": source_product_id,
            "product_id": product_id,
            "client_selection": client_selection,
            "product_ids": product_ids,
            "market_outlook_text": market_outlook_text,
            "suggested_products_and_rationale": suggested_products_and_rationale,
        }
        if runtime_context:
            request_ctx.update(runtime_context)

        resolved, resolution_log = self._resolve_inputs(request_ctx)

        # Build file ReferenceDocuments from resolved file/runtime_or_static content
        file_docs: list[ReferenceDocument] = []
        api_ids: list[str] = []
        for inp in self._inputs:
            if inp.source == "file" or inp.source == "runtime_or_static":
                content = resolved.get(inp.id, "")
                if content.strip():
                    file_docs.append(ReferenceDocument(
                        path=Path(f"api:/resolved/{inp.id}"),
                        content=content,
                        source_type="markdown",
                    ))
            elif inp.source == "api":
                api_ids.append(inp.id)

        packaging = self._prompt_packaging
        return PipelinePrep(
            resolved_inputs=resolved,
            api_input_ids=api_ids,
            file_reference_docs=file_docs,
            decision_context_order=packaging.get("decision_context_order", []),
            references_order=packaging.get("references_order", []),
            execution=self._execution,
        )

    # ── Stage A: Load and validate ─────────────────────────────────

    def _load_and_validate(self) -> None:
        """Load YAML config, merge input_defaults, and validate."""
        raw = yaml.safe_load(self._config_path.read_text(encoding="utf-8")) or {}

        # Load input_defaults (shared block in config_planbot.yaml)
        input_defaults: dict[str, Any] = raw.get("input_defaults", {})
        global_defaults: dict[str, Any] = input_defaults.get("global", {})
        by_id_defaults: dict[str, dict] = input_defaults.get("by_id", {})

        # Load pipeline proposal section
        pipeline = raw.get("pipeline", {})
        if not pipeline:
            raise ValueError("Missing top-level 'pipeline' key in config_planbot.yaml")

        proposal_cfg = pipeline.get(self._proposal_id)
        if not proposal_cfg:
            raise ValueError(
                f"Proposal '{self._proposal_id}' not found under 'pipeline' key"
            )

        self._raw_config = proposal_cfg
        self._execution = proposal_cfg.get("execution", {})
        self._input_policy = proposal_cfg.get("input_policy", {})
        self._prompt_packaging = proposal_cfg.get("prompt_packaging", {})
        self._quality_gates = proposal_cfg.get("quality_gates", {})

        # Build resolved input definitions by merging defaults
        raw_inputs: list[dict] = proposal_cfg.get("inputs", [])
        self._inputs = []
        for inp in raw_inputs:
            input_id = inp["id"]
            id_defaults = by_id_defaults.get(input_id, {})

            # Merge: explicit > by_id > global > engine hard default
            source = inp.get("source") or id_defaults.get("source") or global_defaults.get("source")
            if source is None and inp.get("paths"):
                source = "file"
            elif source is None:
                source = "api"  # engine hard default for unknown IDs

            prompt_section = (
                inp.get("prompt_section")
                or id_defaults.get("prompt_section")
                or global_defaults.get("prompt_section")
                or "references"
            )
            required = inp.get(
                "required",
                id_defaults.get("required", global_defaults.get("required", False)),
            )
            description = inp.get(
                "description",
                id_defaults.get("description", global_defaults.get("description", "")),
            )

            resolved_def = _InputDef(
                id=input_id,
                source=source,
                paths=inp.get("paths") or id_defaults.get("paths", []),
                prompt_section=prompt_section,
                required=required,
                source_priority=inp.get("source_priority", []),
                description=description or "",
            )
            self._inputs.append(resolved_def)

        LOGGER.info(
            "Pipeline config loaded: proposal=%s, inputs=%d",
            self._proposal_id,
            len(self._inputs),
        )

    # ── Stage C: Input resolution ─────────────────────────────────

    def _resolve_inputs(
        self,
        request_ctx: dict[str, Any],
    ) -> tuple[dict[str, str], list[dict]]:
        """Resolve every input to its final string content.

        Returns (resolved_dict, resolution_log).
        """
        resolved: dict[str, str] = {}
        log: list[dict] = []

        missing_data_default = self._input_policy.get(
            "missing_data", {}
        ).get("default", "error")
        per_input_policy = self._input_policy.get("missing_data", {}).get(
            "per_input", {}
        )

        for inp in self._inputs:
            outcome = "error"
            content: str = ""

            try:
                if inp.source == "file":
                    content, outcome = self._resolve_file(inp)
                elif inp.source == "api":
                    content, outcome = self._resolve_api(inp, request_ctx)
                elif inp.source == "runtime_or_static":
                    content, outcome = self._resolve_runtime_or_static(inp, request_ctx)
                else:
                    LOGGER.warning("Unknown source '%s' for input '%s'", inp.source, inp.id)
                    outcome = "error"
            except Exception as exc:
                LOGGER.warning("Resolution error for input '%s': %s", inp.id, exc)
                outcome = "error"

            # Apply missing_data policy when resolution fails or finds nothing
            if outcome in ("error", "skipped") and not content:
                policy = per_input_policy.get(inp.id, missing_data_default)
                if policy == "skip":
                    outcome = "skipped"
                elif policy == "fallback_to_static":
                    content, outcome = self._resolve_fallback_static(inp)
                elif policy == "error":
                    outcome = "error"
                # else: keep as-is

            # API inputs are resolved by the factory — mark as pending, not error
            if inp.source == "api" and not content:
                outcome = "pending"

            resolved[inp.id] = content
            log.append({"id": inp.id, "outcome": outcome, "required": inp.required})

            if outcome == "error" and inp.required:
                raise RuntimeError(
                    f"Required input '{inp.id}' failed resolution. "
                    f"Error code: REQUIRED_INPUT_MISSING"
                )

        return resolved, log

    def _resolve_file(self, inp: _InputDef) -> tuple[str, str]:
        """Resolve a file-glob input. Return (content, outcome)."""
        if not inp.paths:
            return "", "skipped"
        docs = load_references(self._root_dir, inp.paths)
        if not docs:
            return "", "skipped"
        content = "\n\n".join(doc.content.strip() for doc in docs if doc.content.strip())
        return content, "resolved" if content else "skipped"

    def _resolve_api(self, inp: _InputDef, request_ctx: dict) -> tuple[str, str]:
        """API inputs are resolved by the resolver factory at runtime.

        Here we just record that the input is pending — the actual
        resolution happens in the ``api_resolver_factory`` callback.
        """
        # API inputs are resolved externally — mark as pending.
        # The resolver factory receives the full request_ctx and knows
        # which API calls to make.
        return "", "resolved"  # resolved by factory, not here

    def _resolve_runtime_or_static(
        self, inp: _InputDef, request_ctx: dict[str, Any]
    ) -> tuple[str, str]:
        """Walk source_priority chain. First match wins."""
        for source_ref in inp.source_priority:
            # Check if it's a request key like "request.market_outlook_text"
            if source_ref.startswith("request."):
                key = source_ref[len("request."):]
                val = request_ctx.get(key)
                if val and isinstance(val, str) and val.strip():
                    return val, "resolved"
            else:
                # Treat as a file glob
                docs = load_references(self._root_dir, [source_ref])
                if docs:
                    content = "\n\n".join(doc.content.strip() for doc in docs if doc.content.strip())
                    if content:
                        return content, "resolved"
        return "", "error"

    def _resolve_fallback_static(self, inp: _InputDef) -> tuple[str, str]:
        """Fallback to static glob when runtime_or_static chain is exhausted."""
        # Use the source_priority file entries as fallback
        for source_ref in inp.source_priority:
            if source_ref.startswith("request."):
                continue  # skip runtime refs
            docs = load_references(self._root_dir, [source_ref])
            if docs:
                content = "\n\n".join(doc.content.strip() for doc in docs if doc.content.strip())
                if content:
                    return content, "fallback"
        # Try the paths field as last resort
        if inp.paths:
            docs = load_references(self._root_dir, inp.paths)
            if docs:
                content = "\n\n".join(doc.content.strip() for doc in docs if doc.content.strip())
                if content:
                    return content, "fallback"
        return "", "error"

    # ── Stage D: Quality gates ─────────────────────────────────────

    def _check_quality_gates(self, resolved: dict[str, str]) -> list[dict]:
        """Check that all required inputs are present.

        API inputs are skipped here — they are resolved later by the
        ``api_resolver_factory``.  Only file and runtime_or_static inputs
        are validated at this stage.
        """
        gates = self._quality_gates
        required_sections = gates.get("required_sections", [])
        fail_on_missing = gates.get("fail_on_missing_required_input", False)

        if not fail_on_missing:
            return []

        # Build set of API input IDs to skip quality gate checks
        api_input_ids = {inp.id for inp in self._inputs if inp.source == "api"}

        errors = []
        for section_id in required_sections:
            if section_id in api_input_ids:
                continue  # resolved later by factory
            content = resolved.get(section_id, "")
            if not content.strip():
                errors.append({
                    "code": "QUALITY_GATE_FAILED",
                    "message": f"Required input '{section_id}' is empty or missing",
                })

        return errors

    # ── Stage E: Resolver + CrewAI ─────────────────────────────────

    def _build_default_resolver(
        self, resolved: dict[str, str]
    ) -> Callable[[str], ReferenceDocument]:
        """Build a basic api_resolver from resolved decision_context inputs."""
        docs: dict[str, ReferenceDocument] = {}

        # Map known input IDs to api:// paths
        id_to_api = {
            "client_profile": API_CLIENT_PROFILE,
            "product_catalog": API_PRODUCT_CATALOG,
            "suggested_products_and_rationale": API_SUGGESTED_PRODUCTS_AND_RATIONALE,
            "market_outlook": API_MARKET_OUTLOOK,
        }

        for inp in self._inputs:
            if inp.prompt_section != "decision_context":
                continue
            api_path = id_to_api.get(inp.id, f"api://{inp.id}")
            content = resolved.get(inp.id, "")
            docs[api_path] = ReferenceDocument(
                path=Path(api_path),
                content=content or "",
                source_type="markdown",
            )

        return build_api_resolver(docs)

    def _run_pipeline(
        self,
        resolved: dict[str, str],
        api_resolver: Callable[[str], ReferenceDocument],
        output_file_override: str | Path | None = None,
    ) -> str:
        """Build reference sections config and invoke run_crew_planbot."""
        packaging = self._prompt_packaging
        decision_order = packaging.get("decision_context_order", [])
        references_order = packaging.get("references_order", [])

        # Build reference_sections for run_crew_planbot
        reference_sections: dict[str, dict] = {}

        # Decision context section — all API inputs
        api_globs: list[str] = []
        for input_id in decision_order:
            api_path = f"api://{input_id}"
            api_globs.append(api_path)

        if api_globs:
            reference_sections["decision_context"] = {
                "purpose": "Runtime context data for proposal generation",
                "globs": api_globs,
            }

        # References section — all file inputs
        ref_globs: list[str] = []
        for inp in self._inputs:
            if inp.prompt_section != "references":
                continue
            if inp.paths:
                ref_globs.extend(inp.paths)

        if ref_globs:
            reference_sections["references"] = {
                "purpose": "Reference documents for proposal generation",
                "globs": ref_globs,
            }

        # Build runtime_reference_overrides
        runtime_overrides: dict[str, list[str]] = {}
        if api_globs:
            runtime_overrides["decision_context"] = api_globs

        # Build a temporary PlanBotConfig-like structure for run_crew_planbot.
        # We patch the config loading by temporarily writing a minimal config.
        exec_cfg = self._execution

        temp_config = deepcopy(yaml.safe_load(self._config_path.read_text(encoding="utf-8")) or {})

        # Override the proposal section with pipeline-driven settings
        proposal_name = f"pipeline_{self._proposal_id}"
        output_folder = exec_cfg.get("output", {}).get("folder", f"runs/{self._proposal_id}")
        output_filename = exec_cfg.get("output", {}).get(
            "filename_template", f"{self._proposal_id}.md"
        )
        model_key = exec_cfg.get("model", "deepseek_tool")

        # Build a temporary proposal entry
        temp_config[proposal_name] = {
            "task": f"{self._proposal_id}_task",
            "output_root": output_folder,
            "output_filename": output_filename,
            "overwrite_output_folder": True,
            "crewai_config_folder": f"data/planbot/{self._proposal_id}/crewai",
            "references": {
                "decision_context": [
                    {"name": g, "purpose": "Runtime data"}
                    for g in api_globs
                ],
                "references": [
                    {"name": g, "purpose": "Reference document"}
                    for g in ref_globs
                ],
            },
            "llm_model": model_key,
            "references_root": f"data/planbot/{self._proposal_id}",
        }

        # Write the patched config to a temp file
        temp_config_path = self._root_dir / "temp" / f"pipeline_{self._proposal_id}.yaml"
        temp_config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_config_path.write_text(yaml.dump(temp_config), encoding="utf-8")

        try:
            result = run_crew_planbot(
                app_config=self._app_config,
                config_path=str(temp_config_path),
                proposal_name=proposal_name,
                runtime_reference_overrides=runtime_overrides,
                output_file_override=output_file_override,
                api_resolver=api_resolver,
            )
            return str(result.output_path)
        finally:
            # Clean up temp config
            if temp_config_path.exists():
                temp_config_path.unlink()

    # ── Integration helpers ────────────────────────────────────────

    @property
    def inputs(self) -> list[_InputDef]:
        """Resolved input definitions (read-only for factory callers)."""
        return list(self._inputs)

    @property
    def execution(self) -> dict[str, Any]:
        """Execution settings from YAML."""
        return dict(self._execution)

    @property
    def prompt_packaging(self) -> dict[str, Any]:
        """Prompt packaging config from YAML."""
        return dict(self._prompt_packaging)
