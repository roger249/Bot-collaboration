from __future__ import annotations

from pathlib import Path

import pytest

from src.planbot.input_loader import (
    API_CLIENT_PROFILE,
    API_HOLDINGS,
    API_PRODUCT_CATALOG,
    ReferenceDocument,
    load_references,
)


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


# ---------------------------------------------------------------------------
# api:// resolver tests (Sprint 2)
# ---------------------------------------------------------------------------


def _make_mock_resolver(
    responses: dict[str, ReferenceDocument] | None = None,
):
    """Build a resolver that returns pre-configured ReferenceDocuments."""
    if responses is None:
        responses = {
            API_CLIENT_PROFILE: ReferenceDocument(
                path=Path("api://client/test-001/profile.md"),
                content="# Test Profile",
                source_type="markdown",
            ),
            API_HOLDINGS: ReferenceDocument(
                path=Path("api://client/test-001/holdings.csv"),
                content="client_id,product_id\nTEST,PRD01",
                source_type="csv",
            ),
            API_PRODUCT_CATALOG: ReferenceDocument(
                path=Path("api://client/test-001/catalog.json"),
                content='{"products": []}',
                source_type="json",
            ),
        }

    def resolve(api_path: str) -> ReferenceDocument:
        if api_path not in responses:
            raise ValueError(f"Unknown API path: {api_path!r}")
        return responses[api_path]

    return resolve


def test_api_resolver_delegates_api_patterns():
    """load_references calls api_resolver for api:// patterns."""
    resolver = _make_mock_resolver()

    references = load_references(
        Path("/fake/root"),
        [API_CLIENT_PROFILE],
        api_resolver=resolver,
    )

    assert len(references) == 1
    assert references[0].source_type == "markdown"
    assert references[0].content == "# Test Profile"
    assert "test-001/profile.md" in str(references[0].path)


def test_api_resolver_mixed_api_and_file_patterns(tmp_path: Path):
    """load_references handles api:// patterns alongside filesystem globs."""
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "doc.md").write_text("# File Doc", encoding="utf-8")

    resolver = _make_mock_resolver()

    references = load_references(
        tmp_path,
        ["refs/doc.md", API_CLIENT_PROFILE],
        api_resolver=resolver,
    )

    assert len(references) == 2
    sources = {r.source_type for r in references}
    assert "markdown" in sources  # both file and API produce markdown-type docs
    contents = {r.content for r in references}
    assert "# File Doc" in contents
    assert "# Test Profile" in contents


def test_api_resolver_falls_back_to_filesystem(tmp_path: Path):
    """Non-api:// patterns use filesystem glob even when api_resolver is set."""
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "doc.md").write_text("# Doc", encoding="utf-8")

    references = load_references(
        tmp_path,
        "refs/doc.md",
        api_resolver=_make_mock_resolver(),
    )

    assert len(references) == 1
    assert references[0].path.name == "doc.md"


def test_api_pattern_without_resolver_raises():
    """load_references raises when api:// pattern used without api_resolver."""
    with pytest.raises(ValueError, match="api_resolver"):
        load_references(
            Path("/fake/root"),
            [API_CLIENT_PROFILE],
            api_resolver=None,
        )


def test_api_resolver_returns_correct_source_type():
    """Each API path returns ReferenceDocument with the expected source_type."""
    resolver = _make_mock_resolver()

    refs = load_references(
        Path("/fake/root"),
        [API_CLIENT_PROFILE, API_HOLDINGS, API_PRODUCT_CATALOG],
        api_resolver=resolver,
    )

    types = {str(r.path): r.source_type for r in refs}
    for r in refs:
        path_str = str(r.path)
        if "profile.md" in path_str:
            assert r.source_type == "markdown"
        elif "holdings.csv" in path_str:
            assert r.source_type == "csv"
        elif "catalog.json" in path_str:
            assert r.source_type == "json"
        else:
            pytest.fail(f"Unexpected document path: {path_str}")


