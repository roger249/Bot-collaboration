# Data Access Layer — Sprint 2: Bank API Simulator + `BankRestDataAdapter`

Status: **Planned** — scope for a future sprint; refine before start.

This document groups the Sprint 2 work items from
[data_access_layer.md](data_access_layer.md) into ordered tasks.

## Objective

Replace `data_server.py` with a **bank API simulator** that exposes only raw
data (clients, holdings, products) via OpenAPI.  This lets developers test the
REST adapter path without a real bank integration.  All business logic
(scorecards, similarity, fitness, search) moves to direct Python invocation.

## Task 1 — Shrink `data_server.py` to a Bank API Simulator

`data_server.py` currently exposes both raw data **and** business-logic
endpoints (scorecard, similarity, fitness, search).  This task strips it down to
a pure bank simulator.

**Keep (raw data — what the bank exposes):**

| Endpoint | Adapter call |
|---|---|
| `GET /api/v1/clients/{client_id}` | `fetch_clients([client_id])` |
| `GET /api/v1/clients` | `fetch_clients()` |
| `GET /api/v1/holdings` | `fetch_holdings()` |
| `GET /api/v1/products/{product_id}` | `fetch_products([product_id])` |
| `GET /api/v1/products` | `fetch_products()` |

**Remove (business logic — now Python-only, no HTTP):**

- `POST /api/v1/clients/search`
- `GET /api/v1/clients/readiness`
- `GET /api/v1/clients/holdings/maturing`
- `POST /api/v1/products/search_similar`
- `POST /api/v1/products/reinvestment-candidates`
- `POST /api/v1/products/fitness-score`

No backward compatibility.  Consumers call `client_api.py` / `product_tool.py`
functions directly in-process (as `proposal_server.py` already does).

