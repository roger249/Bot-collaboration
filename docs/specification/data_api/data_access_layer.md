# Data Access Layer — Two-Layer Architecture

Status: **Design proposal** — not yet implemented.

## Problem

All client/product APIs in `src/integrations/` currently access a single DuckDB file
(`data/planbot/db/planbot.duckdb`) via hardcoded `duckdb.connect()` calls.
To deploy in a bank environment, these APIs must retrieve data from bank-internal
systems (CRM, custody, product master, etc.) instead.

The APIs also embed significant **business logic** (scorecards, similarity scoring,
fitness scoring). This IP must be preserved — only the raw data retrieval layer
should be replaced.

## Principle: Two Layers, Two Access Surfaces

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  LAYER 2 — LOGIC LAYER (accessed via Python API)                │
│  ─────────────────────────────────────                           │
│  ★ SCORECARD ENGINE  (our IP, stays)                            │
│    • investor_readiness_score.py                                 │
│      — score_cash_drag(clients, holdings, config) → dict        │
│      — score_concentration_risk(clients, holdings, config) → …  │
│      — score_active_manage(clients, holdings, config) → …       │
│      — score_life_stage(clients, config) → …                    │
│      — compute_total_scores(client_scores, config) → …          │
│    • product_tool.py scoring                                    │
│      — _compute_similarity_score(product, query, sigmas) → …   │
│      — _compute_concentration_risk(clients, holdings, …) → …   │
│      — search_product_by_fitness_score(clients, products, …) → │
│    • client_api.py derived fields                               │
│      — _compute_derived_fields(clients, holdings, products) →  │
│        {cid: {age, has_fund, product_families, cash_pct, …}}   │
│                                                                  │
│  ★ SEARCH / FILTER (pure Python, no SQL)                        │
│    — search(clients, **criteria) → list[dict]                   │
│    — search_by_id(clients, cid) → dict | None                   │
│    — search_holdings_maturing(holdings, products, …) → …        │
│    — search_similar(products, query_attrs, weights, sigmas) →  │
│                                                                  │
│  All operate on plain dicts:                                     │
│    clients  = [{client_id, name, aum, birthdate, …}]            │
│    holdings = [{client_id, product_id, mv, …}]                  │
│    products = [{product_id, type, rr, …}]                       │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LAYER 1 — DATA ACCESS LAYER (accessed via OpenAPI)             │
│  ──────────────────────────────────────────────                  │
│  ◄── Data Adapter Interface  (NEW, swappable)  ──►              │
│                                                                  │
│    fetch_clients(client_ids?)  → list[dict]                     │
│    fetch_holdings(client_ids?) → list[dict]                     │
│    fetch_products(product_ids?) → list[dict]                    │
│                                                                  │
│         ╱                          ╲                             │
│  DuckDBAdapter              BankAPIAdapter                      │
│  (today, dev/test)          (future, per bank)                  │
│  SELECT * FROM …            GET /crm/clients                    │
│                             GET /custody/holdings               │
│                             GET /product-master/products        │
│                                                                  │
│  Exposed as FastAPI endpoints in data_server.py:                │
│    GET  /api/v1/clients/{client_id}                             │
│    GET  /api/v1/clients?risk_rating=3,5                         │
│    GET  /api/v1/clients/maturing?within_days=365                │
│    GET  /api/v1/products/{product_id}                           │
│    POST /api/v1/products/search_similar                         │
│    POST /api/v1/products/search_reinvestment_candidates         │
│    POST /api/v1/products/search_by_fitness_score                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Why Two Explicit Layers?

| Concern | Who owns it | Access surface | Swappable? |
|---|---|---|---|
| Raw data retrieval (SQL, REST, gRPC) | **Layer 1 — DAL** | OpenAPI (`data_server.py`) | Yes — per-bank adapter |
| Scorecard computation, derived fields, filtering | **Layer 2 — Logic** | Python API (`import`) | No — our IP |
| LLM prompt assembly, CrewAI invocation | `proposal_server.py` | Python API | No |

The boundary is:
1. **DAL** returns plain `list[dict]` — zero business logic, zero enrichment.
2. **Logic Layer** consumes those dicts and produces scores, classifications, filters.
3. **Consumers** (proposal_server, tests) call Logic Layer functions directly in-process.
   They never touch DAL directly — the wiring happens once at startup.

