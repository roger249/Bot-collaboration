from __future__ import annotations

from pathlib import Path

import pytest

from src.planbot.input_loader import load_references


def test_load_references_raises_when_any_glob_matches_no_files(tmp_path: Path):
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "exists.md").write_text("hello", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="missing\\.md") as exc_info:
        load_references(
            tmp_path,
            [
                "refs/exists.md",
                "refs/missing.md",
            ],
        )

    message = str(exc_info.value)
    assert "Expected files under" in message
    assert str((tmp_path / "refs").resolve()) in message


def test_load_references_succeeds_when_all_globs_match_files(tmp_path: Path):
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "doc.md").write_text("# Doc", encoding="utf-8")

    references = load_references(tmp_path, "refs/doc.md")

    assert len(references) == 1
    assert references[0].path.name == "doc.md"
