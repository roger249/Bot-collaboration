# Proposal JSON Output Specification — Sprint 2 (Comprehensive)

## Version
- Spec version: 1.0-s2
- Date: 2026-07-24
- Scope: Extends Sprint 1 (`proposal_JSON_output_s1.md`) by adding narrative fields to the JSON payload. This enables downstream systems to consume the full proposal in structured form without parsing markdown.

## Relationship to Sprint 1

Sprint 1 defines the minimal JSON contract (computation-required fields only). This Sprint 2 spec is a superset. An S1 payload is a valid S2 payload with narrative fields omitted.

| Aspect | Sprint 1 | Sprint 2 (this spec) |
|---|---|---|
| `schema_version` | `1.0-s1` | `1.0-s2` |
| LLM-owned JSON fields | 3 groups | 9 groups |
| Markdown narrative | Primary narrative | Duplicated in JSON |
| JSON failure surface | Low | Higher |

## Objective
Define a comprehensive structured JSON payload produced by LLM that captures both computation-required fields (scenario assumptions, funding source) and narrative content (executive summary, rationale, pros/cons, alternatives). The downstream system can optionally use this to rebuild the full proposal from JSON without parsing markdown.

The payload must carry:
- Recommended product identity, allocation amount, and narrative rationale.
- Recommended product risk characteristics.
- Alternative product suggestions and justification.
- Pros and cons of the recommendation.
- Funding source description (what is sold/trimmed).
- Client needs inferred from the client profile.
- Scenario return assumptions.
- References used by the LLM.

The payload must not carry:
- Computed portfolio totals, ending values, or probability-weighted portfolio metrics (these remain downstream-owned).

## Two-Stage Architecture

1. Stage 1 (LLM)
- Inputs: client profile, product catalog snapshot, guidelines, prompt instructions.
- Outputs: markdown proposal + comprehensive JSON payload.

2. Stage 2 (Downstream proposal generation)
- Inputs: LLM JSON + raw holdings + same-version product catalog snapshot.
- Outputs: enriched markdown proposal with deterministic scenario valuation, risk disclosures, performance metrics, suggested portfolio allocation.
- Optionally: assemble full proposal output directly from JSON + catalog/holdings data (bypassing markdown parsing).

## Contract Boundaries

### LLM-owned fields
- Recommended product, allocation amount, and narrative rationale.
- Recommended product risk characteristics.
- Alternative product suggestions and justification.
- Pros and cons of the recommendation.
- Funding source description.
- Client needs inferred from the client profile.
- Scenario assumptions (returns, drivers, confidence, data source labels).
- Structured product hold-to-maturity assumption metadata.
- References used during evaluation.

### Python-injected fields
These are NOT output by the LLM. After extraction, Python merges them:

| Field | Source |
|---|---|
| `schema_version` | Always `"1.0-s2"` |
| `proposal_type` | Known from task config |
| `client_id` | Known from fan-out binding |
| `catalog_context.*` | Catalog version metadata from the run |
| `valuation_context.*` | Known from task config defaults |
| `source_product_id` | Known from client input |

### Scenario field semantics
- `name` — Display label for the scenario (e.g., "Normal", "Upside — Soft Landing").
- `description` — 1-3 sentence qualitative summary of the macro backdrop and key themes.
- `assumption_rationale` — Bullet-point justification for individual assumption choices.

### Downstream-owned fields
- Product-level PnL values.
- Portfolio-level scenario return and ending value.
- Probability-weighted return and aggregate summaries.
- Risk disclosures.
- Performance metrics (product contrast).
- Suggested portfolio allocation table.

## Design Decisions

### DD1–DD7
Identical to Sprint 1. See `proposal_JSON_output_s1.md` for full descriptions.

- **DD1:** JSON alongside markdown
- **DD2:** Exactly three scenarios (normal, upside, downside)
- **DD3:** Probability suggested, not mandatory
- **DD4:** Instrument assumptions override asset-class assumptions (downstream rule)
- **DD5:** Structured products use hold-to-maturity assumptions
- **DD6:** Strict enums with field mapping (see table below)
- **DD7:** Instrument IDs are catalog-bound

| Enum | Validates JSON Field |
|---|---|
| `proposal_type` | `proposal_type` |
| `scenario_id` | `scenario_set.scenarios[*].scenario_id` |
| `return_convention` | `valuation_context.return_convention` |
| `assumption_type` | `scenario_set.scenarios[*].market_drivers[*].assumption_type` |
| `unit` | `scenario_set.scenarios[*].market_drivers[*].unit` |
| `asset_class` | `scenario_set.scenarios[*].asset_class_returns[*].asset_class` |
| `source` | `scenario_set.scenarios[*].asset_class_returns[*].source` |
| `confidence` | `scenario_set.scenarios[*].instrument_returns[*].confidence` |
| `model_type` | `scenario_set.scenarios[*].instrument_returns[*].return_model.model_type` |
| `valuation_basis` | `scenario_set.scenarios[*].instrument_returns[*].return_model.valuation_basis` |
| `action` | `funding_source[*].action` |

