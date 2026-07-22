# Product Fitness Score Card V2 (Future Enhancement)

## Objective

Define the next-generation Product Fitness Score (PFS) framework that improves suitability, explainability, and portfolio-level fit while keeping backward compatibility with the current implementation.

This document is based on the current implemented scoring logic in:
- `src/integrations/product_tool.py` (`search_product_by_fitness_score`)
- `config/config_planbot.yaml` (`product_fitness_score`)
- `tests/test_product_tool.py` (AC9 to AC14 related coverage)

## Current implementation baseline (V1)

Current PFS computes a weighted score for each `(client_id, product_id)` pair with 4 dimensions:

```
fitness_score = w1*risk_rating_match_score
              + w2*concentration_score
              + w3*has_similar_investment_experience_score
              + w4*better_product_score
```

Current defaults (`config/config_planbot.yaml`):
- `risk_rating_match_score`: 0.30
- `concentration_score`: 0.30
- `has_similar_investment_experience_score`: 0.20
- `better_product_score`: 0.20

Current behaviors:
- Optional hard risk gate (`risk_rating_hard_filter`) excludes products riskier than client risk rating.
- Concentration score uses a hypothetical add-position test.
- Experience score uses same-type / same-family / none tiers.
- Better-product score compares expected return uplift against comparable holdings.
- Scores are 0-10 per component; final score sorted by fitness, expected return, product_id.

## V2 design principles

1. Keep two-stage decisioning:
- Stage A: hard suitability/eligibility gates.
- Stage B: weighted ranking among eligible products.

2. Keep deterministic and explainable scoring:
- Each score must be decomposable into named component contributions.

3. Keep configuration-driven behavior:
- No hard-coded thresholds/weights in code.

4. Preserve backward compatibility:
- V1 fields remain available during migration.

## V2 scoring model

### Stage A: hard gates (pass/fail)

A product is eligible only if all enabled gates pass.

Proposed gates:
- `gate_risk_rating`: `product.risk_rating <= client.risk_rating` (existing behavior when hard filter enabled)
- `gate_currency_support`: product tradable/settleable in client account currency setup
- `gate_min_ticket`: client investable amount meets product minimum ticket size
- `gate_jurisdiction`: product legal/segment eligibility for client residence/profile
- `gate_liquidity_horizon`: product lock-up or maturity not violating client horizon constraints

Notes:
- Gates are boolean and should be returned in debug output.
- A failed gate returns an exclusion reason code.

### Stage B: weighted rank score (0-10)

For eligible products:

```
pfs_v2 = sum_i( w_i * s_i ) / sum_i(w_i)
```

Proposed dimensions:

1. `risk_alignment_score` (refined V1 risk match)
- Match between client risk rating and product risk rating.
- Add optional penalty for high downside asymmetry products.

2. `concentration_impact_score` (extends V1 concentration score)
- Impact on single-name, region, asset-class concentration.
- Add optional sector concentration impact when sector data is available.

3. `experience_compatibility_score` (extends V1 experience)
- Existing same-type/same-family logic.
- Add product complexity tier penalty when client experience is low.

4. `relative_improvement_score` (refines V1 better product score)
- Compare expected return and risk-adjusted efficiency versus comparable holdings.
- Optional fallback when expected_return is missing.

5. `goal_alignment_score` (new)
- Fit to client objective: income, growth, capital preservation, diversification.
- Penalize objective mismatch.

6. `liquidity_fit_score` (new)
- Match between product liquidity profile and client cash-flow horizon.

7. `cost_efficiency_score` (new)
- Fee/spread/load impact vs expected benefit.

8. `portfolio_correlation_score` (new, optional phase)
- Penalize products too correlated with concentrated exposures.

### Dimension input field contract and readiness checks

Each dimension must define minimum input fields and data-quality thresholds before being enabled in production scoring.

Readiness status definitions:
- `ready`: all required fields present and pass thresholds.
- `partial`: fields present but one or more thresholds fail; allow score with penalty or fallback only.
- `deferred`: required fields missing; dimension disabled.

| Dimension | Required input fields | DuckDB source | Minimum robustness checks |
|---|---|---|---|
| `risk_alignment_score` | `clients.risk_rating`, `products.risk_rating` | `clients`, `products` | Non-null coverage >= 99%; value in configured rating scale; invalid rate <= 0.5% |
| `concentration_impact_score` | `clients.aum`, `holdings.market_value`, `holdings.region`, `holdings.asset_class`, `products.region`, `products.asset_class` | `clients`, `holdings`, `products` | `aum > 0` coverage >= 98%; non-null region/asset_class coverage >= 95%; unresolved holding-product links <= 1% |
| `experience_compatibility_score` | `holdings.product_id`, `products.product_type`, optional `products.complexity_tier` | `holdings`, `products` | Non-null `product_type` coverage >= 98%; unmapped `product_type` to family <= 2%; duplicate `(client_id, product_id)` holdings rows pre-aggregated |
| `relative_improvement_score` | `products.expected_return`, comparable holdings by `product_type`, optional risk metrics (`volatility`, `max_drawdown`) | `products`, `holdings` | Non-null `expected_return` coverage >= 90% for in-scope product types; numeric sanity bounds pass (for example -100% to +100%); stale metric rate <= 10% |
| `goal_alignment_score` | `clients.investment_goal` (one or more), `products.investment_objective` or objective tags | `clients`, `products` | Goal taxonomy mapping coverage >= 95%; non-null client goal coverage >= 90%; unmapped goal labels <= 3% |
| `liquidity_fit_score` | `clients.liquidity_horizon_days` or equivalent horizon bucket, `products.liquidity_bucket`, `products.lockup_days`, optional `products.redemption_frequency` | `clients`, `products` | Non-null client horizon coverage >= 90%; non-null product liquidity metadata coverage >= 95%; lockup/horizon unit normalization validated |
| `cost_efficiency_score` | `products.expense_ratio`, `products.transaction_cost_bps`, optional `products.front_load_bps`, `products.exit_load_bps` | `products` | Non-null total-cost fields coverage >= 90%; all cost fields non-negative; outlier rate above configured cap <= 1% |
| `portfolio_correlation_score` (optional) | product factor tags or return series; client portfolio factor/return aggregates; optional covariance matrix snapshot date | `products`, derived analytics tables | History window completeness >= 80%; aligned frequency check passes; stale covariance snapshot rate <= 10% |