## Current State

```
FastAPI Endpoints  (data_server.py, proposal_server.py)
      │
      ▼
client_api.py  /  product_tool.py   ← MIXED: SQL + logic in one file
      │
      ├── Raw SQL (SELECT FROM clients/holdings/products)
      └── Embedded scorecard logic (investor_readiness_score.py, similarity, fitness)
      │
      ▼
duckdb.connect("data/planbot/db/planbot.duckdb")
```

Scorecard functions accept `duckdb.DuckDBPyConnection` and run SQL inline.
`_compute_derived_fields()` in `client_api.py` opens a connection, runs 7 SQL
queries, calls 4 scorecard functions, and returns enriched dicts — all in one
function with no separation boundary.

## Target Contract: Data Adapter Interface (Layer 1)

Layer 1 has **four methods only**. No business logic, no filtering, no enrichment.

```python
class DataAdapter(Protocol):
    """Raw data provider. Returns plain dicts — no business logic."""

    def fetch_clients(
        self,
        client_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]: ...

    def fetch_holdings(
        self,
        client_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]: ...

    def fetch_products(
        self,
        product_ids: list[str] | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]: ...

    def health_check(self) -> bool:
        """Return True if the backend is reachable."""
        ...
```

Pagination (`limit`/`offset`) is part of the protocol from day one — even though
the DuckDB adapter ignores it for now.  The REST adapter maps it to `?page=` and
`?size=`.  Adding it now prevents a protocol change later when the first bank
deployment needs it.

| Method | Returns | Notes |
|---|---|---|
| `fetch_clients` | `[{client_id, name, aum, birthdate, risk_rating, …}]` | `None` = all clients |
| `fetch_holdings` | `[{client_id, product_id, market_value, region, asset_class, …}]` | `None` = all holdings |
| `fetch_products` | `[{product_id, product_type, risk_rating, expected_return, …}]` | `None` = all products |
| `health_check` | `bool` | Used by startup/readiness probes |

DuckDB implementation:

```python
class DuckDBDataAdapter:
    def __init__(self, db_path: Path):
        self._db_path = db_path

    def fetch_clients(self, client_ids=None):
        conn = duckdb.connect(str(self._db_path), read_only=True)
        try:
            query = "SELECT * FROM clients"
            params = []
            if client_ids:
                placeholders = ",".join("?" for _ in client_ids)
                query += f" WHERE client_id IN ({placeholders})"
                params = client_ids
            return [dict(zip(cols, row)) for row in conn.execute(query, params).fetchall()]
        finally:
            conn.close()
    # … same pattern for fetch_holdings, fetch_products
```

Bank REST implementation (future):

```python
class BankRestDataAdapter:
    def __init__(self, base_url: str, auth_token: str, timeout: float = 10):
        self._base_url = base_url
        self._session = httpx.Client(headers={"Authorization": f"Bearer {auth_token}"})

    def fetch_clients(self, client_ids=None):
        # GET /crm/clients or POST /crm/clients/batch
        ...
```

### Adapter Caching

Bank REST adapters need a cache — upstream APIs are slow, rate-limited, and
charged per call.  The cache lives **inside the adapter**, invisible to the
Logic Layer.  Start with in-memory TTL; swap to Redis later if horizontal
scaling is needed.

```python
class BankRestDataAdapter:
    def __init__(self, …, cache_ttl: int = 300):
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._cache_ttl = cache_ttl

    def fetch_clients(self, client_ids=None):
        cache_key = _make_key(client_ids)
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if time.monotonic() - ts < self._cache_ttl:
                return data
        data = self._do_rest_call(client_ids)
        self._cache[cache_key] = (time.monotonic(), data)
        return data
```

Why in-memory first, not Redis:

| Factor | In-memory | Redis |
|---|---|---|
| Setup | Zero — built into adapter | New service, connection handling, health check |
| Latency | Microseconds | Network round-trip (~1ms) |
| Failure mode | Nothing to fail | Redis down → every REST call fails |
| Shared across containers | No | Yes |

The proposal server is single-instance by design (one container).  If horizontal
scaling is needed later, the cache is a one-class swap — `InMemoryCache` →
`RedisCache` — with zero Logic Layer changes.

## Target Contract: Logic Layer API (Layer 2)

