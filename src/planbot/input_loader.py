from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re

from src.shared.io_utils import read_text


@dataclass
class ReferenceDocument:
    path: Path
    content: str
    source_type: str


# Known api:// scheme prefixes that the resolver handles.
_API_SCHEME = "api://"

# API path constants — used by callers to build runtime_reference_overrides.
API_CLIENT_PROFILE = f"{_API_SCHEME}client_profile"
API_HOLDINGS = f"{_API_SCHEME}holdings"
API_PRODUCT_CATALOG = f"{_API_SCHEME}product_catalog"


def _convert_pdf_to_text(path: Path) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise RuntimeError(
            "PDF conversion requires markitdown with PDF extras. Install dependencies with: pip install -r requirements.txt"
        ) from exc

    converter = MarkItDown()
    result = converter.convert(str(path))

    for attribute in ("text_content", "markdown", "content", "text"):
        value = getattr(result, attribute, None)
        if isinstance(value, str) and value.strip():
            return value

    if isinstance(result, str) and result.strip():
        return result

    raise ValueError(f"PDF conversion returned empty content for {path.name}")


def _derive_glob_search_folder(root_dir: Path, pattern: str) -> Path:
    """Infer the base folder a glob searches in for clearer diagnostics."""
    wildcard_found = False
    static_parts: list[str] = []

    for part in Path(pattern).parts:
        if any(char in part for char in "*?["):
            wildcard_found = True
            break
        static_parts.append(part)

    if wildcard_found:
        return (root_dir / Path(*static_parts)).resolve()

    # Non-glob pattern: show parent folder that was expected to contain the file.
    return (root_dir / Path(pattern)).parent.resolve()


def load_references(
    root_dir: Path,
    glob_pattern: str | list[str],
    api_resolver: Callable[[str], ReferenceDocument] | None = None,
) -> list[ReferenceDocument]:
    patterns = glob_pattern if isinstance(glob_pattern, list) else [glob_pattern]
    paths_set: set[Path] = set()
    api_docs: list[ReferenceDocument] = []

    for pattern in patterns:
        # ── api:// scheme — delegate to resolver ──────────────────────
        if pattern.startswith(_API_SCHEME):
            if api_resolver is None:
                raise ValueError(
                    f"Pattern '{pattern}' uses {_API_SCHEME} scheme but no "
                    f"api_resolver was provided to load_references."
                )
            api_docs.append(api_resolver(pattern))
            continue

        # ── filesystem glob ───────────────────────────────────────────
        matched_paths = {path for path in root_dir.glob(pattern) if path.is_file()}
        # If config is markdown-only, include sibling PDFs automatically.
        if pattern.endswith(".md"):
            matched_paths.update(path for path in root_dir.glob(pattern[:-3] + ".pdf") if path.is_file())

        if not matched_paths:
            search_folder = _derive_glob_search_folder(root_dir, pattern)
            raise FileNotFoundError(
                f"Reference glob '{pattern}' matched no files under root '{root_dir}'. "
                f"Expected files under '{search_folder}' (exists={search_folder.exists()})."
            )

        paths_set.update(matched_paths)

    paths = sorted(paths_set)
    references: list[ReferenceDocument] = []
    for path in paths:
        if not path.is_file():
            continue

        suffix = path.suffix.lower()
        resolved = path.resolve()

        if suffix == ".md":
            references.append(
                ReferenceDocument(path=resolved, content=read_text(resolved), source_type="markdown")
            )
        elif suffix == ".csv":
            references.append(
                ReferenceDocument(path=resolved, content=read_text(resolved), source_type="csv")
            )
        elif suffix == ".json":
            references.append(
                ReferenceDocument(path=resolved, content=read_text(resolved), source_type="json")
            )
        elif suffix == ".pdf":
            references.append(
                ReferenceDocument(path=resolved, content=_convert_pdf_to_text(resolved), source_type="pdf")
            )

    # Append api:// docs after filesystem docs (stable ordering).
    references.extend(api_docs)
    return references


def extract_urls_from_references(
    references: list[ReferenceDocument],
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
