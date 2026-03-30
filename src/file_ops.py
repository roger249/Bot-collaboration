from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class RunPaths:
    root: Path
    specs_dir: Path
    comments_dir: Path
    author_dir: Path
    progress_dir: Path
    logs_dir: Path


def create_run_paths(output_root: Path, workflow_name: str) -> RunPaths:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = output_root / f"{workflow_name}_{timestamp}"
    specs_dir = root / "specs"
    comments_dir = root / "comments"
    author_dir = root / "author"
    progress_dir = root / "progress"
    logs_dir = root / "logs"
    for path in (specs_dir, comments_dir, author_dir, progress_dir, logs_dir):
        path.mkdir(parents=True, exist_ok=True)
    return RunPaths(
        root=root,
        specs_dir=specs_dir,
        comments_dir=comments_dir,
        author_dir=author_dir,
        progress_dir=progress_dir,
        logs_dir=logs_dir,
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def next_version_filename(current_name: str) -> str:
    match = re.search(r"\.v(\d+)\.md$", current_name)
    if not match:
        stem = Path(current_name).stem
        return f"{stem}.v2.md"
    current_version = int(match.group(1))
    return current_name.replace(f".v{current_version}.md", f".v{current_version + 1}.md")


def comment_filename(spec_name: str) -> str:
    return f"comment_{Path(spec_name).name}"


def author_filename(spec_name: str) -> str:
    return f"author_{Path(spec_name).name}"


def progress_filename(round_number: int) -> str:
    return f"progress_round_{round_number}.md"