Layer 2 functions accept **plain dicts only** — no `duckdb.DuckDBPyConnection`,
no `httpx.Client`, no I/O.

### Scorecard functions (current → target)

Current:
```python
def score_cash_drag(conn: duckdb.DuckDBPyConnection, config: dict) -> dict[str, float]:
    rows = conn.execute("""
        SELECT c.client_id, c.aum, c.cash_pct,
               COALESCE(SUM(CASE WHEN h.asset_class='Cash' THEN h.market_value ELSE 0 END), 0)
        FROM clients c LEFT JOIN holdings h ON c.client_id = h.client_id
        GROUP BY c.client_id, c.aum, c.cash_pct
    """).fetchall()
    for client_id, aum, cash_pct, mmf_value in rows:
        …
```

Target:
```python
def score_cash_drag(
    clients: list[dict],      # [{client_id, aum, cash_pct, …}]
    holdings: list[dict],     # [{client_id, asset_class, market_value, …}]
    config: dict,             # pivot points, weights
) -> dict[str, float]:
    for c in clients:
        cid = c["client_id"]
        aum = c.get("aum", 0)
        cash_pct = c.get("cash_pct", 0)
        mmf_value = sum(
            h["market_value"] for h in holdings
            if h["client_id"] == cid and h.get("asset_class") == "Cash"
        )
        effective_cash_pct = max(cash_pct or 0, (mmf_value / aum * 100) if aum else 0)
        …
```

The business logic (pivot interpolation, weight application, max-of-three for
concentration) is preserved **exactly** — only the input type changes.

### Derived fields (current → target)

Current `_compute_derived_fields(conn)` runs 7 SQL queries inside one function.
Target splits into: one `fetch_*` call + pure-Python computation in a new
file `src/planbot/client_enrichment.py`.

The old `_compute_derived_fields()` in `client_api.py` becomes a thin orchestrator:
fetch data from adapter → call `compute_derived_fields()` → return.

```python
def compute_derived_fields(
    clients: list[dict],
    holdings: list[dict],
    products: list[dict],
    score_config: dict,
) -> dict[str, dict[str, Any]]:
    """Pure function. No I/O. Returns enriched client dicts keyed by client_id."""
    today = date.today()
    product_map = {p["product_id"]: p for p in products}

    enriched: dict[str, dict] = {}
    for c in clients:
        cid = c["client_id"]
        cdata = dict(c)
        # age
        cdata["age"] = _compute_age(c.get("birthdate"), today)
        # has_fund
        cdata["has_fund"] = any(
            product_map.get(h["product_id"], {}).get("product_type") != "money_market_fund"
            for h in holdings if h["client_id"] == cid
        )
        # product_types_in_holdings
        pts = set()
        for h in holdings:
            if h["client_id"] == cid:
                pid = h["product_id"]
                if pid in product_map:
                    pts.add(product_map[pid]["product_type"])
        cdata["product_types_in_holdings"] = sorted(pts)
        cdata["product_families_in_holdings"] = sorted(
            {get_product_family(p) for p in pts}
        )
        # cash_pct_computed
        cdata["cash_pct_computed"] = _compute_cash_pct(c, holdings, cid)
        enriched[cid] = cdata

    # Attach scores from the scorecard engine
    cash_scores = score_cash_drag(clients, holdings, score_config["score_cash_drag"])
    conc_scores = score_concentration_risk(clients, holdings, score_config["score_concentration_risk"])
    …
    for cid in enriched:
        enriched[cid]["cash_score"] = cash_scores.get(cid, 0)
        …

    return enriched
```

## Config-Driven Backend Selection

A single boolean flag in `config_planbot.yaml` switches the entire data backend:

```yaml
# config/config_planbot.yaml
common:
  get_client_product_from_restapi: false  # dev/test: use DuckDB bundled in the Docker image
  # get_client_product_from_restapi: true  # production: connect to bank CRM + custody + product master

data_source:
  duckdb:
    path: data/planbot/db/planbot.duckdb
  rest:
    client_base_url: https://bank-internal/crm/api/v2
    product_base_url: https://bank-internal/product-master/api/v1
    auth_token_env: BANK_API_KEY
    timeout_seconds: 10
    cache_ttl_seconds: 300
```

| Flag value | Backend | Adapter used |
|---|---|---|
| `false` (default) | Internal DuckDB | `DuckDBDataAdapter` — self-contained |
| `true` | Bank REST APIs | `BankRestDataAdapter` — production path |

