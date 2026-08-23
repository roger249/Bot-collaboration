"""
Proposal Pipeline Engine — configuration-driven proposal prompt assembly.

Reads proposal YAML configuration and input_defaults and resolves all inputs
(file globs, API calls, runtime_or_static fallback chains) into per-input
content.  The live API wrappers use ``load()`` + ``.inputs``; the resolution
helpers are exercised by the unit tests.

Architecture:
    PipelineEngine
        ├── _load_and_validate()         → loads proposal YAML + merges defaults
        ├── _resolve_inputs()            → resolves each input per its source
        └── load()                       → public entry point (used by wrappers)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.planbot.input_loader import load_references
from src.shared.config_loader import AppConfig

LOGGER = logging.getLogger(__name__)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _ROOT_DIR / "config" / "config_planbot.yaml"

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
    sources: dict[str, str] = field(default_factory=dict)
    default_source: str = ""
    description: str = ""
    include: dict[str, bool] = field(default_factory=dict)


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


def get_input_default_sources(config_path: str | Path) -> dict[str, str]:
    """Read the ``default_source`` for each input id across all pipelines.

    Used by API wrappers to resolve ``market_outlook_source`` when the request
    omits it (precedence: request field → yaml ``default_source`` → "request").
    """
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    pipeline = raw.get("pipeline", {}) or {}
    result: dict[str, str] = {}
    for proposal_cfg in pipeline.values():
        if not isinstance(proposal_cfg, dict):
            continue
        for inp in proposal_cfg.get("inputs") or []:
            if not isinstance(inp, dict):
                continue
            default_source = inp.get("default_source")
            if default_source:
                result[str(inp.get("id"))] = str(default_source)
    return result


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

    def load(self) -> "PipelineEngine":
        """Load config and merge defaults (populates ``.inputs``) without resolving inputs."""
        self._load_and_validate()
        return self

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
            include = inp.get("include") or {}
            if not isinstance(include, dict):
                include = {}

            sources = inp.get("sources") or {}
            if not isinstance(sources, dict):
                sources = {}

            resolved_def = _InputDef(
                id=input_id,
                source=source,
                paths=inp.get("paths") or id_defaults.get("paths", []),
                prompt_section=prompt_section,
                required=required,
                source_priority=inp.get("source_priority", []),
                sources={str(k): str(v) for k, v in sources.items()},
                default_source=str(inp.get("default_source") or ""),
                description=description or "",
                include=include,
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
        """Resolve a ``runtime_or_static`` input.

        Inputs declaring the ``sources`` map are resolved by
        ``_resolve_sources`` (request/static selection).  Otherwise the legacy
        ``source_priority`` chain is walked, first match wins.
        """
        if inp.sources:
            return self._resolve_sources(inp, request_ctx)

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

    def _resolve_sources(
        self, inp: _InputDef, request_ctx: dict[str, Any]
    ) -> tuple[str, str]:
        """Resolve an input via the ``sources`` map + ``default_source``.

        Chosen source = request ``market_outlook_source`` (if set) →
        ``default_source`` → ``"request"``.  ``static`` always loads the static
        glob; ``request`` uses the request value if present, else falls back to
        the static glob.
        """
        requested = request_ctx.get("market_outlook_source")
        chosen = str(requested or inp.default_source or "request").strip()

        static_glob = inp.sources.get("static")
        request_ref = inp.sources.get("request", "")

        if chosen == "static":
            content = self._load_glob_content(static_glob)
            return (content, "resolved") if content else ("", "error")

        # request (default): prefer the request value, fall back to static.
        if request_ref.startswith("request."):
            key = request_ref[len("request."):]
            val = request_ctx.get(key)
            if val and isinstance(val, str) and val.strip():
                return val, "resolved"

        content = self._load_glob_content(static_glob)
        return (content, "fallback") if content else ("", "error")

    def _load_glob_content(self, glob_or_paths: str | list[str] | None) -> str:
        """Load and join the content of one or more file globs, or ``""``."""
        if not glob_or_paths:
            return ""
        patterns = (
            [glob_or_paths] if isinstance(glob_or_paths, str) else glob_or_paths
        )
        docs = load_references(self._root_dir, patterns)
        return "\n\n".join(
            doc.content.strip() for doc in docs if doc.content.strip()
        )

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