Notes:
- If a dimension is `partial`, scoring should either apply a confidence penalty or drop to a documented fallback formula.
- If a dimension is `deferred`, it must be excluded from weighting and remaining weights must be renormalized.

### Readiness validation output (required)

Before scoring run, emit a readiness summary to support audit and release decisions.

Suggested output:

```json
{
  "generated_at": "2026-07-16T10:30:00Z",
  "score_version": "v2",
  "dimension_readiness": {
    "risk_alignment_score": {
      "status": "ready",
      "checks": {
        "nonnull_coverage": 0.997,
        "scale_validity": 0.999
      }
    },
    "goal_alignment_score": {
      "status": "partial",
      "checks": {
        "client_goal_coverage": 0.88,
        "goal_taxonomy_mapping": 0.96
      },
      "fallback_mode": "reduced_weight"
    }
  }
}
```

## Suggested V2 default weights (initial)

These are starting points only and should be calibrated with outcome data.

```yaml
product_fitness_score_v2:
  weights:
    risk_alignment_score: 0.20
    concentration_impact_score: 0.20
    experience_compatibility_score: 0.10
    relative_improvement_score: 0.15
    goal_alignment_score: 0.15
    liquidity_fit_score: 0.10
    cost_efficiency_score: 0.10
```

Optional dimension:
- `portfolio_correlation_score` can be introduced later by reducing other weights proportionally.

## Output contract additions

V2 should still return `fitness_score` and `component_scores`, plus:

- `gates`: map of gate name -> pass/fail
- `gate_fail_reasons`: list of reason codes when excluded
- `component_contributions`: weighted contribution per dimension
- `data_quality_flags`: missing/stale critical inputs (e.g., missing expected return)
- `score_version`: e.g., `v1` or `v2`

Example (per result):

```json
{
  "client_id": "PB-HK-000001-8",
  "product_id": "BOND-XYZ",
  "fitness_score": 7.84,
  "score_version": "v2",
  "gates": {
    "gate_risk_rating": true,
    "gate_min_ticket": true,
    "gate_jurisdiction": true
  },
  "component_scores": {
    "risk_alignment_score": 8.5,
    "concentration_impact_score": 7.2,
    "goal_alignment_score": 9.0
  },
  "component_contributions": {
    "risk_alignment_score": 1.70,
    "concentration_impact_score": 1.44,
    "goal_alignment_score": 1.35
  },
  "data_quality_flags": ["missing_coupon"]
}
```

## Data requirements for V2

New or improved fields likely needed:
- Client goal profile (income/growth/preservation/diversification)
- Client liquidity horizon and near-term cash need
- Product fee and transaction-cost fields
- Product complexity tier
- Product eligibility metadata (jurisdiction, segment, min ticket)
- Optional product correlation proxies or factor tags
- Optional sector in holdings/product linkage

Minimum implementation requirement:
- Any dimension without a completed input-field contract and readiness checks must remain disabled by config.

## Migration strategy

### Phase 1: V2 skeleton with V1 parity
- Introduce `score_version` switch.
- Keep current 4 V1 dimensions as V2-compatible names.
- Add gate output structure without changing ranking logic.

### Phase 2: Add new dimensions with feature flags
- Enable `goal_alignment_score`, `liquidity_fit_score`, `cost_efficiency_score` behind config flags.
- Keep default off until data quality is validated.

### Phase 3: Calibration and tuning
- Tune weights/thresholds using historical outcomes.
- Add monitoring for score drift and recommendation stability.

## Acceptance criteria (V2)

| # | Criterion | Verification |
|---|---|---|
| AC1 | V2 supports stage-A gates and stage-B weighted scoring | Unit tests for gate pass/fail and score output |
| AC2 | V2 preserves V1 result compatibility when new dimensions are disabled | Regression test comparing V1 vs V2-compat mode |
| AC3 | V2 returns explainable outputs (`gates`, `component_contributions`, `score_version`) | Contract tests |
| AC4 | New dimensions are config-driven and can be toggled without code changes | Config toggle tests |
| AC5 | Missing data does not crash scoring and is surfaced via `data_quality_flags` | Negative-path unit tests |
| AC6 | Sorting remains deterministic with documented tie-break rules | Determinism test on fixed fixture |
| AC7 | Hard-gate exclusion reasons are explicit and auditable | Unit test for each gate reason code |
| AC8 | End-to-end API can return mixed results (eligible + excluded products) per client | Integration test with fixture payload |
| AC9 | Dimension readiness validation is emitted before scoring and includes status (`ready`, `partial`, `deferred`) for each enabled V2 dimension | Contract test with validation fixture |

## Open decisions

1. Whether suitability gates should be globally strict or policy-configurable by channel/client segment.
2. Whether `relative_improvement_score` should include volatility/drawdown when available.
3. Whether helper APIs should expose full scoring traces by default or only in debug mode.
4. Whether to add a minimum score threshold for recommendation eligibility.

## Not in V2 scope

- ML model replacement of rules-based scoring.
- Full optimization engine (mean-variance or factor optimizer).
- Real-time event-driven re-scoring architecture.