The file-glob adapter (Phase A legacy) remains a third fallback branch, wired
when neither the DuckDB file nor REST config is present.

## Wiring: Adapter Injected at Startup, Logic Layer Separate

```python
# In data_server.py (Layer 1 — OpenAPI surface)
from src.adapters.data_adapter import build_data_adapters

CONFIG_PATH = Path("config/config_planbot.yaml")
_raw_config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
score_config = _raw_config.get("investor_readiness_score", {})
product_scoring_config = _raw_config.get("product_fitness_score", {})

client_adapter, product_adapter = build_data_adapters(_raw_config)
# Internally: if get_client_product_from_restapi is false → DuckDBDataAdapter
#            if true → BankRestDataAdapter(s)

@app.get("/api/v1/clients/{client_id}")
def get_client(client_id: str):
    # DAL call only — no scorecard logic here
    rows = client_adapter.fetch_clients([client_id])
    if not rows:
        raise HTTPException(404)
    client = rows[0]

    # Enrich via Logic Layer (Python API call)
    holdings = client_adapter.fetch_holdings([client_id])
    products = product_adapter.fetch_products()
    enriched = compute_derived_fields([client], holdings, products, score_config)

    return enriched.get(client_id)
```

```python
# In test (Logic Layer tested independently — no DB)
def test_score_cash_drag_pure():
    clients = [
        {"client_id": "C1", "aum": 1_000_000, "cash_pct": 5.0},
        {"client_id": "C2", "aum": 500_000, "cash_pct": 30.0},
    ]
    holdings = [
        {"client_id": "C1", "asset_class": "Cash", "market_value": 50_000},
        {"client_id": "C2", "asset_class": "Equity", "market_value": 350_000},
    ]
    config = {"weight": 1, "pivot": {"0.0": 10, "0.3": 5, "1.0": 0}}
    scores = score_cash_drag(clients, holdings, config)
    assert scores["C2"] < scores["C1"]  # high cash = lower score
```

## Python API Surface After the Split

After the refactor, `client_api.py` and `product_tool.py` become thin orchestrators
with zero I/O themselves.  They receive data from the adapter, delegate to
pure Logic Layer functions, and return results.  This preserves them as the
documented Python API entry points while keeping scorecard IP in its own modules.

```python
# client_api.py (after refactor)

def search_by_id(adapter: DataAdapter, client_id: str) -> dict | None:
    enriched = _get_enriched_clients(adapter, [client_id])
    return enriched.get(client_id)


def search(adapter: DataAdapter, **criteria) -> list[dict]:
    enriched = _get_enriched_clients(adapter)
    results = [c for c in enriched.values() if _match_criteria(c, criteria)]
    return sorted(results, key=lambda c: c.get("investor_readiness_score", 0), reverse=True)
```

### Maturing holdings search

`search_holdings_maturing()` stays in the Logic Layer.  The DAL fetches raw
holdings + products; the Logic Layer filters by maturity window and product
type.  This keeps the business rule (which product types qualify as "maturing")
outside the adapter where it can be unit-tested.

```python
def search_holdings_maturing(
    holdings: list[dict],
    products: list[dict],
    product_types=None,
    within_days=14,
    as_of_date=None,
) -> list[dict]:
    product_map = {p["product_id"]: p for p in products}
    ref = as_of_date or date.today().isoformat()
    results = []
    for h in holdings:
        p = product_map.get(h["product_id"])
        if not p:
            continue
        pts = product_types or ["bond", "bond_fund"]
        if p.get("product_type") not in pts:
            continue
        maturity = _parse_maturity(p)
        if maturity is None:
            continue
        days = (maturity - date.fromisoformat(ref)).days
        if 0 <= days <= within_days:
            results.append({**h, "days_to_mature": days})
    return sorted(results, key=lambda r: r["days_to_mature"])

def _parse_maturity(product: dict) -> date | None:
    ts = product.get("type_specific", {})
    raw = ts.get("maturity")  # "2026-08-31" or ISO 8601
    if not raw:
        return None
    return date.fromisoformat(str(raw).strip())
```

### Product scoring split — `product_scoring.py` (pure) + `product_tool.py` (thin orchestrator)

The product side mirrors the client side split:

| File | Layer | Contents |
|---|---|---|
| `src/planbot/product_scoring.py` | Logic (pure Python) | `compute_similarity_score()`, `compute_fitness_score()`, `compute_concentration_risk()` — all accept `list[dict]`, no I/O |
| `src/integrations/product_tool.py` | Logic (thin orchestrator) | `search_similar()`, `search_reinvestment_candidates()`, `search_product_by_fitness_score()` — call adapter → delegate to scoring → return |

```python
# product_tool.py (after refactor)

def search_similar(adapter: DataAdapter, query_attrs: dict, *, top_n=10, …) -> list[dict]:
    products = adapter.fetch_products()
    scored = [
        (compute_similarity_score(p, query_attrs, sigmas, weights), p)
        for p in products
        if p["product_id"] not in exclude_ids
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:top_n]]
```

This keeps `product_tool.py` as the documented "Product Python API" entry point.

### Graceful handling of missing data

Cross-system data is eventually consistent.  During a single proposal call the
bank's CRM, custody, and product-master are queried independently.  A holding may
reference a product that was just delisted, or a client may have been archived
between the client and holdings calls.  The Logic Layer must handle these
orphaned rows without crashing.

**Sprint 1 (main refactor):** Tier 1 — idempotent key resolution.  Every
cross-entity lookup uses `.get()` with a fallback, logs a warning, and continues.
The response carries a structured `warnings` list.

```python
# In compute_derived_fields()
product_map = {p["product_id"]: p for p in products}
orphans: list[str] = []
for h in holdings:
    p = product_map.get(h["product_id"])
    if p is None:
        LOGGER.debug("Orphan holding: client=%s product=%s", h["client_id"], h["product_id"])
        orphans.append(h["product_id"])
        continue
    …

return {
    "status": "success",
    "client": enriched_client,
    "warnings": [
        {"code": "ORPHAN_HOLDING", "product_id": pid,
         "message": "Holding references a product not found in the product master. "
                    "Excluded from concentration and exposure calculations."}
        for pid in orphans
    ],
}
```

**Deferred to Sprint 2:** Tiers 2–3 are tabled until orphan rates in production
justify them.

| Tier | Mechanism | Rationale for deferral |
|---|---|---|
| 2 — Single retry after 1.5s | One extra REST call | Only helps transient write-in-flight races. Monitor orphan rate first. |
| 3 — Data-quality caveat in markdown | A few lines of text | Adds value to RM/LLM output. Can be added once Tier 1 warnings are flowing. |

No distributed transactions, no sagas, no two-phase commit.

## File Layout (Target)

```
src/
├── adapters/                       # NEW: DAL implementations
│   ├── __init__.py
│   ├── data_adapter.py             # DataAdapter Protocol + factory
│   ├── duckdb_adapter.py           # DuckDBDataAdapter
│   └── rest_adapter.py             # BankRestDataAdapter
│
├── integrations/
│   ├── client_api.py               # REFACTORED: Logic Layer only (no SQL)
│   ├── product_tool.py             # REFACTORED: Logic Layer only (no SQL)
│   ├── data_server.py              # REFACTORED: wires adapter, delegates to logic
│   ├── proposal_server.py          # (unchanged — already only calls logic)
│   ├── reinvestment_proposal.py    # (unchanged)
│   ├── product_opportunity_proposal.py  # (unchanged)
│   ├── product_investor_matcher.py # (unchanged)
│   └── portfolio_review.py         # (unchanged)
│
├── planbot/
│   ├── client_enrichment.py        # NEW: compute_derived_fields(clients, holdings, products, config) — pure Python
│   ├── investor_readiness_score.py # REFACTORED: accept list[dict], no SQL
│   ├── product_scoring.py          # NEW: compute_similarity_score(), compute_fitness_score(), compute_concentration_risk() — pure Python
│   └── …
│
└── shared/
    └── …
```

## Scope of Changes

| Component | Change | Effort |
|---|---|---|
| New: `src/adapters/` (protocol, factory, DuckDB impl) | Create 3 files | Low |
| `investor_readiness_score.py` 4 score functions | Accept `list[dict]` instead of `conn` | Medium |
| `client_api.py` `_compute_derived_fields()` | Accept `list[dict]` instead of `conn` | Medium |
| `product_tool.py` scoring (similarity, fitness) | Accept `list[dict]` instead of `conn` | Medium |
| `client_api.py` search/get-by-id | Get data from adapter, pass to logic | Low |
| `product_tool.py` search/get-by-id | Get data from adapter, pass to logic | Low |
| `data_server.py` | Wire `build_data_adapters()` at startup | Low |

