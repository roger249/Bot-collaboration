# Bank Data API — Implementation Contract

**Audience:** the bank's engineering team implementing a data server that serves
raw client, holding, and product data for PlanBot to consume.

**Version:** 0.1.0 (draft for hand-off)

**Machine-readable source of truth:** `docs/specification/data_api/openapi_data.json`
(this file is generated from the reference implementation; the prose below is the
human-readable companion).

---

## 1. Purpose

The bank exposes a **read-only data API** with three resources:

| Resource | Description |
|---|---|
| `clients` | Client master records (one row per client). |
| `holdings` | Positions held by clients (one row per position). |
| `products` | Investable-product master (one row per product). |

All business logic (scoring, similarity ranking, maturity detection, fitness)
is performed **by PlanBot**, not by this API. This API is a pure data pipe —
no derived fields, no ranking, no scoring.

Relationships:

- `holdings.client_id` references `clients.client_id`.
- `holdings.product_id` references `products.product_id` (may be absent for
  instruments not in the product master).

---

## 2. Conventions

### 2.1 Base URL and versioning

- Base path: `/api/v1`
- All endpoints are `GET`. No authentication is assumed in this draft contract;
  the bank may add auth headers without changing the response shapes.

### 2.2 Comma-separated list filters

The list endpoints accept an optional `client_id` / `product_id` query parameter
that is a **comma-separated** list of identifiers:

```
GET /api/v1/clients?client_id=PB-HK-000007-5,PB-HK-000002-6
```

- Omit the parameter to return **all** rows.
- Whitespace around each item is trimmed.
- An empty value is treated the same as omitting the parameter.

### 2.3 Pagination and ordering

List endpoints support `offset` and `limit`:

| Param | Type | Default | Meaning |
|---|---|---|---|
| `offset` | int (≥ 0) | `0` | Number of rows to skip (0-based). |
| `limit` | int (≥ 1) | none | Maximum rows to return. Omit for all. |

**Ordering:** results MUST be returned in a deterministic order so that
`offset`/`limit` pagination is repeatable. A conforming implementation sorts
list results by its natural key:

- `clients` → ascending `client_id`
- `holdings` → ascending `client_id`, then `holding_idx`
- `products` → ascending `product_id`

### 2.4 Error semantics

| Situation | Response |
|---|---|
| Resource exists | `200` with the row(s). |
| List matches nothing | `200` with `[]` (empty array) — **not** an error. |
| Single `/{id}` lookup not found | `404` with body `{"detail": "Client not found: <id>"}` (or "Product not found"). |
| Malformed query (bad types, out-of-range) | `422` with a validation-error body (bank may use its own shape). |

**Important:** the difference between "list returns empty" and "single lookup
misses" is intentional — empty lists are a valid success path; a missing
single resource is an error.

### 2.5 Data types and nullability

- All monetary values are numeric (`number`) in the row's stated currency.
- `%` values are plain numbers (e.g. `42.8`, not `0.428`).
- Numeric values are serialized rounded to **4 decimal places**.
- Fields marked **nullable** may be `null` in a row. Fields marked **required**
  are always present.
- `risk_rating` is an integer 1 (low) – 5 (high).

---

## 3. Resource schemas

### 3.1 `clients`

| Field | Type | Required | Description |
|---|---|---|---|
| `client_id` | string | ✅ | Unique client identifier. |
| `name` | string | ✅ | Client full name. |
| `aum` | number | no | Assets under management (USD). |
| `cash_pct` | number | no | Reported cash percentage of AUM. |
| `region` | string | no | Client region. |
| `birthdate` | string | no | Date of birth, `YYYY-MM-DD`. |
| `occupation` | string | no | Occupation. |
| `risk_rating` | integer | no | Risk tolerance 1 (low) – 5 (high). |
| `marital_status` | string | no | Marital status. |
| `children_info` | string | no | Free-text children information. |
| `liquidity_need` | string | no | Liquidity need (e.g. "Low"). |
| `income_stability` | string | no | Income stability description. |
| `investment_objective` | string | no | Stated investment objective. |
| `qualitative_profile` | string | no | Free-text RM notes for suitability analysis. |

