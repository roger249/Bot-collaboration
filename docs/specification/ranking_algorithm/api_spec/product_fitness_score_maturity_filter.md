# Near-Maturity Exclusion Filter (product search endpoints)

> **Status**: SPECIFICATION (finalized — awaiting implementation authorization)
> **Endpoints**:
> - `POST /api/v1/products/fitness-score`
> - `POST /api/v1/products/search-similar`
> - `POST /api/v1/products/reinvestment-candidates`
> **Logic Layer**: `search_product_by_fitness_score()`, `search_similar()`, and
> `search_reinvestment_candidates()` in `src/integrations/product_tool.py`

## 1. Objective

When searching / scoring candidate products for a client, exclude any product
that will mature within the near-maturity window, so the LLM / relationship
manager never recommends a product that is effectively already maturing (a moot
or impossible-to-act-on recommendation).

Two inputs control the filter:

- `min_business_days_to_maturity` — the number of **business days** a product
  must have remaining in order to be kept.  **Default `2`** (i.e. exclude any
  product with fewer than 2 business days to maturity).
- `as_of_date` — the reference date ("today").  **Defaults to the server system
  date** when not supplied.

## 2. Scope

### 2.1 Affected endpoints

The filter applies to all three product-search endpoints:

| Endpoint | Logic Layer function |
|---|---|
| `POST /api/v1/products/fitness-score` | `search_product_by_fitness_score()` |
| `POST /api/v1/products/search-similar` | `search_similar()` |
| `POST /api/v1/products/reinvestment-candidates` | `search_reinvestment_candidates()` (→ `search_similar_to_product()` → `search_similar()`) |

The `/api/v1/product-investor-matcher` pipeline is **not** changed directly,
but it calls `search_product_by_fitness_score()` internally and therefore
inherits the filter via the function's default parameters.  This inheritance
is intended.

### 2.2 Affected products

The filter applies **only** to products that carry an explicit maturity date in
`type_specific.maturity` (ISO 8601).  Today that includes:

| `product_type` | maturity source |
|---|---|
| `bond` | `type_specific.maturity` (explicit calendar date) |
| `deposit` | `type_specific.maturity` |
| `structured_product` | `type_specific.maturity` (contractual maturity) |
| `bond_fund` (target-maturity only) | `type_specific.maturity` |

Products **without** a parseable maturity date — open-ended funds, ETFs,
equities, money-market funds, cash — are **unaffected** and always retained.

Reuse the existing parser `_parse_maturity()` from
`src/planbot/client_enrichment.py` (parses `type_specific.maturity`, returns
`date | None`).  Do **not** reuse `_extract_time_to_maturity_days()` — that one
returns *duration* for `bond_fund` (`effective_duration`), which is not a
calendar maturity and must not drive this filter.

## 3. API change

Add two optional fields to each of the three request models in
`src/integrations/proposal_server.py` (`FitnessScoreRequest`,
`SimilarProductSearchRequest`, `ReinvestmentCandidatesRequest`):

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `min_business_days_to_maturity` | `int` (≥ 1) | no | `2` | Minimum business days to maturity a candidate must have to be kept |
| `as_of_date` | `str` (ISO 8601 date, e.g. `"2026-09-08"`) | no | server system date (`date.today()`) | Reference date for the near-maturity check |

They are threaded through:

- `get_product_fitness_score()` → `search_product_by_fitness_score(..., as_of_date=..., min_business_days_to_maturity=...)`
- `search_similar_products()` → `search_similar(..., as_of_date=..., min_business_days_to_maturity=...)`
- `get_reinvestment_candidates()` → `search_reinvestment_candidates(..., as_of_date=..., min_business_days_to_maturity=...)` → `search_similar_to_product()` → `search_similar()`

> `as_of_date` matches the existing maturity API
> (`GET /api/v1/clients/holdings/maturing`, `search_holdings_maturing`).
> `min_business_days_to_maturity` supersedes the earlier "1 business day"
> literal so the threshold is tunable (default `2`).

## 4. Business-day definition

- A **business day** is Monday–Friday.
- **Weekends (Saturday, Sunday) are holidays** and are skipped.
- Exchange / bank / territory public holidays are **not** modelled in this
  change (weekends only) — kept simple for now.

Define `next_business_day(d)` = the earliest date strictly after `d` that is
a business day (Mon–Fri).

## 5. Filter rule (precise)

Let:

- `n` = `min_business_days_to_maturity` (default `2`, ≥ 1).
- `ref` = `as_of_date` if provided, else `date.today()`.
- `cutoff` = `add_business_days(ref, n)` — the date that is `n` business days
  **after** `ref`, skipping weekends.

For each candidate product (the request's candidate `product_id`s — **not** the
holdings-enrichment IDs, see §6):