## LLM JSON Schema (v1.0-s2)

The JSON the LLM outputs. Narrative fields added in S2 are marked with `← S2`.

```json
{
  "schema_version": "1.0-s2",
  "proposal_type": "reinvestment",
  "client_id": "PB-HK-000001-8",
  "source_product_id": "USIG-2026",
  "catalog_context": {
    "catalog_version_id": "catalog-2026-07-23-a",
    "catalog_as_of_date": "2026-07-23"
  },
  "valuation_context": {
    "base_currency": "USD",
    "horizon_months": 12,
    "return_convention": "simple_annual",
    "probability_required": false
  },
  "executive_summary": {
    "maturing_product": "US Investment Grade Corporate Bond (maturing Aug 2026)",
    "inflow_amount": 500000,
    "inflow_currency": "USD",
    "recommended_product": "Total Bond Market ETF (BND)",
    "summary_rationale": "Shift from single-name corporate bond to diversified ...",
    "expected_outcome": "Preserve capital with moderate yield ..."
  },
  "client_needs": [
    {
      "need": "Capital Preservation",
      "horizon_years": 3,
      "remark": "Near-term liquidity required; principal stability is primary concern"
    }
  ],
  "recommended_product": {
    "product_id": "ETF-BND",
    "product_name": "Total Bond Market ETF",
    "recommended_amount": 500000,
    "rationale": "Broad diversification across 10,000+ bonds vs single-name credit risk ...",
    "fit_score": 0.87,
    "risk_characteristics": [
      {
        "category": "Credit Risk",
        "detail": "Investment-grade portfolio; low default risk."
      },
      {
        "category": "Market Risk",
        "detail": "Moderate duration (~6 years); sensitive to interest rate movements."
      },
      {
        "category": "Liquidity",
        "detail": "High. ETF trades on-exchange with tight bid-ask spreads."
      }
    ]
  },
  "funding_source": [
    {
      "instrument_id": "USIG-2026",
      "action": "redeem",
      "amount": 500000,
      "note": "Maturing corporate bond releases principal for reinvestment"
    }
  ],
  "pros_and_cons": {
    "pros": [
      "Reduced single-issuer concentration risk through broad diversification",
      "Improved liquidity vs individual corporate bond"
    ],
    "cons": [
      "Modest yield vs equities or high-yield credit",
      "Higher duration sensitivity in rising-rate environment"
    ]
  },
  "alternative_products": [
    {
      "product_id": "ETF-SHY",
      "product_name": "iShares 1-3 Year Treasury Bond ETF",
      "justification": "Shorter duration (1.9 years) offers lower interest-rate sensitivity."
    },
    {
      "product_id": "ETF-USHY",
      "product_name": "iShares Broad USD High Yield Corporate Bond ETF",
      "justification": "Higher yield potential (~8%) compensates for increased credit risk."
    }
  ],
  "scenario_set": {
    "scenario_set_id": "core_3_case_v1",
    "scenarios": [
      {
        "scenario_id": "normal",
        "name": "Normal",
        "description": "Moderate growth, rates range-bound, inflation near target.",
        "probability": 0.60,
        "market_drivers": [
          {
            "driver": "us_10y_cmt",
            "assumption_type": "level",
            "value": 4.50,
            "unit": "pct"
          }
        ],
        "asset_class_returns": [
          { "asset_class": "cash", "return_pct": 3.50, "source": "historical_average", "source_period": "2021-2025" },
          { "asset_class": "fixed_income", "return_pct": 4.50, "source": "historical_average", "source_period": "2021-2025" },
          { "asset_class": "equity", "return_pct": 10.00, "source": "historical_average", "source_period": "2016-2025" }
        ],
        "instrument_returns": [
          {
            "instrument_id": "US3MT",
            "return_pct": 3.50,
            "decomposition": { "income_return_pct": 3.50, "price_return_pct": 0.00 },
            "confidence": "high"
          },
          {
            "instrument_id": "N02952",
            "return_model": {
              "model_type": "range_accrual_coupon",
              "valuation_basis": "hold_to_maturity",
              "inputs": {
                "reference_rate": "us_10y_cmt",
                "accrual_range_min_pct": 0.00,
                "accrual_range_max_pct": 5.01,
                "coupon_when_in_range_pct": 5.94,
                "coupon_when_out_of_range_pct": 0.00,
                "principal_protected_if_held_to_maturity": true
              }
            },
            "resolved_return_pct": 5.94,
            "confidence": "medium"
          }
        ],
        "assumption_rationale": [
          "Rates remain range-bound and coupon accrues in normal conditions."
        ]
      },
      {
        "scenario_id": "upside",
        "name": "Upside",
        "description": "Strong growth, risk-on rally, rates ease.",
        "probability": 0.25,
        "market_drivers": [],
        "asset_class_returns": [],
        "instrument_returns": [],
        "assumption_rationale": []
      },
      {
        "scenario_id": "downside",
        "name": "Downside",
        "description": "Recession or credit event, flight to safety.",
        "probability": 0.15,
        "market_drivers": [],
        "asset_class_returns": [],
        "instrument_returns": [],
        "assumption_rationale": []
      }
    ]
  },
  "references_used": [
    { "name": "client_profile_PB-HK-000001-8_profile.md", "section": "client_profiles" },
    { "name": "selected_etf.csv", "section": "product_catalogs" },
    { "name": "market_outlook.md", "section": "guidelines" }
  ]
}
```