def test_api_resolver_unknown_path_raises():
    """Resolver raises for unknown api:// paths; caller catches it."""
    def resolver(path: str) -> ReferenceDocument:
        raise ValueError(f"Unknown API path: {path!r}")

    with pytest.raises(ValueError, match="Unknown API path"):
        load_references(
            Path("/fake/root"),
            ["api://unknown"],
            api_resolver=resolver,
        )


def test_api_resolver_filtering_returns_requested_client_only():
    """API resolver returns only the requested client_id data, not all clients."""
    captured_paths: list[str] = []

    def resolver(api_path: str) -> ReferenceDocument:
        captured_paths.append(api_path)
        return ReferenceDocument(
            path=Path(f"api://client/PB-001/{api_path.split('/')[-1]}"),
            content=f"data for PB-001 via {api_path}",
            source_type="json",
        )

    refs = load_references(
        Path("/fake/root"),
        [API_CLIENT_PROFILE, API_HOLDINGS],
        api_resolver=resolver,
    )

    assert len(refs) == 2
    # Verify the resolver was called with the exact paths (not all clients).
    assert captured_paths == [API_CLIENT_PROFILE, API_HOLDINGS]
    assert all("PB-001" in str(r.path) for r in refs)


# ---------------------------------------------------------------------------
# HTTP resolver tests (Phase B)
# ---------------------------------------------------------------------------


class TestHttpApiResolver:
    """Tests for the HTTP-based HttpApiResolver (Phase B)."""

    def test_as_callable_returns_valid_resolver(self):
        """as_callable() produces a callable compatible with load_references."""
        from src.planbot.http_resolver import HttpApiResolver

        resolver = HttpApiResolver(
            client_id="TEST-001",
            source_product_id="PROD-001",
            base_url="http://localhost:8000",
        )
        fn = resolver.as_callable()
        assert callable(fn)

    def test_unknown_api_path_raises(self):
        """Resolver raises ValueError for unknown api:// paths."""
        from src.planbot.http_resolver import HttpApiResolver

        resolver = HttpApiResolver(
            client_id="TEST-001",
            source_product_id="PROD-001",
        )
        fn = resolver.as_callable()

        with pytest.raises(ValueError, match="Unknown API path"):
            fn("api://unknown")

    def test_resolver_returns_reference_documents_with_mocked_http(self):
        """Resolver formats HTTP-fetched data into ReferenceDocuments."""
        from unittest.mock import patch

        from src.planbot.http_resolver import HttpApiResolver
        from src.planbot.input_loader import (
            API_CLIENT_PROFILE,
            API_HOLDINGS,
            API_PRODUCT_CATALOG,
            ReferenceDocument,
        )

        resolver = HttpApiResolver(
            client_id="TEST-001",
            source_product_id="PROD-001",
            base_url="http://localhost:8000",
        )

        # Inject pre-fetched data to bypass HTTP
        resolver._client_profile = {
            "client_id": "TEST-001",
            "name": "Test",
            "risk_rating": 3,
            "holdings": [
                {"product_id": "P1", "instrument_name": "Bond A"},
            ],
        }
        resolver._client_profile_fetched = True
        resolver._source_product = {
            "product_id": "PROD-001",
            "name": "Source Product",
            "product_type": "bond",
        }
        resolver._source_product_fetched = True
        resolver._candidate_products = [
            {"product_id": "C1", "name": "Candidate 1", "similarity_score": 0.85},
        ]
        resolver._candidates_fetched = True

        fn = resolver.as_callable()

        # Profile doc
        doc = fn(API_CLIENT_PROFILE)
        assert isinstance(doc, ReferenceDocument)
        assert doc.source_type == "markdown"
        assert "TEST-001" in doc.content
        assert "# Client Profile" in doc.content

        # Holdings doc
        doc = fn(API_HOLDINGS)
        assert isinstance(doc, ReferenceDocument)
        assert doc.source_type == "csv"
        assert "Bond A" in doc.content

        # Catalog doc
        doc = fn(API_PRODUCT_CATALOG)
        assert isinstance(doc, ReferenceDocument)
        assert doc.source_type == "json"
        assert "Candidate 1" in doc.content