> **Schema note:** `qualitative_profile` is a **required part of the contract**
> even though it is absent from the reference implementation's `CREATE TABLE`
> definition (it was added later via `ALTER TABLE`). The bank's data layer must
> include this column. Treat the field tables in this document — not the
> reference seeder DDL — as authoritative for the API contract.

### 3.2 `holdings`

| Field | Type | Required | Description |
|---|---|---|---|
| `client_id` | string | ✅ | Owner client identifier. |
| `holding_idx` | integer | ✅ | Zero-based position index within the client. |
| `holding_id` | string | no | Unique holding identifier. |
| `product_id` | string | no | Instrument/product identifier (→ `products.product_id`). |
| `instrument_name` | string | no | Display name of the instrument. |
| `symbol` | string | no | Ticker/symbol. |
| `asset_class` | string | no | Asset class (see §4). |
| `region` | string | no | Issuer/market region. |
| `currency` | string | no | ISO currency code of the position. |
| `quantity` | number | no | Quantity held. |
| `book_cost` | number | no | Book cost. |
| `market_value` | number | no | Current market value in the holding currency. |
| `unrealized_pl` | number | no | Unrealized profit/loss. |
| `unrealized_pl_pct` | number | no | Unrealized P/L as a percentage. |
| `yield_pct` | number | no | Yield percentage. |
| `risk_bucket` | string | no | Risk bucket (see §4). |
| `esg_score` | string | no | ESG score; `null` when no coverage (note: it is a **string**). |
| `liquidity` | string | no | Settlement liquidity (e.g. "T+2"). |

### 3.3 `products`

| Field | Type | Required | Description |
|---|---|---|---|
| `product_id` | string | ✅ | Unique product identifier. |
| `isin` | string | no | ISIN; `null` for products without one. |
| `name` | string | ✅ | Product name. |
| `ticker` | string | no | Ticker. |
| `trading_currency` | string | no | Trading currency. |
| `risk_rating` | integer | ✅ | Risk rating 1 (low) – 5 (high). |
| `expected_return` | number | no | Expected annual return (%). |
| `region` | string | no | Region. |
| `country` | string | no | Country. |
| `sector` | string | no | Sector. |
| `remarks` | string | no | Free-text remarks. |
| `product_type` | string | ✅ | Product type (see §4). |
| `vehicle` | string | no | Vehicle (see §4). |
| `type_specific` | object | no | Product-type-specific attributes (see §3.3.1). |
| `performance_history` | object | no | Historical metrics keyed by period (see §3.3.2). |
| `investment_note` | string | no | House-view narrative. |

#### 3.3.1 `type_specific` (keys vary by `product_type`)

The keys of this object depend on the product type. The reference
implementation emits the following key sets (all values are JSON scalars or
`null`):

| `product_type` | `type_specific` keys |
|---|---|
| `bond` | `issuer_name`, `issuer_sector`, `issuer_country`, `coupon_type`, `coupon_rate`, `coupon_frequency`, `day_count_convention`, `credit_rating`, `maturity`, `seniority`, `callable`, `puttable`, `convertible`, `green_bond`, `sukuk` |
| `bond_fund` | `provider`, `nav`, `expense_ratio`, `share_class`, `strategy_summary`, `dividend_frequency`, `aum`, `strategy`, `theme`, `domicile`, `rebalancing_frequency`, `dividend_treatment`, `ytm`, `yield_to_worst`, `effective_duration`, `option_adjusted_spread`, `weighted_average_duration`, `weighted_average_coupon` |
| `equity_fund` | `provider`, `nav`, `aum`, `dividend_frequency`, `dividend_treatment`, `domicile`, `replication_method`, `strategy_summary`, `ter` |
| `stock` | `company_name`, `exchange`, `industry`, `market_cap`, `lot_size`, `dividend_yield`, `dividend_paying` |
| `money_market_fund` | `nav`, `maturity_profile`, `credit_quality`, `dividend_treatment`, `yield_type` |
| `balanced_fund` | `provider`, `nav`, `strategy_summary`, `equity_exposure`, `fixed_income_exposure`, `cash_exposure`, `alternative_exposure`, `investment_style`, `risk_profile`, `dividend_treatment` |
| `currency` | *(none — empty object `{}`)* |