**Simulator shape:** serves the **internal** shape (DuckDB's native field names),
so it behaves as a faithful stand-in for a bank that already exposes the same
contract.  Shape-mapping is still implemented in `BankRestDataAdapter` and
covered by unit tests against a mock, but the simulator itself doesn't force a
different shape.

### Consequence — candidate selection moves into the proposal server (Option A)

`HttpApiResolver.candidate_products` currently calls the
`reinvestment-candidates` endpoint (being removed).  In Phase B, the proposal
server must compute candidates **in-process** instead:

1. `HttpApiResolver` fetches only raw data (`source_product` + full product
   catalog) from the simulator.
2. The proposal server calls `search_similar_to_product()` **locally** (Python)
   to rank candidates.

This keeps the bank as a pure data pipe and preserves the similarity-scoring IP
in the Logic Layer.

**Blast radius (verified against code):**

| File | Calls `HttpApiResolver.candidate_products`? |
|---|---|
| `src/planbot/http_resolver.py` | ✅ internally — `_format_catalog_json()` (line 254) |
| `src/integrations/reinvestment_proposal.py` | ✅ — line 315 (only external caller) |
| `src/integrations/product_opportunity_proposal.py` | ❌ — uses `client_profile`/`source_product` only |
| `src/integrations/portfolio_review.py` | ❌ — uses `client_profile` only |

Only **two files** change:

1. `http_resolver.py` — `candidate_products` refactored to return the raw
   product universe (drop the `reinvestment-candidates` POST).
2. `reinvestment_proposal.py` — applies `search_similar_to_product()` locally
   on that universe.

```python
# data_server.py — Sprint 2 (bank simulator)
from src.adapters.data_adapter import build_data_adapters

client_adapter, product_adapter = build_data_adapters(_raw_config)

@app.get("/api/v1/clients/{client_id}")
def get_client(client_id: str):
    rows = client_adapter.fetch_clients([client_id])
    if not rows:
        raise HTTPException(404)
    return rows[0]
```

## Task 2 — `BankRestDataAdapter` Implementation

Implement `src/adapters/rest_adapter.py` with:

| Endpoint | Maps to |
|---|---|
| `GET /crm/clients` | `fetch_clients(client_ids)` |
| `GET /custody/holdings` | `fetch_holdings(client_ids)` |
| `GET /product-master/products` | `fetch_products(product_ids)` |

Requirements:

- Return plain `list[dict]` — shape-mapping only, no business logic.
- Pagination uses `offset`/`limit` query params (matching the `DataAdapter`
  protocol).  If a real bank API uses `page`/`size`, the adapter translates.
- Handle auth via `auth_token_env` from config (adapter sends `Authorization:
  Bearer <token>`).  The simulator's auth enforcement is deferred.
- Error handling: **raise on `5xx`/`429`/`401`** (backend broken / rate-limited /
  unauthorized — caller must handle); **return `[]`/`None` on `404`** (resource
  genuinely missing).  Mirrors `HttpApiResolver` today.
- `health_check()` returns `False` when unreachable.

## Task 3 — Adapter Caching

Add in-memory TTL caching inside `BankRestDataAdapter` (invisible to the Logic
Layer).  Use [`cachetools.TTLCache`](https://cachetools.readthedocs.io/) — a
single pure-Python dependency with bounded size + per-entry expiry, avoiding
hand-rolled locking/expiry.  Redis is deferred until horizontal scaling is
justified.

Cache parameters are externalized to `config_planbot.yaml` (repo convention),
read once by the factory and passed to the adapter:

```yaml
# config/config_planbot.yaml
data_source:
  duckdb:
    path: data/planbot/db/planbot.duckdb
  rest:
    client_base_url: https://bank-internal/crm/api/v2
    product_base_url: https://bank-internal/product-master/api/v1
    auth_token_env: BANK_API_KEY
    timeout_seconds: 10
    cache_ttl_seconds: 300    # per-entry expiry (0 = disable cache)
    cache_maxsize: 512        # max cached entries per adapter
```

```python
from cachetools import TTLCache


class BankRestDataAdapter:
    def __init__(self, base_url, auth_token, *, cache_ttl: int = 300, cache_maxsize: int = 512):
        self._cache: TTLCache[str, list[dict]] = TTLCache(
            maxsize=cache_maxsize, ttl=cache_ttl
        ) if cache_ttl > 0 else None

    def fetch_clients(self, client_ids=None, *, limit=None, offset=0):
        if self._cache is None:
            return self._do_rest_call(client_ids, limit, offset)
        key = _make_key(client_ids, limit, offset)
        try:
            return self._cache[key]
        except KeyError:
            data = self._do_rest_call(client_ids, limit, offset)
            self._cache[key] = data
            return data
```

The factory wires config → adapter:

```python
def build_data_adapters(config: dict) -> tuple[DataAdapter, DataAdapter]:
    ...
    rest = config.get("data_source", {}).get("rest", {})
    client = BankRestDataAdapter(
        base_url=rest["client_base_url"],
        auth_token=os.environ[rest["auth_token_env"]],
        cache_ttl=rest.get("cache_ttl_seconds", 300),
        cache_maxsize=rest.get("cache_maxsize", 512),
    )
    ...
```

Dependency: add `cachetools` as a runtime dependency (`uv add cachetools`).
`cachetools` caches implement `collections.abc.MutableMapping`, so a future
`RedisCache` is a drop-in swap through the same interface.

| Factor | In-memory (`TTLCache`) | Redis |
|---|---|---|
| Setup | Zero | New service + connection handling |
| Latency | Microseconds | ~1ms round-trip |
| Failure mode | Nothing to fail | Redis down → all calls fail |
| Shared across containers | No | Yes |

## Task 4 — REST Integration Tests

Add `@pytest.mark.rest` tests against the bank simulator (no live bank
dependency).  The existing single integration suite continues to run against
DuckDB; the REST marker gates auth, pagination, and caching tests.

## Task 5 — Seeder Extraction

Move seeder/ETL code out of `investor_readiness_score.py` into an isolated
module under `src/test_data/` (e.g. `client_seed.py`).  The scorecard file keeps
only pure functions; the seeder keeps the `duckdb` import.

```text
src/
├── test_data/
│   ├── client_seed.py        # init_client_db, get_client_db_conn, _normalize_holdings_product_ids
│   ├── product_catalog_seed.py
│   └── reseed.py
└── planbot/
    └── investor_readiness_score.py   # pure scorecard functions only
```

## Deferred to Sprint 3

Cross-system inconsistency handling (Tier 2/3) is moved to Sprint 3 — see
[data_access_layer_sprint3.md](data_access_layer_sprint3.md).
