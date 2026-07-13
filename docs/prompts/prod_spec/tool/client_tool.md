Client Integration Layer
========================

The planbot will be invoked by the main module for investment suggestion.

All client and product information will be stored outside of Planbot and planning be accessed via API.

Planbot also expose an API for various investment proposal.

Before the main module ready, a mock will be built.  This includes below.

- Spec out the new engine using score card approach, including 
  - a investor readiness score to extract investor ready to buy new product for further analysis
  - a product fitness score to match investor and products
- Move the current test data from csv, md, into DuckDB
- Enrich the test data
- Python method to built from this DuckDB
- FastAPI on top of the Python method
- The python method also be the base to build a tool for later interaction with LLM.

This document focus on client data migration & the python method.

All python API will be wrapped by Fast API in next stage to be invoked by the main module

## Single DuckDB Design

All data — clients, profiles, holdings, and the product catalog — live in **one DuckDB file**:

```
data/planbot/db/planbot.duckdb
```

| Table | Purpose | Loaded by |
|---|---|---|
| `clients` | Client master (id, name, aum, region) | `investor_readiness_score.py` |
| `profiles` | Demographics (birthdate, occupation, risk_rating) | `investor_readiness_score.py` |
| `holdings` | Normalised positions per client (FK → `products.product_id`) | `investor_readiness_score.py` |
| `products` | Product catalog (122 products, FK target for holdings) | `product_catalog_seed.py` |

**Rationale for a single file:**

- Zero‑config JOINs: `holdings JOIN products USING (product_id)` works without `ATTACH DATABASE`
- Referential integrity: FK constraints are enforceable within one DB
- Simple deployment: one file to ship, backup, or replicate
- Non‑overlapping table names mean the product catalog seeder and client loader can target the same file safely

The **product catalog seeder** (`src/test_data/product_catalog_seed.py`) must use `CREATE TABLE IF NOT EXISTS` + `INSERT OR REPLACE` rather than `DROP TABLE`, so that client data is never wiped during a catalog refresh.

# Client API

The following API will be provided to retrieve client data.  Data are transported using JSON format.

### 1. `search_by_id`

Returns the full client profile including nested holdings.

```
search_by_id(client_id: str) → ClientProfile
```

### 2. `search` (by criteria)

Filter clients by demographic and portfolio attributes.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `risk_rating` | `int` or `[int, int]` | **yes** | 1‑5, or range e.g. `[3,5]` |
| `age` | `int` or `[int, int]` | no | Age or age range |
| `product_types_in_holdings` | `str` or `[str]` | no | e.g. `"equity"`, `["bond","balanced"]` |
| `concentration_score` | `float` or `[float, float]` | no | 0‑10 score or range |
| `cash_score` | `float` or `[float, float]` | no | 0‑10 score or range |

Numeric parameters accept a single value (exact match) or a `[min, max]` range.  String/enum parameters accept a single value or a list for OR matching.  When an optional parameter is omitted, it is not used as a filter.

```
search(**criteria) → list[ClientProfile]
```

### 3. `search_holdings_maturing`

Find clients with bonds or fixed‑income products maturing within a given window.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `product_types` | `[str]` | no | e.g. `["bond"]` — match product catalog `product_type`.  If omitted, all FI types are included. |
| `within_days` | `int` | no | Calendar days to maturity.  Default 14. |
| `as_of_date` | `str` (ISO 8601) | no | Reference date for computing days‑to‑maturity.  Defaults to system date. |

```
search_holdings_maturing(product_types=["bond"], within_days=14) → [
  {client_id, product_id, notional, days_to_mature}
]
```

### 4. `search_by_investor_readiness_score`

Return clients ranked by their investor readiness score.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `top_n` | `int` | no | Number of top results to return.  Default returns all. |

A prototype of the score card is implemented in `src/planbot/investor_readiness_score.py`.  Will refactor this to the API.

```
search_by_investor_readiness_score(top_n=10) → list[{rank, client_id, name, total_score, …}]
```


# Schema

All field names use **snake_case** in the API.  The DuckDB schema mirrors this naming.

## Stored fields

