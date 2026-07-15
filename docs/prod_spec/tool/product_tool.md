Product Catalog Integration
===========================

## Overview

The information about the financial product is retrieved via API from the main module product catalog layer.  To develop a working prototype without depending on the readiness of the main module.  This spec is to provide a mock up (simulation) of the product catalog API.  The main tasks includes

1. Tidy up and have initial schema designed for the product catalog
2. Populate it with test data
3. Move all product catalog into DuckDB
4. Provide Python method to query the duckDB
5. Move Python method into Fast API
6. With this product and the client API, we will migrate the various investment proposal to use API to query the necessary data to fit to LLM.

Steps 1-3 shall have finished from the spec docs/prompts/product_catalog.md

This document focus on step 4.

All score (constant) used in the computation shall be defined in yaml and not hard coded.

## Python methods for search products

Below are the API exposed to search the product catalog, it returns a list of the products in JSON format

### search_by_product_id

Look up a single product by its `product_id`.

### search_similar

Proximity search returning top *n* products ranked by similarity to the query attributes:

- `risk_rating`
- `expected_return`
- `product_type`
- `asset_class`
- `region`
- `sector` (mapped to `sector` in products table)
- `time_to_maturity` — accepted in d, w, m, y
- `coupon` — dividend of a MF/ETF, coupon for bond
- `trade_date` — default to system date if not specified; used to compute `time_to_maturity`

search_similar filtering rules:

- `product_type` is a soft filter only
- `risk_rating` behavior is controlled by API input `risk_rating_hard_filter`
  - `true`: enforce `risk_rating` as a hard filter constraint
  - `false`: include `risk_rating` in similarity scoring only
- `diversification`
  - if true (default), 
    Diversification selection algorithm:
    - Group the `search_similar` ranked results by `product_type`.
    - From each group, select the top-*max_per_product_type* products by similarity score.
    - *max_per_product_type* is an input parameter, default to 2.
    - The diversification rule is applied per query.
  - false
    - return the list of product ordered by score in descending order
- If a dimension is not specified in the input, exclude that dimension from scoring
- Score weights are normalized by the included dimensions only
- Final score is used as relative ranking only (not an absolute score threshold)


### search_reinvestment_candidates

Leverages `search_similar` but the input is a `product_id` whose attributes are used as the similarity query.

Diversification rule also applies.

### search_product_by_fitness_score

Accepts lists of `client_id` (m) and `product_id` (n), computes a fitness score for each client×product pair, and returns the top-*n* results ranked by descending score

Output shape: `(client_id, product_id, score, component_scores)`

See the formula section below for scoring details and the API contracts section for the request/response format.

## Product fitness score

The score measures how fit a product is for a particular investor, computed across the following dimensions.  Without assuming switching out a particular product.

### Dimensions

1. **risk_rating_match** — `product.risk_rating <= client.risk_rating`
2. **concentration** — the product, when fit to the portfolio, will not create concentration issue
   - It's computed as the concentration by adding the product to the portfolio by an amount concentration_test_position_pct_aum (defined in yaml)
3. **has_similar_investment_experience**
   - holding of same `product_type`
   - holding of the same `product_family` as the `product_type`
4. **better_product_than_existing**
   - better return than existing with same `risk_rating`
   - same `risk_rating` but better `expected_return`

### Scoring behavior

- All four PFS dimensions are included by default.
- API callers may remove dimensions explicitly via `exclude_dimensions`.
- The final score must be computed from included dimensions only (renormalized weights).
- The final score is used for relative ranking across candidate products, not as a hard pass/fail score.
- For concentration, reuse the concentration method configured in `config/config_planbot.yaml` under `investor_readiness_score.score_concentration_risk`, but evaluate it on a hypothetical post-add portfolio:
  - `s_single_holding`
  - `s_region_exposure`
  - `s_asset_class_exposure`
  - compute concentration risk as the max of the three interpolated sub-scores.
  - assume the candidate product is added as a test position equal to `concentration_test_position_pct_aum * client.aum`.
  - convert that concentration risk into a diversification-friendly score by `concentration_score = 10 - hypothetical_concentration_risk_score`.