## Strict Enum Definitions

Enums are unchanged from Sprint 1. See `proposal_JSON_output_s1.md` for full definitions.

Additional enum used only in S2:

### `proposal_type`
- reinvestment

### `scenario_id` (exactly 3 required)
- normal
- upside
- downside

### `assumption_type`
- level | period_return | spread | volatility | regime_flag

### `return_convention`
- simple_annual | total_period | annualized_compounded

### `unit`
- pct | bps | index_level | boolean

### `asset_class`
- cash | money_market | fixed_income | investment_grade_credit | high_yield_credit | government_bonds | inflation_linked_bonds | equity | developed_equity | emerging_equity | multi_asset | alternatives | commodities | real_estate | fx

### `source`
- historical_average | historical_stress_window | implied_market | house_view | model_derived

### `confidence`
- high | medium | low

### `model_type` (phase 1)
- range_accrual_coupon | fixed_coupon_note | autocall_note

### `valuation_basis` (phase 1)
- hold_to_maturity

### `action` (funding_source)
- redeem — principal returned involuntarily at maturity
- reduce — partially trim a holding; remaining position stays open
- sell — fully exit a position, zeroing it out

## Validation Rules

1–6 identical to Sprint 1. See `proposal_JSON_output_s1.md`.

**Additional S2 rule:**

7. Narrative field constraints
- `fit_score` is a decimal in range 0.0–1.0. Example: `0.87` means 87/100.
- `pros` and `cons` arrays must each contain at least one entry.
- `alternative_products` should contain 1–2 entries.

## Downstream Proposal Generation Responsibilities

Unchanged from Sprint 1. See `proposal_JSON_output_s1.md`.

## Prompt-Level Output Markers

The LLM response should include:
- Markdown proposal body (all narrative sections as usual).
- Proposal JSON block between:
  - `---** PROPOSAL_JSON **---`
  - `---** END_PROPOSAL_JSON **---`

## Acceptance Criteria (Spec)

| ID | Criterion | Expected |
|---|---|---|
| AC1 | End-to-end JSON validity | Same as Sprint 1 AC1 plus: all S2 narrative fields present when schema_version is `1.0-s2`, `fit_score` in 0.0–1.0 range |
| AC2 | Output boundary | No computed portfolio totals in LLM JSON |
| AC3 | Markdown regression | Markdown proposal output unchanged when JSON extraction succeeds or fails |
| AC4 | S1 backward compatibility | An S1 payload (with narrative fields omitted) remains valid under S2 validation |

## Implementation Notes

### Files to touch

| File | Change |
|---|---|
| `src/planbot/proposal_json_schema.py` | Extend Pydantic model from S1 to include S2 narrative fields |
| `data/planbot/reinvestment_proposal/crewai/tasks.yaml` | Update expected_output to request full JSON per this spec |
| `data/planbot/shared/proposal_section_instructions/scenario_analysis_instruction.md` | Update schema reference block to S2 schema |

### Field population contract (LLM vs inject)

| Field | Populated by | Notes |
|---|---|---|
| `schema_version` | Python (inject) | Always `"1.0-s2"` |
| `proposal_type` | Python (inject) | Known from task config |
| `client_id` | Python (inject) | Known from fan-out binding |
| `catalog_context.*` | Python (inject) | Catalog version metadata |
| `valuation_context.*` | Python (inject) | Known from task config defaults |
| `source_product_id` | Python (inject) | Known from client input |
| `executive_summary.*` | LLM | Narrative decisions |
| `client_needs.*` | LLM | Inferred from client profile |
| `recommended_product.*` | LLM | Full product detail including risk_characteristics |
| `funding_source.*` | LLM | Which holdings are sold/trimmed |
| `pros_and_cons.*` | LLM | Narrative decisions |
| `alternative_products.*` | LLM | 1–2 alternatives with justification |
| `scenario_set.*` | LLM | Scenario return assumptions |
| `references_used.*` | LLM | References actually used during evaluation |

## Migration from S1 to S2

1. Update `schema_version` injection from `"1.0-s1"` to `"1.0-s2"`.
2. Extend Pydantic model with narrative fields (all `Optional` for backward compatibility).
3. Update task prompt to request narrative fields in JSON.
4. Validate that S1 payloads still pass S2 validation (AC4).

## References
- docs/prod_spec/proposal_JSON_output_s1.md (Sprint 1 base spec)
- data/planbot/shared/proposal_section_instructions/scenario_analysis_instruction.md
- docs/prod_spec/product_catalog/product_catalog.md
