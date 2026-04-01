from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil


def create_run_root(output_root: Path, run_name: str, overwrite_output_folder: bool = False) -> Path:
    if overwrite_output_folder:
        run_root = output_root / run_name
        if run_root.exists():
            shutil.rmtree(run_root)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_root = output_root / f"{run_name}_{timestamp}"

    run_root.mkdir(parents=True, exist_ok=True)
    return run_root


def create_timestamped_run_root(output_root: Path, run_name: str) -> Path:
    return create_run_root(output_root, run_name, overwrite_output_folder=False)
