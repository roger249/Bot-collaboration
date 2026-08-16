#!/usr/bin/env python3
"""Apply a directory of override files onto a target directory.

YAML files (``.yaml`` / ``.yml``) are deep-merged onto the corresponding
target file so that partial overrides are supported: an override may contain
only the keys it wants to change, and every unspecified key is inherited from
the default file baked into the image.

Non-YAML files (prompts, ``.ini``, etc.) are copied verbatim.

Inert sample/template files (dotfiles, or names ending in ``.example``,
``.sample``, ``.dist``, ``.template``) are ignored so a sample override can be
shipped alongside the real config without being applied.

Merge semantics for YAML:
  * dict merged into dict  -> recursive merge
  * any other value        -> override replaces the target value
    (lists are replaced in full, not concatenated)

Usage:
    python merge_yaml.py <override_dir> <target_dir>
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import yaml

_YAML_SUFFIXES = {".yaml", ".yml"}
_IGNORED_SUFFIXES = {".example", ".sample", ".dist", ".template"}


def deep_merge(base, override):
    """Recursively merge ``override`` onto ``base``."""
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for key, value in override.items():
            if key in result:
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    return override


def load_yaml(path: Path):
    """Load a YAML file, returning ``{}`` for empty/missing content."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return {} if data is None else data


def dump_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)


def _is_ignored(name: str) -> bool:
    """Return True for inert sample/template/dot files that should be skipped."""
    lowered = name.lower()
    return (
        name.startswith(".")
        or any(lowered.endswith(suffix) for suffix in _IGNORED_SUFFIXES)
    )


def apply_override(override_dir: Path, target_dir: Path) -> None:
    """Merge/copy files from ``override_dir`` onto ``target_dir``."""
    if not override_dir.is_dir():
        return
    for override_file in sorted(override_dir.rglob("*")):
        if not override_file.is_file() or _is_ignored(override_file.name):
            continue
        rel = override_file.relative_to(override_dir)
        target_file = target_dir / rel
        if override_file.suffix.lower() in _YAML_SUFFIXES:
            base_data = load_yaml(target_file) if target_file.exists() else {}
            merged = deep_merge(base_data, load_yaml(override_file))
            dump_yaml(target_file, merged)
        else:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(override_file, target_file)


def main(argv):
    if len(argv) != 3:
        print(f"Usage: {argv[0]} <override_dir> <target_dir>", file=sys.stderr)
        return 2
    override_dir = Path(argv[1])
    target_dir = Path(argv[2])
    if not target_dir.is_dir():
        print(f"target dir not found: {target_dir}", file=sys.stderr)
        return 1
    apply_override(override_dir, target_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
