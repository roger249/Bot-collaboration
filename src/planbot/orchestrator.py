from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.shared.io_utils import read_text

LOGGER = logging.getLogger(__name__)


@dataclass
class FilterOutput:
    """Container for filter execution results."""
    client_profiles: dict[str, str] | list[str]  # keyed by client_id or ordered list
    client_ids: list[str]
    by_client_id: dict[str, dict[str, Any]]  # keyed holdings map


@dataclass
class ExecutionContext:
    """Per-client iteration context."""
    run_id: str
    index: int
    client_id: str
    client_profile: str
    client_holding: dict[str, Any]
    bindings: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result of one client execution."""
    client_id: str
    proposal_name: str
    status: str  # 'success', 'failed', 'skipped'
    output_path: str | None
    elapsed_ms: int
    error: str | None = None


class FilterBuilder:
    """Builds filter outputs from proposal results."""

    @staticmethod
    def _is_client_header_line(line: str, header_pattern: str) -> bool:
        """Return True when line is a markdown heading for a client section."""
        stripped = line.strip()
        if stripped.startswith(header_pattern):
            return True

        # Support headings like "### Client ID:" when config uses "## Client ID:".
        normalized_header = header_pattern.lstrip("#").strip()
        return bool(re.match(rf"^#+\s*{re.escape(normalized_header)}", stripped))

    @staticmethod
    def _extract_client_id(line: str, client_id_regex: str) -> str | None:
        """Extract client id from header line using configured regex then fallback."""
        try:
            match = re.search(client_id_regex, line)
        except re.error:
            match = None

        if match:
            candidate = match.group(1).strip() if match.groups() else match.group(0).strip()
            if candidate:
                return FilterBuilder._normalize_client_id(candidate)

        # Fallback handles heading-level changes and IDs like wl-2 / zw-5.
        fallback = re.search(r"Client ID:\s*([^\s(]+)", line)
        if fallback:
            return FilterBuilder._normalize_client_id(fallback.group(1).strip())
        return None

    @staticmethod
    def _normalize_client_id(client_id: str) -> str:
        """Normalize model-emitted IDs for stable downstream lookups."""
        dash_variants = {
            "\u2010": "-",  # hyphen
            "\u2011": "-",  # non-breaking hyphen
            "\u2012": "-",  # figure dash
            "\u2013": "-",  # en dash
            "\u2014": "-",  # em dash
            "\u2212": "-",  # minus sign
        }
        normalized = client_id
        for variant, replacement in dash_variants.items():
            normalized = normalized.replace(variant, replacement)
        return normalized.strip()

    @staticmethod
    def product_investor_matching_filter(
        proposal_output: str,
        header_pattern: str = "## Client ID:",
        client_id_regex: str = r"(?<=## Client ID:)(.*?)(?=\s|\()",
    ) -> tuple[dict[str, str], list[str]]:
        """
        Extract client_profiles sections and client_ids from proposal output.
        
        Returns:
            (client_profiles_dict, client_ids_list) where dict is keyed by client_id
        """
        lines = proposal_output.split("\n")
        sections: dict[str, str] = {}  # keyed by client_id
        client_ids_list: list[str] = []
        current_section_id: str | None = None
        current_section_lines: list[str] = []

        for line in lines:
            if FilterBuilder._is_client_header_line(line, header_pattern):
                # Save previous section if exists
                if current_section_id and current_section_lines:
                    sections[current_section_id] = "\n".join(current_section_lines)

                # Extract client_id from header line
                extracted_client_id = FilterBuilder._extract_client_id(line, client_id_regex)
                if extracted_client_id:
                    current_section_id = extracted_client_id
                    client_ids_list.append(current_section_id)
                    current_section_lines = [line]
                else:
                    current_section_id = None
                    current_section_lines = []
            elif current_section_id is not None and line.strip().startswith("## "):
                # New section started, save current one
                if current_section_lines:
                    sections[current_section_id] = "\n".join(current_section_lines)
                current_section_id = None
                current_section_lines = []
            elif current_section_id is not None:
                current_section_lines.append(line)

        # Save last section
        if current_section_id and current_section_lines:
            sections[current_section_id] = "\n".join(current_section_lines)

        LOGGER.info("product_investor_matching_filter extracted %d client sections", len(sections))
        return sections, client_ids_list

    @staticmethod
    def client_holdings_filter(
        csv_file_path: Path,
        client_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """
        Load client holdings from CSV and return map keyed by client_id.
        
        Assumes CSV has a 'client_id' column and other columns as holding attributes.
        """
        holdings_map: dict[str, dict[str, Any]] = {}
        
        if not csv_file_path.exists():
            LOGGER.warning("CSV file not found: %s", csv_file_path)
            return holdings_map

        csv_content = read_text(csv_file_path)
        lines = csv_content.strip().split("\n")
        
        if not lines:
            LOGGER.warning("CSV file is empty: %s", csv_file_path)
            return holdings_map

        # Parse header
        header_line = lines[0]
        headers = [h.strip() for h in header_line.split(",")]
        
        client_id_candidates = ["client_id", "client/id", "clientId", "clientid"]
        client_id_col = next((col for col in client_id_candidates if col in headers), None)
        if client_id_col is None:
            LOGGER.warning(
                "CSV does not have a supported client id column in %s. Supported columns: %s",
                csv_file_path,
                ", ".join(client_id_candidates),
            )
            return holdings_map

        client_id_idx = headers.index(client_id_col)

        # Parse rows
        for line in lines[1:]:
            if not line.strip():
                continue
            cols = [c.strip() for c in line.split(",")]
            if len(cols) > client_id_idx:
                cid = cols[client_id_idx]
                # Build row dict
                row_dict = {headers[i]: cols[i] if i < len(cols) else "" for i in range(len(headers))}
                holdings_map[cid] = row_dict

        LOGGER.info("client_holdings_filter loaded %d client holdings", len(holdings_map))
        return holdings_map


class PlaceholderResolver:
    """Resolves placeholders in config strings using binding values."""

    @staticmethod
    def resolve(template: str, bindings: dict[str, Any]) -> str:
        """
        Replace {key} placeholders in template with values from bindings dict.
        
        Example:
            resolve("output_{client_id}.md", {"client_id": "C0001"})
            -> "output_C0001.md"
        """
        result = template
        for key, value in bindings.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result


class PipelineOrchestrator:
    """Orchestrates execution of proposal pipelines with filters and fan-out."""

    def __init__(self, root_dir: Path, config_path: Path, run_id: str | None = None):
        self.root_dir = root_dir
        self.config_path = config_path
        self.run_id = run_id or self._generate_run_id()
        self.logger = LOGGER

    @staticmethod
    def _generate_run_id() -> str:
        """Generate unique run_id based on timestamp."""
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def load_config(self) -> dict[str, Any]:
        """Load run_configurations from YAML."""
        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f)
        return data.get("run_configurations", {})


    def execute_filters(self, config: dict[str, Any]) -> FilterOutput:
        """
        Execute filter chain and return combined output.
        
        Expects config with 'filters' section defining:
        - product_investor_matching_filter
        - client_holdings_filter
        """
        filters_config = config.get("filters", {})

        # Run product_investor_matching_filter
        pim_filter_cfg = filters_config.get("product_investor_matching_filter", {})
        pim_input = pim_filter_cfg.get("input", {})
        pim_proposal_name = pim_input.get("proposal", "product_investor_matching")
        execute_proposal_first = pim_input.get("execute_proposal_first", False)

        pim_output_path = self.root_dir / f"runs/{pim_proposal_name}" / "output.md"

        if execute_proposal_first:
            # Here you would call the proposal execution logic (e.g., run_crew_planbot)
            # For now, just log the intent
            self.logger.info("execute_proposal_first is True: would execute proposal '%s' here.", pim_proposal_name)
            # After execution, reload the output
            if not pim_output_path.exists():
                raise FileNotFoundError(
                    f"Proposal output not found after execution: {pim_output_path}. "
                    f"Check proposal execution logic."
                )
            pim_content = read_text(pim_output_path)
        else:
            # Only use existing output, do not re-run proposal
            if not pim_output_path.exists():
                # Fallback to latest markdown artifact under runs/<proposal>/ when filename differs.
                proposal_run_root = self.root_dir / f"runs/{pim_proposal_name}"
                all_md = list(proposal_run_root.rglob("*.md")) if proposal_run_root.exists() else []

                # Prefer model output files and skip prompt snapshots.
                preferred_md = [
                    p
                    for p in all_md
                    if p.name != "prompt_snapshot.md" and p.stem.startswith(pim_proposal_name)
                ]
                md_candidates = preferred_md if preferred_md else [p for p in all_md if p.name != "prompt_snapshot.md"]
                md_candidates = sorted(md_candidates, key=lambda p: p.stat().st_mtime, reverse=True)
                if md_candidates:
                    pim_output_path = md_candidates[0]
                    self.logger.info("Using latest proposal output fallback: %s", pim_output_path)
                    pim_content = read_text(pim_output_path)
                else:
                    raise FileNotFoundError(
                        "No product investor matching output found for pipeline filters. "
                        f"Expected {pim_output_path} or any markdown artifact under {proposal_run_root}. "
                        "Set execute_proposal_first: true to generate output or run 'run-planbot --proposal product_investor_matching' first."
                    )
            else:
                pim_content = read_text(pim_output_path)

        pim_output_cfg = pim_filter_cfg.get("output", {})
        client_profiles_cfg = pim_output_cfg.get("client_profiles", {})
        header_pattern = client_profiles_cfg.get("header_pattern", "## Client ID:")
        
        client_ids_cfg = pim_output_cfg.get("client_ids", {})
        client_id_regex = client_ids_cfg.get("pattern", r"(?<=## Client ID:)(.*?)(?=\s|\()")

        client_profiles_dict, client_ids_list = FilterBuilder.product_investor_matching_filter(
            pim_content,
            header_pattern=header_pattern,
            client_id_regex=client_id_regex,
        )

        if not client_ids_list:
            raise ValueError(
                "No client IDs extracted from product investor matching output. "
                f"Source file: {pim_output_path}. "
                f"Expected section headers matching '{header_pattern}' and ids matching '{client_id_regex}'."
            )

        # Run client_holdings_filter
        chf_filter_cfg = filters_config.get("client_holdings_filter", {})
        chf_input = chf_filter_cfg.get("input", {})
        csv_file_rel = chf_input.get("file", "data/planbot/shared/client_profile/client_list.csv")
        csv_file_path = self.root_dir / csv_file_rel

        holdings_map = FilterBuilder.client_holdings_filter(csv_file_path, client_ids_list)

        return FilterOutput(
            client_profiles=client_profiles_dict,
            client_ids=client_ids_list,
            by_client_id=holdings_map,
        )

    def execute_fan_out(
        self,
        config: dict[str, Any],
        filter_output: FilterOutput,
        execute_proposal_fn,  # callable to run a proposal
    ) -> list[ExecutionResult]:
        """
        Execute fan-out orchestration: iterate clients and run proposals.
        
        Args:
            config: run_configurations['client_product_fit_analysis_proposals']
            filter_output: Combined filter output with profiles and holdings
            execute_proposal_fn: Callable(proposal_name, context) -> str (output path)
        """
        results: list[ExecutionResult] = []
        
        fan_out_cfg = config.get("fan_out", {})
        alias_cfg = fan_out_cfg.get("alias", {})
        references_binding_cfg = fan_out_cfg.get("references_section_binding", [])
        execute_cfg = fan_out_cfg.get("execute", [])

        # Iteration: over client_profiles
        client_ids = filter_output.client_ids
        
        self.logger.info(
            "Starting fan-out orchestration: run_id=%s, clients=%d",
            self.run_id,
            len(client_ids),
        )

        defaults = config.get("defaults", {}) if isinstance(config, dict) else {}
        continue_on_error = defaults.get("continue_on_client_error", True)

        for idx, client_id in enumerate(client_ids):
            # Build bindings for this iteration
            bindings = {
                "index": idx,
                "client_id": client_id,
            }
            
            # Resolve alias values
            for alias_key, alias_ref in alias_cfg.items():
                if alias_key == "client_id":
                    # Already in bindings
                    continue
                # For other aliases, resolve from filter outputs (extended later)
                bindings[alias_key] = None

            # Build execution context
            client_profile = filter_output.client_profiles.get(client_id, "") if isinstance(filter_output.client_profiles, dict) else ""
            client_holding = filter_output.by_client_id.get(client_id, {})

            ctx = ExecutionContext(
                run_id=self.run_id,
                index=idx,
                client_id=client_id,
                client_profile=client_profile,
                client_holding=client_holding,
                bindings=bindings,
            )

            # Execute proposals for this client
            for proposal_spec in execute_cfg:
                if isinstance(proposal_spec, dict):
                    enabled = proposal_spec.get("enabled", True)
                    if not enabled:
                        continue

                    proposal_name = proposal_spec.get("proposal")
                    output_file_template = proposal_spec.get("output_file", "")

                    if not proposal_name:
                        self.logger.warning("proposal spec missing 'proposal' name")
                        continue

                    start_time = time.time()
                    try:
                        # Resolve output filename
                        output_file = PlaceholderResolver.resolve(output_file_template, bindings)

                        # Call proposal executor
                        result_path = execute_proposal_fn(proposal_name, ctx, output_file)

                        elapsed_ms = int((time.time() - start_time) * 1000)
                        results.append(
                            ExecutionResult(
                                client_id=client_id,
                                proposal_name=proposal_name,
                                status="success",
                                output_path=result_path,
                                elapsed_ms=elapsed_ms,
                            )
                        )
                        self.logger.info(
                            "Executed %s for client %s: status=success, output=%s, elapsed=%dms",
                            proposal_name,
                            client_id,
                            result_path,
                            elapsed_ms,
                        )
                    except Exception as exc:
                        elapsed_ms = int((time.time() - start_time) * 1000)
                        error_msg = str(exc)
                        results.append(
                            ExecutionResult(
                                client_id=client_id,
                                proposal_name=proposal_name,
                                status="failed",
                                output_path=None,
                                elapsed_ms=elapsed_ms,
                                error=error_msg,
                            )
                        )
                        self.logger.error(
                            "Failed %s for client %s: error=%s, elapsed=%dms",
                            proposal_name,
                            client_id,
                            error_msg,
                            elapsed_ms,
                        )
                        if not continue_on_error:
                            raise

        return results

    def log_execution_results(self, results: list[ExecutionResult]) -> None:
        """Log execution results in structured format."""
        self.logger.info("Execution results summary:")
        self.logger.info(
            "run_id=%s, total_executions=%d, succeeded=%d, failed=%d",
            self.run_id,
            len(results),
            sum(1 for r in results if r.status == "success"),
            sum(1 for r in results if r.status == "failed"),
        )
        for result in results:
            self.logger.info(
                "run_id=%s, client_id=%s, proposal=%s, status=%s, output=%s, elapsed_ms=%d, error=%s",
                self.run_id,
                result.client_id,
                result.proposal_name,
                result.status,
                result.output_path,
                result.elapsed_ms,
                result.error or "",
            )
