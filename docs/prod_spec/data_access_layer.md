# Data Access Layer — Multi-Backend Architecture

Status: **Design proposal** — not yet implemented.

## Problem

All client/product APIs in `src/integrations/` currently access a single DuckDB file
(`data/planbot/db/planbot.duckdb`) via hardcoded `duckdb.connect()` calls.
To deploy in a bank environment, these APIs must retrieve data from bank-internal
systems (CRM, custody, product master, etc.) instead.

The APIs also embed significant **business logic** (scorecards, similarity scoring,
fitness scoring). This IP must be preserved — only the raw data retrieval layer
should be replaced.

## Current State

```
FastAPI Endpoints  (data_server.py, proposal_server.py)
      │
      ▼
client_api.py  /  product_tool.py
      │
      ├── Raw SQL (SELECT FROM clients/holdings/products)
      └── Embedded scorecard logic (investor_readiness_score.py, similarity, fitness)
      │
      ▼
duckdb.connect("data/planbot/db/planbot.duckdb")
```

The APIs are tightly coupled: scorecard functions accept `duckdb.DuckDBPyConnection`
and run SQL inline.

## Target Architecture

```
┌──────────────────────────────────────────────────────┐
│  FastAPI Endpoints  (ZERO changes)                  │
├──────────────────────────────────────────────────────┤
│  API Response Assembly  (thin, stays)               │
│  — Calls scorecard + formats OpenAPI response shapes│
├──────────────────────────────────────────────────────┤
│  ★ SCORECARD ENGINE  (our IP, stays)  ★            │
│  — investor_readiness_score.py                      │
│    • score_cash_drag()                              │
│    • score_concentration_risk()                     │
│    • score_active_manage()                          │
│    • score_life_stage()                             │
│    • compute_total_scores()                         │
│  — product_tool.py scoring functions                │
│    • _compute_similarity_score()                    │
│    • _compute_hypothetical_concentration_risk()     │
│    • search_product_by_fitness_score()              │
│  — client_api.py derived fields                     │
│    • _compute_derived_fields()  (age, has_fund,     │
│      product_families, cash_pct_computed)           │
│                                                     │
│  All operate on plain dicts:                        │
│    clients  = [{client_id, name, aum, birthdate…}]  │
│    holdings = [{client_id, product_id, mv, …}]      │
│    products = [{product_id, type, rr, …}]           │
├──────────────────────────────────────────────────────┤
│  ◄── DataSource Interface  (NEW, swappable)  ──►    │
│                                                     │
│  fetch_clients(client_ids?)  → list[dict]           │
│  fetch_holdings(client_ids?) → list[dict]           │
│  fetch_products(product_ids?) → list[dict]          │
│                                                     │
│       ╱                      ╲                       │
│  DuckDBAdapter          BankAPIAdapter              │
│  (today)                (future, per bank)          │
│  SELECT * FROM clients  GET /crm/clients            │
│  SELECT * FROM holdings GET /custody/holdings       │
│                          GET /product-master/products│
└──────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. DataSource is purely data retrieval

The interface has **three methods only**. No business logic, no filtering,
no enrichment — just raw rows as dicts.

```python
class DataSource(Protocol):
    """Raw data provider. Returns plain dicts. No business logic."""

    def fetch_clients(self, client_ids: list[str] | None = None) -> list[dict]: ...
    def fetch_holdings(self, client_ids: list[str] | None = None) -> list[dict]: ...
    def fetch_products(self, product_ids: list[str] | None = None) -> list[dict]: ...
```

### 2. Scorecard engine accepts dicts, not DB connections

Current:

```python
def score_cash_drag(conn: duckdb.DuckDBPyConnection, config: dict) -> dict[str, float]:
    rows = conn.execute("SELECT ... FROM clients c LEFT JOIN holdings h ...")
```

Target:

```python
def score_cash_drag(
    clients: list[dict],
    holdings: list[dict],
    config: dict,
) -> dict[str, float]:
    # Same pivot interpolation, same weights, same output
