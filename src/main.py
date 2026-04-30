from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from dotenv import load_dotenv

# Support direct execution: `python src/main.py`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.shared.config_loader import load_config
from src.author_reviewer.crew_workflow import run_crew_workflow
from src.planbot.crew_workflow import run_crew_planbot


LOGGER = logging.getLogger(__name__)


def _load_local_dotenv() -> None:
    project_root = Path(__file__).resolve().parents[1]
    dotenv_path = project_root / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Author-reviewer workflow prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the workflow")
    run_parser.add_argument("--config", required=True, help="Path to workflow config YAML")

    planbot_parser = subparsers.add_parser("run-planbot", help="Run a PlanBot proposal")
    planbot_parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to main config YAML (for logging and LLM setup)",
    )
    planbot_parser.add_argument(
        "--planbot-config",
        default="config/config_planbot.yaml",
        help="Path to PlanBot config YAML",
    )
    planbot_parser.add_argument(
        "--proposal",
        default="portfolio_review",
        help="Name of the proposal to run (e.g., portfolio_review, client_suitability)",
    )
    return parser


def main() -> None:
    _load_local_dotenv()
    parser = build_parser()
    argv = sys.argv[1:]
    if not argv:
        default_config = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
        if default_config.exists():
            argv = ["run", "--config", str(default_config)]
    args = parser.parse_args(argv)

    if args.command == "run":
        config = load_config(args.config)
        try:
            result = run_crew_workflow(config)
            LOGGER.debug(
                "%s",
                json.dumps(
                    {
                        "run_root": str(result.run_root),
                        "log_path": str(result.log_path),
                        "final_spec_path": str(result.final_spec_path),
                        "total_rounds": result.total_rounds,
                        "stopped_reason": result.stopped_reason,
                    },
                    indent=2,
                ),
            )
        except Exception as exc:
            LOGGER.exception("Workflow execution failed")
            LOGGER.error("Workflow failed: %s", exc)
            raise SystemExit(1) from exc
    elif args.command == "run-planbot":
        config = load_config(args.config)
        try:
            result = run_crew_planbot(config, args.planbot_config, args.proposal)
            LOGGER.debug(
                "%s",
                json.dumps(
                    {
                        "run_root": str(result.run_root),
                        "log_path": str(result.log_path),
                        "output_path": str(result.output_path),
                        "prompt_path": str(result.prompt_path),
                        "references_used": result.references_used,
                        "urls_used": result.urls_used,
                    },
                    indent=2,
                ),
            )
        except Exception as exc:
            LOGGER.exception("PlanBot execution failed")
            LOGGER.error("PlanBot failed: %s", exc)
            raise SystemExit(1) from exc


def run_planbot_programmatically(
    config_path: str | None = None,
    planbot_config: str | None = None,
    proposal: str | None = None,
) -> object:
    """Run PlanBot programmatically and return the PlanBotResult.

    This mirrors the behaviour of the `run-planbot` CLI command but can be
    invoked from Python code or tests.
    """
    _load_local_dotenv()
    if config_path is None:
        config_path = str(Path(__file__).resolve().parents[1] / "config" / "config.yaml")
    if planbot_config is None:
        planbot_config = "config/config_planbot.yaml"
    if proposal is None:
        proposal = "portfolio_review"

    app_config = load_config(config_path)
    return run_crew_planbot(app_config, planbot_config, proposal)


if __name__ == "__main__":
    main()