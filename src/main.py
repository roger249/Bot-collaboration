from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Support direct execution: `python src/main.py`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config_loader import load_config
from src.workflow import run_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Author-reviewer workflow prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the workflow")
    run_parser.add_argument("--config", required=True, help="Path to workflow config YAML")
    return parser


def main() -> None:
    parser = build_parser()
    argv = sys.argv[1:]
    if not argv:
        default_config = Path(__file__).resolve().parents[1] / "config" / "workflow.yaml"
        if default_config.exists():
            argv = ["run", "--config", str(default_config)]
    args = parser.parse_args(argv)

    if args.command == "run":
        config = load_config(args.config)
        try:
            result = run_workflow(config)
            print(
                json.dumps(
                    {
                        "run_root": str(result.run_root),
                        "log_path": str(result.log_path),
                        "final_spec_path": str(result.final_spec_path),
                        "total_rounds": result.total_rounds,
                        "stopped_reason": result.stopped_reason,
                    },
                    indent=2,
                )
            )
        except Exception as exc:
            print(f"Workflow failed: {exc}")
            raise SystemExit(1) from exc


if __name__ == "__main__":
    main()