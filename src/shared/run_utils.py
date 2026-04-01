from __future__ import annotations

from datetime import datetime
from pathlib import Path


def create_timestamped_run_root(output_root: Path, run_name: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = output_root / f"{run_name}_{timestamp}"
    run_root.mkdir(parents=True, exist_ok=True)
    return run_root