### Formula

Inputs:

- `client_ids` (m)
- `product_ids` (n)

Output rows:

- `(client_id, product_id, score, component_scores)`

Per pair `(client_id, product_id)`, compute:

**1) Hard risk gate**

The computing logic depends on the input parameter `risk_rating_hard_filter`.
- default to true
  - if `product.risk_rating > client.risk_rating`, then score is 0 and row is ranked at bottom.
- false
  - above checking is bypassed and score is computed as normal

**2) Component scores (0 to 10 scale before weighting)**

- **risk_rating_match_score**
  - if gate passes, score by closeness of `product.risk_rating` to `client.risk_rating`
  - use:

    `risk_rating_match_score = 10 * (1 - |client.risk_rating - product.risk_rating| / 4)`

  - clip to `[0, 10]`

The above logic may change to yaml table definition later after empirical test.

- **concentration_score**
  - computed using the same concentration method/pivots in `investor_readiness_score.score_concentration_risk`
  - sub-scores from `s_single_holding`, `s_region_exposure`, `s_asset_class_exposure`
  - add the candidate product as a hypothetical position with notional:

    `candidate_test_notional = concentration_test_position_pct_aum * client.aum`

  - recompute the client concentration risk on the hypothetical portfolio after adding that position
  - hypothetical concentration risk score = `max(sub_scores)`
  - final concentration score:

    `concentration_score = 10 - hypothetical_concentration_risk_score`

  - this keeps the score on a 0-10 scale where higher is better diversification and lower is more concentration risk introduced by the candidate
- **has_similar_investment_experience_score**
  - same `product_type` held: high (score = `experience_score_same_type`, default 10.0)
  - holding of same `product_family` as target `product_type`: medium (score = `experience_score_same_family`, default 6.0)
  - otherwise: low (score = `experience_score_none`, default 0.0)
  - The `product_type` → `product_family` mapping is defined in `src/shared/product_family.py` via `get_product_family()`.
    Unmapped `product_type` values default to themselves as their own family.

    | `product_type` | `product_family` |
    |---|---|
    | `bond` | `bond` |
    | `bond_fund` | `bond` |
    | `equity_fund` | `equity` |
    | `stock` | `equity` |
    | `money_market_fund` | `cash` |
    | `balanced_fund` | `balanced` |

  - Example: a `bond_fund` candidate matches "same family" against a client holding `bond`. A `balanced_fund` candidate matches "same family" only against clients holding other `balanced_fund` products.
- **better_product_score**
  - compare candidate product against each comparable holding in portfolio (same `product_type`)
  - use notional/position-weighted impact instead of count-based impact
  - higher score when candidate has better `expected_return` than holdings with same/similar `risk_rating`, weighted by holding notional (or market_value)
  - suggested weighted uplift:
    - `weight_h = holding_notional_h / sum(holding_notional over comparable holdings)`
    - `uplift_h = max((expected_return_candidate - expected_return_h) / max(abs(expected_return_h), eps), 0)`
    - `better_product_score = better_product_score_scale * min(sum(weight_h * uplift_h) / better_product_score_uplift_cap, 1)`
  - if no comparable holdings exist, score is 0 (no baseline for comparison — the client has no exposure to this product type)

**3) Final weighted score**

- Let included dimensions be all PFS dimensions except those explicitly listed in `exclude_dimensions`.
- Read `w_k` from YAML config (`config/config_planbot.yaml`).
- Renormalize their weights to sum to 1.

`fitness_score = sum(w_k * score_k)` over included dimensions only.

Ranking:

- rank by descending `fitness_score` per client.
- ties break by `expected_return` desc, then `product_id` asc.

The score will pass to the LLM along with the selected clients and products to make the final recommendation.  The additional information including

- market outlook
- product description from the bank

the mechanism will be similar to the current proposal client_product_fit_analysis_task specified in config/config_planbot.yaml

## API contracts

### search_similar

Request:

```json
{
  "query": {
    "risk_rating": 3,
    "expected_return": 6.5,
    "product_type": "bond_fund",
    "asset_class": "fixed_income",
    "region": "north_america",
    "sector": "government",
    "time_to_maturity": "2y",
    "coupon": 4.2,
    "trade_date": "2026-07-14"
  },
  "top_n": 3,
  "risk_rating_hard_filter": false,
  "diversification": true,
  "max_per_product_type": 2,
  "exclude_product_ids": ["PROD001"]
}
```

#### Behavior

- `product_type` is always soft scoring only.
- `risk_rating_hard_filter = true`: enforce `product.risk_rating <= query.risk_rating` as a hard eligibility filter.
- `risk_rating_hard_filter = false` (default): no hard filter; include `risk_rating` in similarity score.
- `w_i` are read from YAML config (`config/config_planbot.yaml`), not from API request payload.
- Both methods read their respective weight sets from `config/config_planbot.yaml` under `product_fitness_score.search_similar_weights` and `product_fitness_score.product_fitness_weights`.
- If any dimension is not specified in `query`, remove that dimension from scoring and renormalize remaining weights to sum to 1.
- Ranking is by descending similarity score only (relative ranking semantics).

- `top_n` is optional; if omitted, defaults to 3.

#### Similarity score

- For numeric dimensions:

  `s_i = 1 - min(abs(x_i - q_i) / sigma_i, 1)`

- For categorical dimensions:

  `s_i = 1` for exact match; `s_i = 0` for mismatch.

- Final similarity score:

  `similarity_score = sum(w_i * s_i)` over included dimensions only.

#### Response

```json
{
  "results": [
    {
      "product_id": "ETF-HYG",
      "name": "iShares iBoxx High Yield Corporate Bond ETF",
      "product_type": "bond_fund",
      "risk_rating": 3,
      "expected_return": 6.2,
      "similarity_score": 0.92
    },
    {
      "product_id": "ETF-BND",
      "name": "Vanguard Total Bond Market ETF",
      "product_type": "bond_fund",
      "risk_rating": 2,
      "expected_return": 4.8,
      "similarity_score": 0.84
    }
  ]
}
```

Consumers needing full product details should call `search_by_product_id` with the returned `product_id` values.

#### sigma_i — per-dimension scale for numeric similarity

`sigma_i` controls how "wide" a match is for each numeric dimension. Two sources, resolved in order of precedence:

| Precedence | Source | Description |
|---|---|---|
| 1 (primary) | YAML config `product_fitness_score.search_similar_sigmas` | Explicit per-dimension sigma values |
| 2 (fallback) | Population standard deviation from `products` table | Computed dynamically per dimension when YAML value is absent |

Behavior:

- If a `sigma_i` is defined in YAML for a given dimension, use it.
- If not defined, compute `sigma_i = STDDEV_POP(column)` over all rows in the `products` table for that dimension.
- For `time_to_maturity`, the fallback sigma is computed on the derived column `DATEDIFF('day', trade_date, maturity)` across all products where maturity is populated.
- For `coupon`, the fallback sigma is computed on the derived `coupon_value` (see extraction table below).

#### Dimension-to-column extraction mapping

Some query dimensions do not map 1:1 to a single `products` column. The table below defines the extraction path for each dimension.

| Query dimension | DuckDB source | Extraction rule |
|---|---|---|
| `risk_rating` | `products.risk_rating` | Direct column |
| `expected_return` | `products.expected_return` | Direct column |
| `product_type` | `products.product_type` | Direct column (categorical) |
| `asset_class` | Derived: mapped from `products.product_type` | `bond_fund`, `bond` → `fixed_income`; `equity_fund`, `stock` → `equity`; `money_market_fund` → `cash`; `balanced_fund` → `balanced` |
| `region` | `products.region` | Direct column (categorical) |
| `sector` | `products.sector` | Direct column (categorical). |
| `time_to_maturity` | Derived: `json_extract(type_specific, '$.maturity')` for bonds; `json_extract(type_specific, '$.effective_duration')` for bond funds | For `bond`: `DATEDIFF('day', trade_date, CAST(json_extract_string(type_specific, '$.maturity') AS DATE))`. For `bond_fund`: use `effective_duration * 365` (years→days). For other product types: dimension is excluded from scoring (no meaningful maturity concept). |
| `coupon` | Derived: `json_extract(type_specific, '$.coupon_rate')` for bonds; `json_extract(type_specific, '$.dividend_yield')` or `performance_history` yield for equity/balanced funds | For `bond`: `CAST(json_extract_string(type_specific, '$.coupon_rate') AS DOUBLE)`. For `equity_fund`, `stock`, `balanced_fund`: `CAST(json_extract_string(type_specific, '$.dividend_yield') AS DOUBLE)`. For `bond_fund`: use `json_extract(type_specific, '$.ytm')` as coupon proxy. For `money_market_fund`: use `json_extract(type_specific, '$.yield_type')` as proxy. If extracted value is NULL for a given product, exclude that product from `coupon` dimension scoring. |
| `trade_date` | API input only | Not a product column. Used to compute `time_to_maturity` (see above). Defaults to `CURRENT_DATE` if not specified. |