```

The business logic (pivot interpolation, weight application, max-of-three for
concentration) is preserved exactly.

### 3. Config-driven backend selection

```yaml
# config/config_planbot.yaml
data_source:
  client:
    backend: duckdb          # or "core_banking_api", "crm_api"
    duckdb:
      path: data/planbot/db/planbot.duckdb
    core_banking_api:
      base_url: https://bank-internal/api/v2
      auth: ${BANK_API_KEY}
      timeout_seconds: 10
      cache_ttl_seconds: 300

  product:
    backend: duckdb
    # ... same pattern
```

Mixed backends are supported — e.g., clients from a CRM API while products stay
in DuckDB during migration.

### 4. Factory wires it up at startup

```python
# In data_server.py
from src.integrations.data_source import build_data_source

client_ds = build_data_source("client", config)
product_ds = build_data_source("product", config)

# Endpoints call client_ds.fetch_clients(...) instead of duckdb.connect()
```

## Scope of Changes

| Component | Change | Effort |
|---|---|---|
| `investor_readiness_score.py` | Refactor 4 score functions: accept `list[dict]` instead of `duckdb.DuckDBPyConnection` | Medium |
| `client_api.py` `_compute_derived_fields()` | Refactor: accept `list[dict]` instead of `duckdb.DuckDBPyConnection` | Medium |
| `product_tool.py` scoring functions | Refactor similarity/fitness scoring: accept `list[dict]` | Medium |
| `client_api.py` search/get-by-id | Get data from DataSource, pass to scorecard engine | Low |
| `product_tool.py` search/get-by-id | Get data from DataSource, pass to scoring functions | Low |
| New: `DataSource` protocol + `DuckDBAdapter` | One new file | Low |
| New: `BankAPIAdapter` | One new file per bank system | Low |

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

### Phase 1: Protocol + DuckDB Adapter (no behavior change)

1. Create `src/integrations/data_source.py` with the `DataSource` protocol
2. Create `DuckDBDataSource` class that wraps existing SQL queries
3. Update `data_server.py` to use `build_data_source()` factory
4. Verify all existing tests pass

### Phase 2: Decouple Scorecard from SQL (no behavior change)

1. Refactor `score_cash_drag()` to accept `list[dict]`
2. Refactor `score_concentration_risk()` to accept `list[dict]`
3. Refactor `score_active_manage()` to accept `list[dict]`
4. Refactor `score_life_stage()` to accept `list[dict]`
5. Refactor `_compute_derived_fields()` to accept `list[dict]`
6. Refactor product_tool scoring to accept `list[dict]`
7. Verify all existing tests pass after each refactor

### Phase 3: Bank Adapter (one per bank system)

1. Implement `CoreBankingAdapter` for the first bank integration
2. Add bank-specific config section
3. Integration tests against bank sandbox

## File Layout (target)

```
src/integrations/
├── data_source.py              # NEW: DataSource protocol + factory
│   ├── DataSource              # Protocol class
│   ├── DuckDBDataSource        # Wraps existing duckdb.connect()
│   └── build_data_source()     # Factory from config
├── adapters/                   # NEW: bank-specific adapters
│   └── core_banking_adapter.py # Example: REST client to bank CRM
├── client_api.py               # MODIFIED: uses DataSource, delegates to scorecard
├── product_tool.py             # MODIFIED: uses DataSource, delegates to scoring
├── data_server.py              # MODIFIED: wires DataSource at startup
├── proposal_server.py          # (unchanged)
├── reinvestment_proposal.py    # (unchanged)
└── ...
```

## What NOT to Do

- **Don't** change the OpenAPI contract — that cascades into LLM prompts,
  CrewAI tools, tests, and docs.
- **Don't** push bank-specific logic into the proposal/LLM layer.
- **Don't** replace DuckDB entirely — keep it as a local dev/test harness.
- **Don't** put scorecard logic in adapters — adapters are pure data pipes.