1. Parse `maturity = _parse_maturity(product)`.
2. If `maturity is None` → **keep** (no maturity date, not filterable).
3. Else if `maturity < cutoff` → **exclude** (fewer than `n` business days to maturity).
4. Else → **keep**.

Equivalently, in business-day terms: exclude when
`business_days_between(ref, maturity) < n`.

The boundary is **exclusive (strictly less than)**: a product maturing exactly
`n` business days out (`maturity == cutoff`) is **kept**.

The check uses **date-only** comparison (no time-of-day, no timezone).  With the
default `n = 2`, a product is excluded when it has fewer than 2 business days
remaining (e.g. it matures today, tomorrow, or over the immediately following
weekend).

`add_business_days(ref, n)` is defined as: starting from `ref`, advance one day
at a time, counting **only** business days (Mon–Fri) until `n` have elapsed;
the returned date is the date on which the `n`-th business day falls.

## 6. Placement in the pipeline

The filter runs **before scoring/ranking** in each function, on the candidate
set that will be scored:

### 6.1 `search_product_by_fitness_score()`

1. Fetch clients, holdings, products (as today).
2. Build the candidate list from the request's `product_ids`.
3. **Drop excluded near-maturity candidates.**
4. Proceed with the existing scoring loop over the *remaining* candidates.

The existing holdings-enrichment product IDs (fetched for experience /
better-product scoring) are **not** subject to the filter — only the candidate
`product_ids` being scored — otherwise a client's own already-held maturing
position could silently disappear from the comparison set.

### 6.2 `search_similar()`

1. Fetch products (as today), apply `exclude_product_ids`.
2. Apply the risk-rating hard filter (if enabled).
3. **Drop excluded near-maturity candidates.**
4. Proceed with similarity scoring / diversification on the survivors.

The `query` product (the anchor) is not in the scored set, so it is unaffected.

### 6.3 `search_reinvestment_candidates()`

Threads the two parameters down to `search_similar_to_product()` →
`search_similar()`, so the filter applies per client before candidate ranking.
The `source_product_id` (the maturing product being replaced) is already
excluded by `search_similar_to_product()`, so it is never subject to the
filter.

### Interaction with `top_n` / `max_candidates_*`

`top_n` (and `max_candidates_per_client` / `max_candidates_per_product_type`)
count only surviving (non-excluded) candidates.  Exclusion reduces the
candidate pool before ranking, so the returned row count is
`min(limit, surviving_count)`.

### Reporting excluded products

Add a structured, non-breaking report to each response's `meta` (and a log
line), so callers can see what was filtered:

```json
"meta": {
  "as_of_date": "2026-09-08",
  "min_business_days_to_maturity": 2,
  "near_maturity_excluded": ["PROD123", "FX-TARF-USDHKD-6M-B"]
}
```

> `search_product_by_fitness_score()` already returns `meta` with
> `semantic_embedding_available`; the new keys are added alongside it.
> `search_similar()` / `search_reinvestment_candidates()` currently return no
> `meta` — a `meta` block is added to them (non-breaking).

`near_maturity_excluded` lists candidate product IDs that were dropped, in the
order they were encountered.  An empty list / omitted key means nothing was
excluded.

## 7. Worked examples

Assume weekends are holidays (Mon–Fri business days), no other holidays.

| `as_of_date` (ref) | `n` | Product `maturity` | `cutoff` (`add_business_days(ref, n)`) | Result |
|---|---|---|---|---|
| Wed 2026-09-09 | 1 | 2026-09-09 (Wed) | Thu 09-10 | **exclude** (0 bd) |
| Wed 2026-09-09 | 1 | 2026-09-10 (Thu) | Thu 09-10 | keep (1 bd) |
| Wed 2026-09-09 | 2 | 2026-09-10 (Thu) | Fri 09-11 | **exclude** (1 bd < 2) |
| Wed 2026-09-09 | 2 | 2026-09-11 (Fri) | Fri 09-11 | keep (2 bd) |
| Fri 2026-09-11 | 1 | 2026-09-11 (Fri) | Mon 09-14 | **exclude** (0 bd) |
| Fri 2026-09-11 | 1 | 2026-09-12 (Sat) | Mon 09-14 | **exclude** (0 bd — weekend) |
| Fri 2026-09-11 | 1 | 2026-09-13 (Sun) | Mon 09-14 | **exclude** (0 bd — weekend) |
| Fri 2026-09-11 | 1 | 2026-09-14 (Mon) | Mon 09-14 | keep (1 bd) |
| Wed 2026-09-09 | 1 | `null` / absent / invalid | — | keep (no maturity date) |
| Wed 2026-09-09 | 1 | 2026-09-08 (Tue, already past) | Thu 09-10 | **exclude** (negative days) |

## 8. Edge cases

- **`min_business_days_to_maturity` out of range**: enforce `≥ 1` via Pydantic
  (`ge=1`), returning `422` on `0` / negative / non-integer values.