| API Field | Source | Type | Description |
|-----------|--------|------|-------------|
| `client_id` | `client_list.csv` → `client/id` | `string` | PB‑HK‑… unique identifier |
| `name` | `client_list.csv` → `client/name` | `string` | Full display name |
| `birthdate` | `client_profile.csv` → `Birthdate` | `string` (ISO 8601) | `YYYY‑MM‑DD`, or `"N/A"` for corporate entities |
| `occupation` | `client_profile.csv` → `Occupation` | `string` | e.g. `"Retired"`, `"CFO"`, `"Corporate Entity"` |
| `risk_rating` | `client_profile.csv` → `Risk Rating` | `integer` (1‑5) | 1 = conservative, 5 = aggressive |
| `marital_status` | `client_profile.csv` → `Marital Status` | `string` | `"Single"`, `"Married"`, `"Divorced"` |
| `children_info` | `client_profile.csv` → `Children Info` | `string` | e.g. `"2 children"`, `"0 children"` |
| `annual_income` | enriched data (planned) | `float` | Annual gross income in base currency |
| `net_worth` | enriched data (planned) | `float` | Total net worth excluding primary residence |
| `aum` | `client_list.csv` → `client/aum` | `float` | Total portfolio value |
| `region` | `client_list.csv` → `client/region` | `string` | Primary geographic region |

### Fields to deprecate

These columns exist in the source CSV but will be removed from the API once goal‑based needs are implemented:

| Field | Source | Replacement |
|---|---|---|
| `investment_objective` | `client_profile.csv` → `Investment Objective` | Move to `needs` section |
| `liquidity_need` | `client_profile.csv` → `Liquidity Need` | Move to `needs` section |

## Derived fields (computed, not stored)

| Field | Computation | Type |
|-------|------------|------|
| `age` | `today - birthdate` | `integer` |
| `has_fund` | `holdings` JOIN `products` — any row where `product_type ≠ 'money_market_fund'` | `boolean` |
| `cash_pct` | `max( client_cash_pct_raw, Σ holdings_cash_mv / aum × 100 )` — see Cash Drag dimension | `float` (0‑100) |
| `cash_score` | Linear‑interpolated from `cash_pct / 100` vs pivot table | `float` (0‑10) |
| `concentration_score` | Max of single‑holding / region / asset‑class exposure, each linearly interpolated | `float` (0‑10) |
| `product_types_in_holdings` | `SELECT DISTINCT p.product_type FROM holdings h JOIN products p …` (see below) | `[str]` |
| `investor_readiness_score` | Weighted sum of 4 dimensions (see Score Card spec) | `float` |


### `product_types_in_holdings` lookup

Derived by joining `holdings.product_id` against the product catalog:

```sql
SELECT DISTINCT p.product_type
FROM holdings h
JOIN products p ON h.product_id = p.product_id
WHERE h.client_id = ?
```

Both tables live in the same DuckDB file (`data/planbot/db/planbot.duckdb`), so the JOIN requires no extra configuration.

The product catalog defines these `product_type` values:

| `product_type` | Category (for filter API) |
|---|---|
| `bond` | bond |
| `bond_fund` | bond |
| `equity_fund` | equity |
| `stock` | equity |
| `money_market_fund` | cash |
| `balanced_fund` | balanced |

The filter API parameter `product_types_in_holdings` accepts the **category** values (`bond`, `equity`, `cash`, `balanced`) and maps them to the underlying `product_type` values.

The product catalog schema is defined in `src/test_data/product_catalog.md`.

---

# Holdings Schema

Client holdings are stored in the source CSV (`client_list.csv`) in **wide format** — each client row carries up to 10 nested holdings as `holdings/0/id`, `holdings/0/marketValue`, … `holdings/9/…`.  This is denormalised for batch export but is unsuitable for querying.

The API **normalises holdings into a separate table** in the shared DuckDB (`data/planbot/db/planbot.duckdb`):

