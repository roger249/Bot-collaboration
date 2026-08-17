## Product fitness score

The score measures how fit a candidate product is for a particular investor, computed across four independent dimensions — without assuming the investor switches out an existing product.

### Objective

Rank candidate products for a given client so the LLM can make a final recommendation.  The score is a **relative** ranking signal (higher = better fit), not a pass/fail gate; the hard risk gate is the only eligibility filter.

### Factors in the scorecard

The four sub-scores (each 0-10 before weighting):

| Factor | What it measures | Example product decision |
|--------|------------------|--------------------------|
| **risk_rating_match** | Closeness of `product.risk_rating` to `client.risk_rating`. | A conservative client (risk 2) is matched to a low‑risk bond; a risk‑5 product is filtered out by the hard gate for that client. |
| **diversification** | Whether adding the product worsens portfolio concentration (higher = less added concentration risk). | An equity‑heavy client scores a precious‑metals or bond candidate highly, because adding it reduces concentration; an extra large‑cap equity position scores low. |
| **has_similar_investment_experience** | Whether the client already holds the same `product_type` or `product_family`. | A client already holding `bond` funds is a natural fit for another bond candidate; a first‑time equity investor gets a lower score for a complex equity product. |
| **better_product** | Whether the candidate has a higher `expected_return` than the client's existing holdings of the same `product_type`. | If the client holds a 3.0% bond and a candidate bond yields 4.5%, the candidate scores high as a superior replacement; a lower‑yield candidate scores 0. |

The `diversification` score is computed as the concentration risk of a hypothetical portfolio that adds the product at `concentration_test_position_pct_aum * client.aum`.

### Input

The score card consumes three data entities through the data-access layer (DAL):

| Entity | Fields used |
|--------|-------------|
| `clients` | `client_id`, `aum`, `risk_rating` |
| `holdings` | `client_id`, `product_id`, `market_value`, `region`, `asset_class` |
| `products` | `product_id`, `name`, `product_type`, `risk_rating`, `expected_return`, `region`, `asset_class`, `investment_note` |

The DAL is configured by `data_source` in `config_planbot.yaml` (self-contained DuckDB by default, or the bank REST API via `common.get_client_product_from_restapi: true`).

API input parameters:

| Parameter | Type | Default | Meaning |
|-----------|------|---------|---------|
| `client_ids` | list[str] | required | Clients to score (m) |
| `product_ids` | list[str] | required | Candidate products (n) |
| `top_n` | int | 10 | Max rows returned (1-50) |
| `risk_rating_hard_filter` | bool | true | Enforce `product.risk_rating <= client.risk_rating` |
| `exclude_dimensions` | list[str] | null | Dimensions to drop before renormalizing weights |

### Scoring behavior

- All four PFS dimensions are included by default.
- API callers may remove dimensions explicitly via `exclude_dimensions`.
- The final score must be computed from included dimensions only (renormalized weights).
- The final score is used for relative ranking across candidate products, not as a hard pass/fail score.
- For diversification, reuse the concentration-risk method configured in `config/config_planbot.yaml` under `investor_readiness_score.score_concentration_risk`, but evaluate it on a hypothetical post-add portfolio:
  - `s_single_holding`
  - `s_region_exposure`
  - `s_asset_class_exposure`
  - compute concentration risk as the max of the three interpolated sub-scores.
  - assume the candidate product is added as a test position equal to `concentration_test_position_pct_aum * client.aum`.
  - convert that concentration risk into a diversification-friendly score by `diversification_score = 10 - hypothetical_concentration_risk_score`.

### Formula

Inputs:

- `client_ids` (m)
- `product_ids` (n)

Output rows:

- `(client_id, product_id, fitness_score, component_scores)` — plus `product_name` and `investment_note` for display.

Per pair `(client_id, product_id)`, compute:

**1) Hard risk gate**

The computing logic depends on the input parameter `risk_rating_hard_filter`.
- `true` (default)
  - if `product.risk_rating > client.risk_rating`, the pair is **excluded entirely** (no result row is emitted).
  - if the product's `risk_rating` is missing, it is treated as `99`, so the pair is excluded whenever the client has a rating.
- `false`
  - the gate is bypassed and all pairs are scored normally.

**2) Component scores (0 to 10 scale before weighting)**

