from __future__ import annotations

import csv
import logging
from pathlib import Path
from io import StringIO
from typing import Any

from src.planbot.orchestrator import ExecutionContext
from src.planbot.crew_workflow import run_crew_planbot
from src.shared.config_loader import AppConfig
from src.shared.io_utils import write_text

LOGGER = logging.getLogger(__name__)


class ProposalExecutor:
    """Executes proposals with per-client context injection."""

    def __init__(
        self,
        app_config: AppConfig,
        config_path: str | Path,
        run_id: str,
        keep_generated_client_inputs: bool = True,
        generated_inputs_root: str | Path = "runs/client_product_fit_analysis/generated_inputs",
    ):
        self.app_config = app_config
        self.config_path = Path(config_path)
        self.root_dir = app_config.root_dir
        self.run_id = run_id
        self.keep_generated_client_inputs = keep_generated_client_inputs
        self.generated_inputs_root = Path(generated_inputs_root)
        self.generated_files: list[Path] = []
        self.generated_dirs: set[Path] = set()

    def execute_with_context(
        self,
        proposal_name: str,
        context: ExecutionContext,
        output_file_template: str,
    ) -> str:
        """
        Execute a proposal with per-client context.
        
        Injects client profile and holdings into the proposal execution.
        
        Args:
            proposal_name: Name of proposal to run (e.g., 'client_product_fit_analysis')
            context: ExecutionContext with client data
            output_file_template: Output filename template (already resolved with placeholders)
            
        Returns:
            Path to generated output file
        """
        LOGGER.info(
            "Executing proposal %s for client %s with context",
            proposal_name,
            context.client_id,
        )

        try:
            profile_file, holdings_file, demographics_file = self._create_client_reference_files(
                client_id=context.client_id,
                profile=context.client_profile,
                holdings=context.client_holding,
                profile_data=context.client_profile_data,
            )

            overrides_list = [
                self._to_relative_path(profile_file),
                self._to_relative_path(holdings_file),
            ]
            if demographics_file:
                overrides_list.append(self._to_relative_path(demographics_file))
            runtime_overrides = {
                "client_profiles": overrides_list,
            }
            output_path = self._resolve_output_path(output_file_template)

            result = run_crew_planbot(
                self.app_config,
                str(self.config_path),
                proposal_name,
                runtime_reference_overrides=runtime_overrides,
                output_file_override=output_path,
            )

            LOGGER.info(
                "Proposal %s completed for client %s: %s",
                proposal_name,
                context.client_id,
                result.output_path,
            )

            return str(result.output_path)

        except Exception as exc:
            LOGGER.error(
                "Proposal %s failed for client %s: %s",
                proposal_name,
                context.client_id,
                str(exc),
            )
            raise

    def _create_client_reference_files(
        self,
        client_id: str,
        profile: str,
        holdings: dict[str, Any],
        profile_data: dict[str, str] | None = None,
    ) -> tuple[Path, Path, Path | None]:
        """
        Create generated reference files for one client.
        
        Returns:
            (profile_file_path, holdings_file_path, demographics_file_path_or_None)
        """
        generated_root = self._resolve_generated_inputs_root()
        generated_dir = generated_root / self.run_id / client_id
        generated_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dirs.add(generated_dir)

        # Write profile markdown
        profile_file = generated_dir / f"{client_id}_profile.md"
        write_text(profile_file, profile.strip() + "\n")
        self.generated_files.append(profile_file)

        # Write holdings as CSV so existing section source type remains compatible.
        holdings_file = generated_dir / f"{client_id}_holdings.csv"
        write_text(holdings_file, self._format_holdings_as_csv(client_id, holdings))
        self.generated_files.append(holdings_file)

        # Write demographics as Markdown table when available
        demographics_file: Path | None = None
        if profile_data:
            demographics_file = generated_dir / f"{client_id}_demographics.md"
            write_text(demographics_file, self._format_profile_data_as_markdown(profile_data))
            self.generated_files.append(demographics_file)
            LOGGER.info("Wrote demographics file for client %s", client_id)

        return profile_file, holdings_file, demographics_file

    @staticmethod
    def _format_holdings_as_csv(client_id: str, holdings: dict[str, Any]) -> str:
        """Format holdings data as one-row CSV keyed by client_id."""
        filtered_keys = [k for k in holdings.keys() if k != "client_id"]
        headers = ["client_id", *filtered_keys]

        row = {"client_id": client_id}
        for key in filtered_keys:
            row[key] = "" if holdings.get(key) is None else str(holdings.get(key))

        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=headers)
        writer.writeheader()
        writer.writerow(row)
        return buffer.getvalue()

    @staticmethod
    def _format_profile_data_as_markdown(profile_data: dict[str, str]) -> str:
        """Format client demographics as a Markdown table for LLM consumption."""
        lines = ["## Client Demographics", ""]
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        # Omit Client Name since it's already in the main profile text
        for key, value in profile_data.items():
            if key.lower() in ("client name", "client_name"):
                continue
            lines.append(f"| {key} | {value} |")
        return "\n".join(lines) + "\n"

    def _resolve_generated_inputs_root(self) -> Path:
        if self.generated_inputs_root.is_absolute():
            return self.generated_inputs_root.resolve()
        return (self.root_dir / self.generated_inputs_root).resolve()

    def _resolve_output_path(self, output_file_template: str) -> Path:
        output_path = Path(output_file_template)
        if output_path.is_absolute():
            return output_path
        return (self.root_dir / output_path).resolve()

    def _to_relative_path(self, path: Path) -> str:
        try:
            rel = path.resolve().relative_to(self.root_dir.resolve())
            return str(rel).replace("\\", "/")
        except ValueError:
            return str(path.resolve())

    def cleanup_temp_files(self) -> None:
        """Remove generated client reference files unless retention is enabled."""
        if self.keep_generated_client_inputs:
            LOGGER.info("Keeping generated client inputs for run_id=%s", self.run_id)
            return

        for temp_file in self.generated_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    LOGGER.debug("Cleaned up temp file: %s", temp_file)
            except Exception as exc:
                LOGGER.warning("Failed to cleanup temp file %s: %s", temp_file, exc)

        for generated_dir in sorted(self.generated_dirs, key=lambda p: len(p.parts), reverse=True):
            try:
                # Remove empty generated directory chain without touching base references folders.
                current = generated_dir
                for _ in range(5):
                    if not current.exists() or current == self.root_dir:
                        break
                    current.rmdir()
                    current = current.parent
            except OSError:
                continue

        self.generated_files.clear()
        self.generated_dirs.clear()