| Component | Change? | Effort |
|---|---|---|
| FastAPI route handlers (`data_server.py`, `proposal_server.py`) | **Zero** | None |
| OpenAPI contract (`openapi.json`) | **Zero** | None |
| LLM prompts / CrewAI | **Zero** | None |
| All existing tests | **Zero** (run against DuckDB adapter) | None |

## Cost-Saving Tactics

1. **Incremental migration** — Keep DuckDB for products while switching only clients
   to a bank system. Mixed backends are supported per domain.

2. **Response caching in adapter** — Bank APIs are expensive/slow. Add a TTL cache
   in the adapter layer so repeated reads (common in LLM scoring loops) don't
   re-hit upstream.

3. **Shape mapping, not logic changes** — The adapter's only job is "bank data
   shape → our internal dict shape." No business logic in adapters.

4. **DuckDB stays as dev/test fixture** — Run all existing tests against DuckDB.
   Add a few integration tests against bank adapters with canned/mocked responses.

## Implementation Plan

### Sprint 1 — Decouple Logic from SQL (no behaviour change, no `data_server.py` change)

**Objective:** The Proposal Server uses the new DuckDB adapter via Python imports.
`data_server.py` continues serving its existing endpoints unchanged — all calls
to DuckDB remain direct SQL during this sprint.

**Acceptance Criteria:**

| # | Criterion |
|---|---|
| AC1 | `src/adapters/` exists with `DataAdapter` Protocol + `DuckDBDataAdapter` + `build_data_adapters()` factory. |
| AC2 | `score_cash_drag(clients: list[dict], holdings: list[dict], config: dict)` accepts dicts, no `duckdb.DuckDBPyConnection`. Same scores as today. |
| AC3 | `score_concentration_risk(clients, holdings, config)` — same. |
| AC4 | `score_active_manage(clients, holdings, config)` — same. |
| AC5 | `score_life_stage(clients, config)` — same. |
| AC6 | `compute_derived_fields(clients, holdings, products, config)` lives in `src/planbot/client_enrichment.py`. No I/O. Returns same enriched dicts as `_compute_derived_fields(conn)` today. |
| AC7 | `src/planbot/product_scoring.py` exists with `compute_similarity_score()`, `compute_fitness_score()`, `compute_concentration_risk()` — all pure, no I/O. Same scores as today. |
| AC8 | `client_api.py` and `product_tool.py` are thin orchestrators: adapter → pure function → return. No `duckdb` import. No `_get_conn()`, no `_load_score_config()`. Config is loaded once and passed in. |
| AC9 | Config flag renamed from `get_client_product_from_db` to `get_client_product_from_restapi` in `config_planbot.yaml` and all references. |
| AC10 | `search_by_investor_readiness_score()` uses the adapter path. |
| AC11 | `_parse_maturity()` exists as a pure-Python helper. `search_holdings_maturing(holdings, products, …)` is pure Logic Layer. |
| AC12 | `data_server.py` is unchanged — all existing endpoints still work against DuckDB directly. |
| AC13 | Proposal Server (`proposal_server.py`) and all its sub-modules (`reinvestment_proposal.py`, `product_opportunity_proposal.py`, `product_investor_matcher.py`, `portfolio_review.py`) run unchanged. |
| AC14 | All existing tests pass with the DuckDB adapter (same assertions, same data, adapter injected via fixture). |
| AC15 | No `duckdb` or `httpx` import in any Logic Layer file (`client_api.py`, `product_tool.py`, `client_enrichment.py`, `product_scoring.py`, `investor_readiness_score.py` scorecard functions). |

### Sprint 2 — Bank Adapter + `data_server.py` Wiring (scope; refine before start)

**Objective:** Enable the REST backend path.  `data_server.py` gets the adapter
switch.  Bank REST adapter is built and tested.

**Tasks (brief — refine before Sprint 2 planning):**