**Contract note:** the bank is not required to reproduce these exact key sets.
Treat them as indicative of the kind of per-type metadata PlanBot consumes;
the only hard requirement is that `type_specific` be a JSON object whose keys
vary by `product_type`.

#### 3.3.2 `performance_history` (period → metrics)

A JSON object keyed by period, with each value an object of metrics:

Periods: `6m`, `1y`, `3y`, `5y`, `10y`.

Metrics (each a `number` or `null`):

| Metric | Meaning |
|---|---|
| `return` | Cumulative return over the period (%). |
| `cagr` | Compound annual growth rate (%). |
| `max_drawdown` | Maximum drawdown (%). |
| `volatility` | Annualized volatility (%). |
| `calmar_ratio` | Calmar ratio (nullable). |
| `downside_risk` | Downside deviation (%). |

A product with no history has `performance_history: {}` (empty object).

---

## 4. Value domains

Where a field is effectively an enum in the reference data, the observed
values are:

| Field | Observed values |
|---|---|
| `clients.region` | `APAC`, `Europe`, `LatAm`, `North America` |
| `holdings.asset_class` | `Cash`, `Equities`, `Fixed Income`, `Alternatives` |
| `holdings.risk_bucket` | `Low`, `Medium`, `High` |
| `holdings.currency` | `USD`, `HKD` |
| `products.product_type` | `bond`, `bond_fund`, `equity_fund`, `stock`, `money_market_fund`, `balanced_fund`, `currency` |
| `products.vehicle` | `Direct`, `ETF`, `Mutual Fund` |

These are the values in the reference dataset, **not** a closed enum contract —
the bank may add regions, currencies, product types, etc., and PlanBot treats
these fields as free strings.

---

## 5. Endpoint reference

> **On identifiers in this section:** the concrete `client_id` / `product_id`
> values used here are PlanBot's **synthetic test data** (`PB-HK-…`, `PROD053`,
> `ETF-HYG`, …). They are illustrative only. The bank serves its **own** real
> identifiers; only the field shapes and semantics are contractual.

### 5.1 `GET /api/v1/clients`

List raw client rows.

| Param | Type | Default | Description |
|---|---|---|---|
| `client_id` | string (comma-separated) | none | Filter by one or more client IDs. |
| `offset` | int | `0` | Rows to skip. |
| `limit` | int | none | Max rows to return. |

Returns `200` with `array<clients>` (empty array if no matches).

### 5.2 `GET /api/v1/clients/{client_id}`

Return a single raw client row. `404` if not found.

### 5.3 `GET /api/v1/holdings`

List raw holding rows.

| Param | Type | Default | Description |
|---|---|---|---|
| `client_id` | string (comma-separated) | none | Filter by one or more client IDs. |
| `offset` | int | `0` | Rows to skip. |
| `limit` | int | none | Max rows to return. |

Returns `200` with `array<holdings>`.

### 5.4 `GET /api/v1/products`

List raw product rows.

| Param | Type | Default | Description |
|---|---|---|---|
| `product_id` | string (comma-separated) | none | Filter by one or more product IDs. |
| `offset` | int | `0` | Rows to skip. |
| `limit` | int | none | Max rows to return. |

Returns `200` with `array<products>`.

### 5.5 `GET /api/v1/products/{product_id}`

Return a single raw product row. `404` if not found.

### 5.6 `GET /health` (recommended)

A liveness probe for load balancers and monitoring. Returns `200` with a body
indicating the service is up, e.g.:

```json
{ "status": "ok" }
```

This endpoint is outside the data contract; it has no required shape beyond a
`200` when healthy.

---

## 6. Worked examples