```sql
CREATE TABLE holdings (
    client_id         TEXT NOT NULL,
    holding_idx       INTEGER NOT NULL,     -- 0‑based position in client's portfolio
    holding_id        TEXT,
    product_id        TEXT,                 -- FK → products.product_id
    instrument_name   TEXT,
    symbol            TEXT,
    asset_class       TEXT,                 -- "Cash" / "Equities" / "Fixed Income"
    region            TEXT,
    currency          TEXT,
    quantity          DOUBLE,
    book_cost         DOUBLE,
    market_value      DOUBLE,
    unrealized_pl     DOUBLE,
    unrealized_pl_pct DOUBLE,
    yield_pct         DOUBLE,
    risk_bucket       TEXT,
    esg_score         TEXT,
    liquidity         TEXT,
    PRIMARY KEY (client_id, holding_idx)
);
```

> **Maturity dates** for bond products are stored in `products.type_specific` JSON as `$.maturity`.  The 12 bond products (`PROD003`, `PROD007`, `PROD011`, `PROD044`‑`PROD052`) carry ISO 8601 maturity dates in `otc_products.md`.  `search_holdings_maturing` joins holdings to products and extracts `json_extract_string(p.type_specific, '$.maturity')` — no separate column is needed on the holdings table.

### Why normalise?

| Approach | Pros | Cons |
|---|---|---|
| **Wide CSV** (current) | Single-file export, easy for Excel | Fixed 10‑holding cap; no JOINs; hard to aggregate across clients |
| **Normalised table** (DuckDB) | Unlimited holdings; JOIN to product catalog; aggregation (SUM, MAX, COUNT); filter by `asset_class`, `region`; maturity via `products.type_specific` JOIN | Requires ETL step (already done by `investor_readiness_score.py`) |

### API response shape

Holdings are returned nested under each client in `search_by_id` and `search` responses:

```json
{
  "client_id": "PB-HK-000003-4",
  "name": "James Harrison",
  "holdings": [
    {
      "holding_idx": 0,
      "holding_id": "ph-1-shv-o-0",
      "product_id": "shv-o",
      "instrument_name": "iShares Short Treasury Bond ETF",
      "symbol": "SHV.O",
      "asset_class": "Cash",
      "region": "North America",
      "currency": "USD",
      "quantity": 5891.95,
      "book_cost": 645481.63,
      "market_value": 650000.00,
      "unrealized_pl": 4518.37,
      "unrealized_pl_pct": 0.7,
      "yield_pct": 4.0,
      "risk_bucket": "Low",
      "liquidity": "T+2"
    }
  ]
}
```

### Holdings‑specific filter API (planned)

```
GET /api/v1/clients/{client_id}/holdings
GET /api/v1/clients/{client_id}/holdings?asset_class=Equities
GET /api/v1/clients/{client_id}/holdings?matured_within_days=14
GET /api/v1/clients/holdings/search?product_types=bond&within_days=14
```

The `?matured_within_days=N` filter joins holdings to products and extracts `json_extract_string(p.type_specific, '$.maturity')`.

---

# Acceptance criteria

- Migrate all duckDB into a single files
- Update all duckDB content from current CSV, md
- Implement the python method for the client API
- Unit tests has been built and passed for all above tasks.

Once above are done, we will work on 

- product tool including product fitness score
- revamp the reinvestment/product fitness reports to use these API

# Roadmap / Known Gaps

| Item | Status | Notes |
|------|--------|-------|
| `maturity` enrichment | ✅ Done | `otc_products.md` Bond table now has ISO 8601 `maturity` column; seeder stores as `$.maturity` in `products.type_specific` JSON |
| `annual_income`, `net_worth` | 🔜 Planned | Requires enriched data source |
| FastAPI endpoints | 🔜 Planned | See API sections above |
| Goal‑based `needs` schema | 🔜 Planned | Replace `investment_objective` and `liquidity_need` |
| `has_fund` precision | ✅ Done | Now uses product catalog JOIN instead of `asset_class ≠ "Cash"` |
| `product_id` key alignment | ⚠️ Verify | Confirm CSV `productId` values match `products.product_id` keys |
| LLM tool interface | 🔮 Future | Python method doubles as LLM tool base (line 19) |
| `config_planbot.yaml` client_api section | 🔜 Planned | `income_stability_mapping`, `product_type` category mapping |