1. Wire `build_data_adapters()` into `data_server.py` at startup.
2. Add `get_client_product_from_restapi: true` path — swap to `BankRestDataAdapter`.
3. Implement `BankRestDataAdapter` calling `GET /crm/clients`, `GET /custody/holdings`, `GET /product-master/products`.
4. Split the config flag into `get_client_from_restapi` / `get_product_from_restapi` for mixed-backend migration (Issue 9).
5. Add adapter caching — in-memory TTL for REST adapters.
6. Add `@pytest.mark.rest` tests against a mock bank REST server.
7. Tier 2/3 cross-system inconsistency handling (retry + markdown caveat) — monitor orphan rate first.

## What NOT to Do

- **Don't** change the OpenAPI contract — that cascades into LLM prompts,
  CrewAI tools, tests, and docs.
- **Don't** push bank-specific logic into the proposal/LLM layer.
- **Don't** replace DuckDB entirely — keep it as a local dev/test harness.
- **Don't** put scorecard logic in adapters — adapters are pure data pipes.
- **Don't** have data_server.py call `duckdb.connect()` directly — always go
  through the adapter interface.
- **Don't** have the Logic Layer import `duckdb` or `httpx` — it must be
  I/O-free so it's unit-testable with canned dicts.

---

## Testing Strategy

A single integration test suite serves all backends.  The same tests run against
DuckDB in dev and against REST in staging/production — the adapter is selected
by `get_client_product_from_restapi` in config.

```python
# conftest.py
@pytest.fixture(scope="session")
def data_adapters():
    config = yaml.safe_load(Path("config/config_planbot.yaml").read_text())
    return build_data_adapters(config)


# test_client_logic.py
def test_search_by_id_returns_profile(data_adapters):
    client_adapter, product_adapter = data_adapters
    result = search_by_id(client_adapter, product_adapter, "PB-HK-000001-8")
    assert result is not None
    assert result["client_id"] == "PB-HK-000001-8"
    assert "holdings" in result
```

Why one suite instead of unit + integration:

1. **No fake data drift.** Canned `list[dict]` in unit tests rot silently when
   the real DB schema changes.  A single suite against the configured backend
   catches schema mismatches immediately.
2. **Same tests, different backends.** `get_client_product_from_restapi: false`
   → DuckDB.  `true` → REST.  The test code doesn't change.
3. **Fewer files.** Two-tier strategies produce parallel test files that need
   to stay in sync.  One suite avoids that overhead.

What changes in practice:
- `test_client_logic.py` and `test_product_logic.py` gain a `data_adapters` fixture.
- All existing assertions stay; only the data source is injected.
- A `pytest.mark.rest` marker gates REST-specific tests (auth, pagination, caching)
  that are meaningless against DuckDB.

---

## Outstanding Issues — Cross-Review Gaps

The following were identified during a cross-review of this design against the
live codebase.  Each is numbered with a suggested resolution.

### 2. Unify `search_by_id` signature everywhere

**Current:** Python API Surface shows `search_by_id(adapter, client_id)` but
Testing Strategy shows `search_by_id(client_adapter, product_adapter, cid)`.
The real function needs product catalog data (for `product_families_in_holdings`,
`has_fund`), so it needs both adapters.

**Fix:** Standardize on `search_by_id(client_adapter, product_adapter, client_id)`.
Update Python API Surface example to match.

### 7. `search_by_investor_readiness_score()` destination

**Current:** This function calls `run_score_card()` which opens a DB connection
and runs SQL.  Neither the design body nor the migration plan mention it.

**Fix:** After the refactor, `run_score_card()` is replaced by:

```python
def search_by_investor_readiness_score(
    client_adapter, product_adapter, top_n=None
) -> list[dict]:
    clients = client_adapter.fetch_clients()
    holdings = client_adapter.fetch_holdings()
    products = product_adapter.fetch_products()
    enriched = compute_derived_fields(clients, holdings, products, score_config)
    ranked = sorted(enriched.values(),
                    key=lambda c: c.get("investor_readiness_score", 0),
                    reverse=True)
    if top_n:
        ranked = ranked[:top_n]
    return ranked
```

Add this to Phase 2 step 7.

### 8. `data_server.py` handlers change in Sprint 2, not Sprint 1

**Current:** The Scope of Changes table says "FastAPI route handlers — Zero
changes."  This is true for Sprint 1 (Issue 13 defers adapter wiring).

