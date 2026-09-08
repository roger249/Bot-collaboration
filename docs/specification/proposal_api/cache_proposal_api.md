# LLM Call Cache

> **Status**: SPECIFICATION (finalized — awaiting implementation authorization)

## 1. Objective

LLM inference is the dominant cost and latency in the proposal pipeline (a
single CrewAI call can take tens of seconds and cost real money).  Introduce an
in-memory **LLM call cache** so that an identical request (same prompt, model,
and provider endpoint) returns the previously-generated response instantly,
instead of re-invoking the provider.

- Backed by **LiteLLM's built-in in-memory cache** (`litellm.cache =
  Cache(type="local", ...)`) — no custom cache layer.
- Keyed by **LiteLLM itself** (model + messages + request params, including the
  resolved `base_url`).
- **TTL** is a **global parameter in `config/config_planbot.yaml`**.

## 2. Background / current state

Production LLM calls for the proposal pipeline all flow through **CrewAI**:

| Path | Where | Transport | Consumers |
|---|---|---|---|
| **CrewAI** | `_build_crew_llm()` → CrewAI `LLM` → `_generate_with_crew()` in `src/planbot/crew_workflow.py` | CrewAI's own HTTP client | all proposal pipelines (`run_crew_planbot`) |

The legacy **direct client** (`OpenAICompatibleClient.generate()` in
`src/shared/llm_client.py`) is **dead code** for production: the author–reviewer
workflow that used it (`src/author_reviewer/workflow.py::run_workflow`) is
unreferenced, and the live `crew_workflow.py` paths only call `build_client()`
for the `mock` provider.  It is therefore **out of scope** (§3.2).

CrewAI's `LLM` (for `openai/...` model strings) routes through **LiteLLM**
(`is_litellm=True`, `litellm.completion(...)`).  LiteLLM ships a built-in
in-memory cache (`litellm.cache = Cache(type="local", ...)`) that is **off by
default** and that CrewAI does **not** enable.  This spec turns it on rather than
building a custom cache.

## 3. Scope

### 3.1 In scope

1. Cache **successful** LLM completions only.  Errors, timeouts, and empty
   responses are **never** cached.
2. The **CrewAI proposal path only** (`run_crew_planbot` → `_generate_with_crew`),
   since it is the single production LLM transport.

### 3.2 Out of scope

- The **direct client** (`OpenAICompatibleClient` in `src/shared/llm_client.py`)
  and the author–reviewer workflow that used it — dead code; not cached.
- The `mock` provider (instant, deterministic, used by tests) — never cached.
- Tool executions (web search, YFinance, product search, fitness score) — these
  already go through the adapter/tool layer and are not LLM text generation.
- A persistent / cross-process / distributed cache (Redis, disk) or multi-worker
  coordination — this is LiteLLM's in-memory (`type="local"`) cache only (each
  server process keeps its own cache; no shared store).

## 4. Cache key

The cache key is **LiteLLM's own** — we do not hand-roll a hash.  LiteLLM keys
its in-memory cache on the full completion request identity: model, messages,
and request params (which include the resolved `base_url`/`api_base`, so the
same prompt routed to a different endpoint is a different entry).

This satisfies the original requirement ("input prompt, along with model name
and URL are the same") without reimplementing key derivation.

## 5. Cache behaviour

- **TTL** — read from `config/config_planbot.yaml` (see §6), passed to LiteLLM
  as `default_in_memory_ttl`.  `ttl_seconds: 0` disables the cache (we do not
  set `litellm.cache`).
- **Hit** — LiteLLM returns the cached completion without calling the provider.
- **Miss** — LiteLLM calls the provider and stores the completion.
- **Eviction** — LiteLLM's `InMemoryCache` evicts on TTL and on a fixed
  in-memory capacity (`max_size_in_memory`, default `200`); oldest/expired
  entries are evicted.
- **Concurrency** — LiteLLM's cache is process-local; no extra locking is
  required by our code.
- **Non-determinism** — caching assumes the provider is deterministic for a
  fixed request.  Providers with sampling (`temperature > 0`) may return
  different text per call; the cache intentionally sacrifices re-sampling in
  exchange for speed and cost — an accepted trade-off for this change.

## 6. Configuration

Add a new top-level section to `config/config_planbot.yaml` (sibling to
`common`, `data_source`, `server`, etc.):

```yaml
llm_cache:
  enabled: true          # master switch
  ttl_seconds: 86400     # global TTL, seconds (0 = disabled); 24h default
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | bool | `true` | Master switch.  When false, `litellm.cache` is left unset. |
| `ttl_seconds` | int ≥ 0 | `86400` | Global TTL in seconds (default 24 hours), passed to LiteLLM as `default_in_memory_ttl`; `0` disables the cache. |

> LiteLLM's in-memory cache capacity (`max_size_in_memory`) is **fixed at 200**
> by LiteLLM and is not exposed through our config — entries evict on TTL/LRU
> beyond that.