The input format for `time_to_maturity` in the query accepts: number + unit suffix. The unit suffix determines conversion to days:

| Suffix | Unit | Multiplier |
|---|---|---|
| `d` | days | 1 |
| `w` | weeks | 7 |
| `m` | months | 30.4375 (365.25/12) |
| `y` | years | 365.25 |

Example: `"2y"` → 730.5 days.

### search_reinvestment_candidates

Request:

```json
{
  "client_ids": ["PB-HK-000001-8", "PB-HK-000002-6"],
  "source_product_id": "ETF-HYG",
  "max_per_product_type": 2,
  "top_n_per_client": 10,
  "risk_rating_hard_filter": false,
  "exclude_product_ids": ["ETF-HYG"]
}
```

- All `search_similar` parameters are passed through: `risk_rating_hard_filter`, `exclude_product_ids`, `diversification`, and `max_per_product_type` are forwarded directly with the same names. `top_n_per_client` maps to `top_n`.
- `risk_rating_hard_filter` is optional; if omitted, defaults to `false`.
- For each client, use the source product attributes as the `search_similar` query.
- Apply diversification selection per client: group ranked results by `product_type`, pick top-*max_per_product_type* from each group.
- `max_per_product_type` is optional; if omitted, defaults to 2.
- `top_n_per_client` is optional; if omitted, return all selected products after diversification grouping.

Response:

```json
{
  "results_by_client": {
    "PB-HK-000001-8": [
      {
        "product_id": "ETF-BND",
        "product_type": "bond_fund",
        "similarity_score": 0.84
      },
      {
        "product_id": "ETF-VOO",
        "product_type": "equity_fund",
        "similarity_score": 0.63
      }
    ]
  }
}
```

Consumers needing full product details should call `search_by_product_id` with the returned `product_id` values.

### search_product_by_fitness_score

Request:

```json
{
  "client_ids": ["PB-HK-000001-8", "PB-HK-000002-6"],
  "product_ids": ["ETF-HYG", "ETF-BND", "ETF-VOO", "PROD003"],
  "top_n": 10,
  "risk_rating_hard_filter": true,
  "exclude_dimensions": ["better_product_than_existing"]
}
```

- `exclude_dimensions` is optional; if omitted, all 4 dimensions are included.
- `top_n` is optional; if omitted, defaults to 10.

Response:

```json
{
  "results": [
    {
      "client_id": "PB-HK-000001-8",
      "product_id": "ETF-BND",
      "fitness_score": 8.35,
      "component_scores": {
        "risk_rating_match_score": 9.0,
        "concentration_score": 8.5,
        "has_similar_investment_experience_score": 10.0,
        "better_product_score": 6.2
      }
    }
  ]
}
```

## YAML configuration

```yaml
product_fitness_score:
  search_similar_weights:
    risk_rating: 0.25
    expected_return: 0.20
    product_type: 0.15
    asset_class: 0.10
    region: 0.10
    sector: 0.05
    time_to_maturity: 0.10
    coupon: 0.05
  search_similar_sigmas:
    risk_rating: 2.0
    expected_return: 5.0
    time_to_maturity: 730.0   # days (~2 years)
    coupon: 2.0
  product_fitness_weights:
    risk_rating_match_score: 0.30
    concentration_score: 0.30
    has_similar_investment_experience_score: 0.20
    better_product_score: 0.20
  product_fitness_params:
    better_product_score_scale: 10
    better_product_score_uplift_cap: 0.30
    better_product_score_eps: 0.01
    concentration_test_position_pct_aum: 0.10
    experience_score_same_type: 10.0
    experience_score_same_family: 6.0
    experience_score_none: 0.0
```