- **Invalid / unparseable `as_of_date`**: return a `422` validation error
  (FastAPI/Pydantic should validate ISO date format at the request boundary).
- **`as_of_date` on a weekend**: `add_business_days` still advances correctly
  (e.g. ref = Sat 09-12, `n = 2` → cutoff = Tue 09-15).  Allowed, not rejected.
- **All candidates excluded**: return the normal success shape with
  `results: []` and `near_maturity_excluded` populated (consistent with the
  existing "empty result is a valid 200" convention).
- **`maturity` present but non-ISO string**: `_parse_maturity` returns `None` →
  product is kept (treated as "no maturity date").  Log at DEBUG.

## 9. Implementation checklist (post-approval)

1. `src/planbot/client_enrichment.py` (or a shared helper module) — add
   `add_business_days(ref: date, n: int) -> date` (skip weekends) and reuse
   `_parse_maturity()`; make both unit-testable.
2. `src/integrations/product_tool.py` — add `as_of_date` +
   `min_business_days_to_maturity` params and the filter + `meta` to:
   - `search_product_by_fitness_score()`
   - `search_similar()` (and pass-through in `search_similar_to_product()`)
   - `search_reinvestment_candidates()`
3. `src/integrations/proposal_server.py` — add both fields to
   `FitnessScoreRequest`, `SimilarProductSearchRequest`, and
   `ReinvestmentCandidatesRequest`; thread through; update each endpoint
   docstring/`description`.
4. Regenerate OpenAPI: `./.venv/bin/python scripts/export_openapi.py`; update
   `docs/specification/data_api/endpoint_index.md` and
   `docs/specification/ranking_algorithm/product_fitness_score.md`.
5. Tests (Python `unittest`, per repo rules — at least one normal + one
   exception flow per endpoint):
   - normal: a near-maturity bond is excluded; a bond maturing exactly `n`
     business days out is retained; a no-maturity product is retained; weekend
     boundary behaves as documented.
   - exception: `min_business_days_to_maturity < 1` → `422`; invalid
     `as_of_date` → `422`; all-excluded → empty `200` with populated `meta`.

## 10. Acceptance Criteria

All of the following must hold before the change is merged.

### Functional

1. Each of the three endpoints — `POST /api/v1/products/fitness-score`,
   `POST /api/v1/products/search-similar`, and
   `POST /api/v1/products/reinvestment-candidates` — accepts the two new
   optional fields `min_business_days_to_maturity` (default `2`, `ge=1`) and
   `as_of_date` (ISO date, default server-local `date.today()`).
2. A candidate whose `type_specific.maturity` parses to a date **strictly less
   than** `add_business_days(as_of_date, min_business_days_to_maturity)` is
   excluded from results and listed in `meta.near_maturity_excluded`.
3. A candidate maturing **exactly** `n` business days out is **kept**
   (exclusive boundary).
4. Products with no parseable `type_specific.maturity` are always kept.
5. Weekends (Sat/Sun) are skipped when computing business days; no public
   holidays are modelled.
6. Each response's `meta` reports `as_of_date`, `min_business_days_to_maturity`,
   and `near_maturity_excluded` (empty list when nothing is excluded).

### Error handling

7. `min_business_days_to_maturity < 1` → HTTP `422`.
8. Invalid / unparseable `as_of_date` → HTTP `422`.
9. All candidates excluded → HTTP `200` with empty results (not an error).

### Regression

10. All existing **fast** unit tests pass (the full suite excluding the slow
    end-to-end regression file below).
11. The end-to-end **regression** test `tests/test_proposal_API.py` passes
    unchanged — it is the mandatory regression gate for integration changes and
    covers:
    - `/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings`
    - `/api/v1/product-opportunity-proposal`
    - `/api/v1/product-opportunity-proposal-automatch`
12. New unit tests are added (per repo rule: at least one normal flow + one
    exception flow per endpoint) and pass.

### Contract / docs

13. OpenAPI specs regenerated via `./.venv/bin/python scripts/export_openapi.py`;
    `docs/specification/data_api/endpoint_index.md` and
    `docs/specification/ranking_algorithm/product_fitness_score.md` updated to
    stay aligned with the live contract.

## 11. Decisions (resolved)

All open questions are settled and folded into the sections above:

1. **Boundary** — strict less than (`maturity < cutoff`); a product maturing
   exactly `n` business days out is kept.
2. **Parameter naming** — `as_of_date` (consistent with `get_holdings_maturing`).
3. **Holiday calendar** — weekends only (no public-holiday calendar).
4. **Opt-out** — none; the filter is always-on (no backward-compat flag).
5. **Matcher inheritance** — `/api/v1/product-investor-matcher` inherits the
   filter via `search_product_by_fitness_score()` defaults; intended.
6. **Product-type coverage** — generic: any product with a parseable
   `type_specific.maturity` is filterable.
7. **Timezone / date boundary** — server-local date (`date.today()`).
