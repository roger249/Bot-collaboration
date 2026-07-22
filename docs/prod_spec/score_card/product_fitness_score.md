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
