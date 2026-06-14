from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from src.planbot.orchestrator import PipelineOrchestrator
from src.planbot.proposal_executor import ProposalExecutor
from src.shared.config_loader import AppConfig
from src.shared.logging_utils import configure_logging

LOGGER = logging.getLogger(__name__)


class ClientProductFitPipelineConfig(BaseModel):
    generated_inputs_root: str = "runs/client_product_fit_analysis/generated_inputs"
    fan_out: dict[str, Any] = Field(default_factory=dict)


class RunConfigurationsModel(BaseModel):
    defaults: dict[str, Any] = Field(default_factory=dict)
    client_product_fit_analysis_proposals: ClientProductFitPipelineConfig = ClientProductFitPipelineConfig()
    filters: dict[str, Any]


class PipelineRunner:
    """Runs orchestrated proposal pipelines using run_configurations."""

    def __init__(self, app_config: AppConfig, config_path: str | Path):
        self.app_config = app_config
        self.config_path = Path(config_path)
        self.root_dir = app_config.root_dir

    def _parse_run_config(self, config: dict[str, Any]) -> RunConfigurationsModel:
        try:
            return RunConfigurationsModel(**config)
        except ValidationError as exc:
            raise ValueError(f"Invalid run_configurations: {exc}") from exc

    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate run_configurations structure before execution."""
        if not config:
            LOGGER.error("run_configurations is empty")
            return False

        # Check for required sections
        if "client_product_fit_analysis_proposals" not in config:
            LOGGER.warning("No client_product_fit_analysis_proposals found in run_configurations")

        if "filters" not in config:
            LOGGER.error("run_configurations missing 'filters' section")
            return False

        filters = config.get("filters", {})
        if "product_investor_matching_filter" not in filters:
            LOGGER.error("filters missing 'product_investor_matching_filter'")
            return False

        if "client_holdings_filter" not in filters:
            LOGGER.error("filters missing 'client_holdings_filter'")
            return False

        if "client_profile_filter" not in filters:
            LOGGER.info("client_profile_filter not configured; client demographics will be omitted")

        # Validate fan_out contract
        proposals_cfg = config.get("client_product_fit_analysis_proposals", {})
        fan_out_cfg = proposals_cfg.get("fan_out", {})
        alias_cfg = fan_out_cfg.get("alias", {})

        if not alias_cfg:
            LOGGER.error("fan_out missing 'alias' section")
            return False

        if "client_id" not in alias_cfg:
            LOGGER.warning("fan_out.alias missing 'client_id' binding")

        execute_cfg = fan_out_cfg.get("execute", [])
        if not execute_cfg:
            LOGGER.error("execute section empty or missing")
            return False

        # Validate that all placeholders used in execute are defined in alias
        for exec_spec in execute_cfg:
            if not isinstance(exec_spec, dict):
                continue
            output_file = exec_spec.get("output_file", "")
            # Extract placeholders like {client_id}
            import re
            placeholders = re.findall(r"\{(\w+)\}", output_file)
            for placeholder in placeholders:
                if placeholder not in alias_cfg and placeholder != "index":
                    LOGGER.error(
                        "Placeholder {%s} used in output_file but not defined in alias",
                        placeholder,
                    )
                    return False

        LOGGER.info("Pipeline configuration validation passed")
        return True

    def run_pipeline(self, pipeline_name: str = "client_product_fit_analysis_proposals") -> dict[str, Any]:
        """
        Run an orchestrated proposal pipeline.
        
        Args:
            pipeline_name: Name of the pipeline to run (key in run_configurations)
            
        Returns:
            Summary dict with results
        """
        orchestrator = PipelineOrchestrator(self.root_dir, self.config_path, app_config=self.app_config)

        # Configure a pipeline-scoped log file so early filter failures are persisted.
        pipeline_logs_dir = self.root_dir / "runs" / "pipelines" / pipeline_name / orchestrator.run_id / "logs"
        pipeline_logs_dir.mkdir(parents=True, exist_ok=True)
        configure_logging(
            self.app_config.logging_level,
            pipeline_logs_dir / "pipeline.log",
            pipeline_logs_dir / "chat_history.log",
            self.app_config.logging_config_file,
            chat_history_enabled=self.app_config.logging_chat_history_enabled,
            chat_history_max_bytes=self.app_config.logging_chat_history_max_bytes,
            chat_history_backup_count=self.app_config.logging_chat_history_backup_count,
        )

        raw_config = orchestrator.load_config()
        parsed_config = self._parse_run_config(raw_config)
        config = parsed_config.model_dump()

        if not self.validate_config(config):
            raise ValueError("Pipeline configuration validation failed")

        LOGGER.info("Loading filters for pipeline: %s", pipeline_name)
        filter_output = orchestrator.execute_filters(config)

        LOGGER.info(
            "Filters complete: clients=%d, profiles=%d, holdings=%d",
            len(filter_output.client_ids),
            len(filter_output.client_profiles),
            len(filter_output.by_client_id),
        )

        # Get pipeline-specific config
        pipeline_cfg = config.get(pipeline_name, {})
        if not pipeline_cfg:
            raise ValueError(f"Pipeline '{pipeline_name}' not found in run_configurations")

        defaults_cfg = config.get("defaults", {})
        keep_generated_client_inputs = bool(defaults_cfg.get("keep_generated_client_inputs", True))
        generated_inputs_root = pipeline_cfg.get("generated_inputs_root")

        LOGGER.info("Starting fan-out orchestration for pipeline: %s", pipeline_name)
        
        # Create proposal executor
        executor = ProposalExecutor(
            self.app_config,
            self.config_path,
            run_id=orchestrator.run_id,
            keep_generated_client_inputs=keep_generated_client_inputs,
            generated_inputs_root=generated_inputs_root,
        )
        
        # Define proposal executor callback
        def execute_proposal_callback(proposal_name: str, ctx, output_file: str) -> str:
            """Execute one proposal for one client."""
            return executor.execute_with_context(proposal_name, ctx, output_file)

        try:
            results = orchestrator.execute_fan_out(
                pipeline_cfg,
                filter_output,
                execute_proposal_callback,
            )
        finally:
            executor.cleanup_temp_files()

        LOGGER.info("Fan-out orchestration complete")
        orchestrator.log_execution_results(results)

        # Count results
        success_count = sum(1 for r in results if r.status == "success")
        failed_count = sum(1 for r in results if r.status == "failed")

        return {
            "run_id": orchestrator.run_id,
            "pipeline": pipeline_name,
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
            "results": results,
        }
