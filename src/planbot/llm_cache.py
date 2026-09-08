"""LiteLLM-backed LLM call cache (in-memory, per-process).

The proposal pipeline invokes CrewAI, which routes ``openai/...`` model strings
through LiteLLM (``litellm.completion``).  LiteLLM ships an in-memory cache that
is off by default; enabling it here caches successful completions keyed by
LiteLLM itself (model + messages + request params, incl. the resolved base URL).

Configuration lives in ``config/config_planbot.yaml`` under ``llm_cache``:

    llm_cache:
      enabled: true        # master switch
      ttl_seconds: 86400   # global TTL in seconds (0 disables); 24h default

The cache is process-local: a restart yields a fresh, empty cache.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

LOGGER = logging.getLogger(__name__)

_DEFAULT_ENABLED = True
_DEFAULT_TTL_SECONDS = 86400

_initialized = False


def _load_llm_cache_section(config_path: str | Path) -> dict:
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    return data.get("llm_cache") or {}


def enable_llm_cache(config_path: str | Path) -> None:
    """Enable LiteLLM's in-memory cache once per process, from config.

    Idempotent: only the first call has any effect.  When ``enabled`` is false
    or ``ttl_seconds == 0``, ``litellm.cache`` is left as ``None`` (the default)
    and no caching occurs.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    section = _load_llm_cache_section(config_path)
    enabled = bool(section.get("enabled", _DEFAULT_ENABLED))
    ttl_seconds = int(section.get("ttl_seconds", _DEFAULT_TTL_SECONDS))

    if not enabled or ttl_seconds <= 0:
        LOGGER.info(
            "LLM cache disabled (enabled=%s, ttl_seconds=%s)",
            enabled,
            ttl_seconds,
        )
        return

    import litellm
    from litellm.caching import Cache

    litellm.cache = Cache(type="local", default_in_memory_ttl=ttl_seconds)
    LOGGER.info("LLM cache enabled (in-memory, ttl=%ss)", ttl_seconds)