- **risk_rating_match_score**
  - if gate passes, score by closeness of `product.risk_rating` to `client.risk_rating`
  - use:

    `risk_rating_match_score = 10 * (1 - |client.risk_rating - product.risk_rating| / 4)`

  - clip to `[0, 10]`
  - if either `risk_rating` is missing, the score is a neutral `5.0`.

The above logic may change to yaml table definition later after empirical test.

- **diversification_score**
  - computed using the same concentration method/pivots in `investor_readiness_score.score_concentration_risk`
  - sub-scores from `s_single_holding`, `s_region_exposure`, `s_asset_class_exposure`
  - add the candidate product as a hypothetical position with notional:

    `candidate_test_notional = concentration_test_position_pct_aum * client.aum`

  - recompute the client concentration risk on the hypothetical portfolio after adding that position
  - hypothetical concentration risk score = `max(sub_scores)`
  - final diversification score:

    `diversification_score = 10 - hypothetical_concentration_risk_score`

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
  - use market-value-weighted impact instead of count-based impact
  - higher score when candidate has better `expected_return` than the comparable holdings
  - weighted uplift:
    - `weight_h = market_value_h / sum(market_value over comparable holdings)`
    - `uplift_h = max((expected_return_candidate - expected_return_h) / max(abs(expected_return_h), eps), 0)`
    - `better_product_score = better_product_score_scale * min(sum(weight_h * uplift_h) / better_product_score_uplift_cap, 1)`, clipped to `[0, 10]`
  - if there are no comparable holdings (no same-`product_type` exposure), or the candidate has no `expected_return`, the score is `0` (no baseline for comparison).

**3) Final weighted score**

- Let included dimensions be all PFS dimensions except those explicitly listed in `exclude_dimensions`.
- Read `w_k` from YAML config (`config/config_planbot.yaml`).
- Renormalize their weights to sum to 1.

`fitness_score = sum(w_k * score_k)` over included dimensions only.

Ranking:

- sort the full result set by descending `fitness_score`; ties break by `expected_return` desc, then `product_id` asc.
- truncate to `top_n` rows.

### Configuration

Weights and parameters live in `config/config_planbot.yaml` under `product_fitness_score`:

```yaml
product_fitness_score:
  product_fitness_weights:
    risk_rating_match_score: 0.30
    diversification_score: 0.30
    has_similar_investment_experience_score: 0.20
    better_product_score: 0.20
  product_fitness_params:
    better_product_score_scale: 10
    better_product_score_uplift_cap: 0.30
    better_product_score_eps: 0.01
    concentration_test_position_pct_aum: 0.10  # % of AUM used as hypothetical test position
    experience_score_same_type: 10.0           # high: same product_type held
    experience_score_same_family: 6.0          # medium: same product_family held
    experience_score_none: 0.0                 # low: no match
```

> `product_fitness_weights` and `product_fitness_params` drive the PFS.  The sibling `search_similar_weights` / `search_similar_sigmas` keys are used by `search_similar`, not by the PFS.

### API

FastAPI endpoint (implemented in `src/integrations/proposal_server.py`, delegating to `search_product_by_fitness_score` in `src/integrations/product_tool.py`):

```
POST /api/v1/products/fitness-score
```

Request body (`FitnessScoreRequest`):

```json
{
  "client_ids": ["PB-HK-000007-5"],
  "product_ids": ["PROD054", "ETF-BIL", "ETF-SHV"],
  "top_n": 10,
  "risk_rating_hard_filter": true,
  "exclude_dimensions": ["diversification_score"]
}
```

Response — a flat list of `FitnessScoreItem`:

```json
{
  "results": [
    {
      "client_id": "PB-HK-000007-5",
      "product_id": "PROD054",
      "product_name": "China Government Bond",
      "investment_note": "Individual bonds allow precise maturity-matching…",
      "fitness_score": 8.25,
      "component_scores": {
        "risk_rating_match_score": 10.0,
        "diversification_score": 8.0,
        "has_similar_investment_experience_score": 6.0,
        "better_product_score": 7.5
      }
    }
  ]
}
```

### Downstream use

The score passes to the LLM along with the selected clients and products to make the final recommendation, together with

- market outlook
- product description from the bank

The mechanism mirrors the current `client_product_fit_analysis_task` in `config/config_planbot.yaml`.