Read via a small loader (e.g. `load_llm_cache_config()` in
`src/planbot/config.py`), since the cache is scoped to the CrewAI proposal path
configured by `config_planbot.yaml`.  It is **not** part of `config/config.yaml`
/ `AppConfig`.

## 7. Placement in code

### 7.1 Enable LiteLLM's cache once at startup

No custom cache module is written.  At process startup (once), read
`llm_cache` from `config/config_planbot.yaml` and, when `enabled` and
`ttl_seconds > 0`, set:

```python
import litellm
from litellm.caching import Cache

litellm.cache = Cache(
    type="local",
    default_in_memory_ttl=ttl_seconds,
)
```

When disabled, `litellm.cache` is left as `None` (the default), so behaviour is
unchanged.

### 7.2 CrewAI path benefits automatically

Because CrewAI's `LLM` (for `openai/...` model strings) calls
`litellm.completion(...)`, setting `litellm.cache` once is enough — every
proposal pipeline (`run_crew_planbot` → `_generate_with_crew`) is cached with no
change to `_build_crew_llm()` or any CrewAI internals.

> LiteLLM caches at the **per-completion** level, so intermediate tool-loop
> turns are also cached (a broader cache than the earlier "final messages only"
> idea).  This is accepted — it is the built-in behaviour and avoids
> reimplementing keying/eviction.

## 8. Worked examples

| Scenario | Behaviour |
|---|---|
| Identical request replayed within TTL | cache **hit**, provider not called, identical text returned |
| Same prompt, different `temperature` | **miss** (temperature is in the key) |
| Same prompt, same model, different provider URL | **miss** (URL is in the key) |
| Same prompt, different model | **miss** (model is in the key) |
| Provider returns error / timeout | **not cached**, error propagates as today |
| `enabled: false` or `ttl_seconds: 0` | pass-through, no cache read/write |
| `mock` provider | never cached |

## 9. Edge cases

- **Large prompts** — LiteLLM stores the response text keyed by the request;
  its `max_size_per_item` (default `1024` bytes) and `max_size_in_memory`
  (default `200` entries) bound memory usage.
- **Empty response** — LiteLLM does not cache failures/empty completions;
  errors propagate as today.
- **Cache disabled at runtime** — `litellm.cache` left `None`; no behavioural
  change.
- **Restart = full invalidation** — the cache is in-memory only, so a process
  restart produces a fresh, empty cache.  No explicit invalidation mechanism
  is required beyond TTL expiry + restart.

## 10. Acceptance Criteria

All must hold before merge.

### Functional

1. `config/config_planbot.yaml` accepts `llm_cache.{enabled, ttl_seconds}` with
   the defaults in §6.
2. With `enabled: true` / `ttl_seconds > 0`, `litellm.cache` is set to an
   in-memory `Cache(type="local", default_in_memory_ttl=ttl_seconds)` at
   startup; an identical completion within TTL is served from cache (provider
   not called again).
3. Changing model / URL / temperature produces a cache miss (LiteLLM keying).
4. Errors, timeouts, and empty responses are never cached.
5. The `mock` provider path is unaffected (it does not call `litellm.completion`).

### Error handling

6. Invalid config (`ttl_seconds < 0`, non-bool `enabled`) → clear startup error.
7. Cache disabled (`enabled: false` / `ttl_seconds: 0`) → `litellm.cache` left
   `None`, transparent pass-through.

### Regression

8. All existing **fast** unit tests pass (full suite excluding the slow e2e file).
9. The end-to-end **regression** `tests/test_proposal_API.py` passes (slow,
   live-LLM; the mandatory gate for integration changes) and covers
   `/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings`,
   `/api/v1/product-opportunity-proposal`, and
   `/api/v1/product-opportunity-proposal-automatch`.
10. New unit tests (normal + exception) verify the loader (defaults, `0`
    disables) and that enabling sets `litellm.cache` with the right TTL.

### Contract / docs

11. `config/config_planbot.yaml` (and `config-override/config_planbot.yaml.example`
    if the cache is meant to be overridable) updated; the loader documented.

## 11. Decisions (resolved)

1. **Determinism vs. sampling** — cache regardless of `temperature`; sacrifice
   re-sampling for speed/cost.
2. **TTL default & location** — top-level `llm_cache` in
   `config/config_planbot.yaml`; default `ttl_seconds: 86400` (24 hours),
   `enabled: true`.
3. **Cache scope / distribution** — in-memory per-process only; no multi-worker
   / distributed coordination.
4. **Cache granularity** — per-completion (LiteLLM's native granularity),
   including intermediate tool-loop turns.
5. **Invalidation** — TTL expiry plus **process restart**.
6. **Implementation** — use **LiteLLM's built-in cache** (`litellm.cache =
   Cache(type="local", default_in_memory_ttl=...)`); no custom cache module, no
   `cachetools`, no CrewAI-internal interception.  Verified against CrewAI
   1.14.4 / LiteLLM 1.83.0.

## 12. Outstanding issues

None — all open questions are resolved.