**Fix:** In Sprint 2, every handler must pass the adapter.  Change the Scope
row to: "Zero in Sprint 1; Low in Sprint 2 — inject adapter as first argument
to `client_api`/`product_tool` calls."  The handler logic (response shape,
error handling) stays the same; only the first argument changes.

### 9. "Mixed backends per domain" is not supported by the single boolean flag

**Current:** Cost-Saving Tactic #1 says "Keep DuckDB for products while switching
only clients."  But `get_client_product_from_restapi` is one boolean — it
switches both together.

**Fix:** Either:

- **Option A:** Keep the single boolean and remove the "mixed backends" claim.
  Simpler but less flexible.
- **Option B:** Split the flag into two: `get_client_from_restapi` and
  `get_product_from_restapi`.  This supports migration "client first, products
  later."  Recommended — minimal extra complexity.

Choose Option B and update the config YAML and factory accordingly.

### 10. Phase 2 step #5 wording doesn't match the design

**Current:** Phase 2 says "Refactor `_compute_derived_fields()` to accept
`list[dict]`."  But the design already says it moves to a new file
`src/planbot/client_enrichment.py`.

**Fix:** Rewrite as:
> **Move** `_compute_derived_fields()` from `client_api.py` to
> `src/planbot/client_enrichment.py` as `compute_derived_fields()` —
> a pure function accepting `(clients, holdings, products, config)`.

### 11. `investor_readiness_score.py` dual role — seeder vs scorecard

**Current:** This file contains both seeder/ETL functions (`init_client_db`,
`get_client_db_conn`, `_normalize_holdings_product_ids`) and scorecard
functions (`score_cash_drag`, `score_concentration_risk`, etc.).  The scorecard
functions go pure in Phase 2 but the seeders still need a DB connection.

**Fix:** Do **not** split the file.  Keep seeders and scorecard together.
The seeders import `duckdb` (they operate on the DB file directly, not through
the adapter — correct, since they populate the file).  The scorecard functions
no longer import `duckdb` after Phase 2.  Add a comment in the file:
`# Seeder helpers — use duckdb.  Scorecard functions below are I/O-free.`

### 12. `build_data_adapters()` factory needs the DB path for DuckDB mode

**Current:** The Wiring section shows `client_adapter, product_adapter = build_data_adapters(config)` but doesn't show how the DuckDB path flows in.

**Fix:** The factory reads `config.data_source.duckdb.path`:

```python
def build_data_adapters(config: dict) -> tuple[DataAdapter, DataAdapter]:
    use_rest = config.get("common", {}).get("get_client_product_from_restapi", False)
    if use_rest:
        rest = config.get("data_source", {}).get("rest", {})
        client = BankRestDataAdapter(base_url=rest["client_base_url"], ...)
        product = BankRestDataAdapter(base_url=rest["product_base_url"], ...)
        return client, product
    else:
        db_path = config.get("data_source", {}).get("duckdb", {}).get(
            "path", "data/planbot/db/planbot.duckdb"
        )
        adapter = DuckDBDataAdapter(Path(db_path))
        return adapter, adapter  # same instance for client and product
```

Add this to the Wiring section or the Target Contract section.

### 13. Defer `data_server.py` adapter wiring to Sprint 2

**Current:** `data_server.py` already serves DuckDB-powered endpoints today via
direct calls to `client_api.py` and `product_tool.py`.  The Phase 1 plan says
to wire `build_data_adapters()` into `data_server.py` immediately, which risks
breaking the working OpenAPI surface during the refactor.

**Fix:** Sprint 1 keeps `data_server.py` exactly as-is — no adapter wiring.
The DuckDB adapter is used **only** by the Logic Layer functions internally
during the scorecard refactor.  Sprint 2 adds the config flag and switches
`data_server.py` handlers to use `build_data_adapters()`.

| Sprint | `data_server.py` behavior |
|---|---|
| 1 | Unchanged — calls `client_api.py`/`product_tool.py` directly. DuckDB adapter is wired inside the Logic Layer only. |
| 2 | Wires `build_data_adapters()` at startup. Switches between DuckDB and REST per `get_client_product_from_restapi`. |

This means the OpenAPI surface (`GET /api/v1/clients/{id}`, `POST /api/v1/products/search_similar`, etc.) continues to work throughout Sprint 1 with zero downtime.  Bank REST integration testing can happen in Sprint 2 with the same endpoints, just pointed at a different adapter.
