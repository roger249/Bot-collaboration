from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from src.shared.io_utils import read_text


@dataclass
class MarkdownReference:
    path: Path
    content: str


def load_markdown_references(root_dir: Path, glob_pattern: str) -> list[MarkdownReference]:
    paths = sorted(root_dir.glob(glob_pattern))
    references: list[MarkdownReference] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() == ".md":
            references.append(MarkdownReference(path=path.resolve(), content=read_text(path.resolve())))
    return references


def build_reference_block(references: list[MarkdownReference]) -> str:
    if not references:
        return "No local markdown references were provided."

    chunks: list[str] = []
    for index, ref in enumerate(references, start=1):
        chunks.append(f"## Reference {index}: {ref.path.name}\n\n{ref.content.strip()}")
    return "\n\n".join(chunks)


def extract_urls_from_references(
    references: list[MarkdownReference],
    url_reference_filename: str | None = "websites.md",
) -> list[str]:
    url_pattern = re.compile(r"https?://[^\s<>()\]\[]+")
    urls: list[str] = []
    target_name = url_reference_filename.lower() if url_reference_filename else None

    for ref in references:
        if target_name is not None and ref.path.name.lower() != target_name:
            continue
        for match in url_pattern.findall(ref.content):
            cleaned = match.rstrip(".,;:!?")
            if cleaned:
                urls.append(cleaned)

    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped
