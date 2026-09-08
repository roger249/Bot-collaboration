"""Unit tests for the LiteLLM-backed LLM cache loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.planbot import llm_cache


def _write_config(tmp_path: Path, yaml_text: str) -> Path:
    path = tmp_path / "config_planbot.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    return path


def test_enable_sets_litellm_cache(tmp_path: Path):
    import litellm

    llm_cache._initialized = False
    litellm.cache = None
    cfg = _write_config(tmp_path, "llm_cache:\n  enabled: true\n  ttl_seconds: 60\n")
    llm_cache.enable_llm_cache(cfg)
    assert litellm.cache is not None
    # local cache default TTL should have been overridden to 60
    assert litellm.cache.ttl == 60


def test_disable_leaves_cache_none(tmp_path: Path):
    import litellm

    llm_cache._initialized = False
    litellm.cache = None
    cfg = _write_config(tmp_path, "llm_cache:\n  enabled: false\n  ttl_seconds: 60\n")
    llm_cache.enable_llm_cache(cfg)
    assert litellm.cache is None


def test_ttl_zero_disables(tmp_path: Path):
    import litellm

    llm_cache._initialized = False
    litellm.cache = None
    cfg = _write_config(tmp_path, "llm_cache:\n  enabled: true\n  ttl_seconds: 0\n")
    llm_cache.enable_llm_cache(cfg)
    assert litellm.cache is None


def test_missing_section_uses_defaults(tmp_path: Path):
    import litellm

    llm_cache._initialized = False
    litellm.cache = None
    cfg = _write_config(tmp_path, "other:\n  x: 1\n")
    llm_cache.enable_llm_cache(cfg)
    # default: enabled=true, ttl=86400
    assert litellm.cache is not None
    assert litellm.cache.ttl == 86400


def test_idempotent(tmp_path: Path):
    import litellm

    llm_cache._initialized = False
    litellm.cache = None
    cfg = _write_config(tmp_path, "llm_cache:\n  enabled: true\n  ttl_seconds: 60\n")
    llm_cache.enable_llm_cache(cfg)
    first = litellm.cache
    llm_cache.enable_llm_cache(cfg)  # second call is a no-op
    assert litellm.cache is first