## Acceptance criteria

The following must be satisfied for this spec to be considered implemented.

All acceptance criteria except AC1 require a corresponding unit test.

| # | Criterion | Verification |
|---|---|---|
| AC1 | `config/config_planbot.yaml` contains the `product_fitness_score` section with all weights, sigmas, and params defined above | Manual review of YAML file |
| AC2 | `search_similar()` returns products ranked by similarity score; unspecified query dimensions are excluded and weights renormalized | Unit test: call with partial query, verify excluded dimensions not in scoring |
| AC3 | `sigma_i` uses YAML value when present, falls back to population std dev otherwise | Unit test: remove one sigma from YAML, verify fallback value computed from DB |
| AC4 | `product_type` is always soft-scored only (never a hard filter in `search_similar`) | Unit test: query with `product_type`, verify products with different type still appear (with lower score) |
| AC5 | `risk_rating_hard_filter=true` enforces `product.risk_rating <= query.risk_rating`; `false` includes `risk_rating` in similarity score only | Unit test: compare result counts for both modes |
| AC6 | `time_to_maturity` and `coupon` are correctly extracted from `type_specific` JSON per the extraction mapping table | Unit test: query bonds/bond funds, verify derived values |
| AC7 | Products where a numeric dimension cannot be extracted (NULL JSON path) are excluded from that dimension's scoring but not from the result set | Unit test: include a product with NULL coupon, verify it ranks but coupon dimension excluded |
| AC8 | `search_reinvestment_candidates()` accepts `client_ids` and `source_product_id`, groups by `product_type`, and selects top-*max_per_product_type* per group with *max_per_product_type* defaulting to 2 | Unit test: verify request/response contract and group counts ≤ max_per_product_type per client |
| AC9 | `product_fitness_score()` when `risk_rating_hard_filter=true` (default), applies hard risk gate (`product.risk_rating > client.risk_rating → score=0`); when `false`, bypasses the gate. Computes all 4 component scores (0-10 scale), and returns `(client_id, product_id, score, component_scores)` | Unit test: verify gate behavior for both modes, verify component score ranges |
| AC10 | `risk_rating_match_score` uses the explicit closeness formula `10 * (1 - |client.risk_rating - product.risk_rating| / 4)`, clipped to `[0, 10]` after the hard gate passes | Unit test: verify exact-match = 10 and lower-risk products score proportionally lower |
| AC11 | `concentration_score` in PFS reuses `score_concentration_risk()` pivots on a hypothetical post-add portfolio using `concentration_test_position_pct_aum * client.aum`, then converts to `10 - hypothetical_concentration_risk_score` | Unit test: compare concentration score for diversified vs concentrated candidate additions |
| AC12 | `better_product_score` uses notional-weighted uplift with `eps` from YAML; scores 0 when no comparable holdings exist (no baseline) | Unit test: client with no matching product_type holdings → 0; client with holdings → computed score |
| AC13 | Renormalized weights sum to 1 when dimensions are excluded via `exclude_dimensions` | Unit test: call with excluded dimensions, verify weights sum to 1 |
| AC14 | Ties in PFS ranking break by `expected_return` desc, then `product_id` asc | Unit test: two products with equal fitness score, verify ordering |
| AC15 | `search_similar()` with `diversification=true` groups results by `product_type` and selects top-*max_per_product_type* per group with *max_per_product_type* defaulting to 2; with `diversification=false` returns a flat list ordered by similarity score desc | Unit test: compare result shapes for both modes, verify group counts ≤ max_per_product_type |

## Outstanding

Items identified during review. Tracked here for follow-up.

All known issues have been resolved. This section is intentionally left empty.

| # | Item | Suggested Approach |
|---|---|---|