> The identifiers in these examples are PlanBot's synthetic test data and are
> illustrative only — the bank serves its own real identifiers.

### 6.1 List two clients

```
GET /api/v1/clients?client_id=PB-HK-000007-5,PB-HK-000002-6
```

```json
[
  {
    "client_id": "PB-HK-000007-5",
    "name": "Akira Tanaka",
    "aum": 28000000.0,
    "cash_pct": 12.0,
    "region": "APAC",
    "birthdate": "1980-01-01",
    "occupation": "Real Estate Developer",
    "risk_rating": 4,
    "marital_status": "Single",
    "children_info": "2 children",
    "liquidity_need": "Low",
    "income_stability": "Stable salaried income",
    "investment_objective": "Long-term capital growth",
    "qualitative_profile": "Self-made real estate developer with entrepreneurial mindset."
  }
]
```

### 6.2 One holding

```
GET /api/v1/holdings?client_id=PB-HK-000007-5&limit=1
```

```json
[
  {
    "client_id": "PB-HK-000007-5",
    "holding_idx": 0,
    "holding_id": "ph-6-us1mt-rr-0",
    "product_id": "PROD053",
    "instrument_name": "US 1-Month Treasury Bill Rate",
    "symbol": "US1MT=RR",
    "asset_class": "Cash",
    "region": "North America",
    "currency": "USD",
    "quantity": 153494.7465,
    "book_cost": 2352941.1765,
    "market_value": 3360000.0,
    "unrealized_pl": 1007058.8235,
    "unrealized_pl_pct": 42.8,
    "yield_pct": 15.7,
    "risk_bucket": "Low",
    "esg_score": null,
    "liquidity": "T+2"
  }
]
```

### 6.3 One product (bond)

```
GET /api/v1/products/PROD053
```

```json
{
  "product_id": "PROD053",
  "isin": null,
  "name": "US Treasury 4.375% 31Aug26",
  "ticker": "XHLF",
  "trading_currency": "USD",
  "risk_rating": 1,
  "expected_return": 3.7,
  "region": "US",
  "country": null,
  "sector": "Government",
  "remarks": "Bridge row for holdings product_id=PROD053.",
  "product_type": "bond",
  "vehicle": "Direct",
  "type_specific": {
    "issuer_name": "U.S. Treasury",
    "issuer_sector": "government",
    "coupon_type": "fixed",
    "coupon_rate": 0.04375,
    "coupon_frequency": "semi-annual",
    "credit_rating": "AA+",
    "maturity": "2026-08-31",
    "seniority": "senior",
    "callable": false
  },
  "performance_history": {
    "1y": { "return": 3.65, "cagr": 3.72, "max_drawdown": 0.0, "volatility": 0.2 },
    "3y": { "return": 14.22, "cagr": 4.53, "max_drawdown": -0.03, "volatility": 0.28 }
  },
  "investment_note": "Individual bonds allow precise maturity-matching for liability-driven investing."
}
```

### 6.4 Missing single resource

```
GET /api/v1/clients/PB-HK-NONEXIST
```

```json
{ "detail": "Client not found: PB-HK-NONEXIST" }
```

HTTP status `404`.

---

## 7. Acceptance checklist

A conforming implementation satisfies all of the following:

- [ ] Exposes the five `GET` endpoints under `/api/v1`.
- [ ] List endpoints support comma-separated `client_id` / `product_id` filtering and `offset` / `limit` pagination.
- [ ] List endpoints return deterministic results ordered by their natural key (§2.3).
- [ ] List endpoints return `200` + `[]` on no matches (never `404`).
- [ ] Single `/{id}` endpoints return `404` with a `{"detail": ...}` body when the ID is absent.
- [ ] Client rows carry the 14 fields in §3.1; holding rows the 18 fields in §3.2; product rows the 16 fields in §3.3.
- [ ] Nullable fields are `null` when absent (not empty string / omitted).
- [ ] `risk_rating` is an integer 1–5; `esg_score` is a string or `null`.
- [ ] `type_specific` and `performance_history` are JSON objects (not stringified JSON).
