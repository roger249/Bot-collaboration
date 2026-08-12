# Proposal JSON Output Specification — Sprint 1 (Minimal)

## Version
- Spec version: 1.0-s1
- Date: 2026-07-24
- Scope: Reinvestment proposal flow first. JSON carries only fields required by the downstream proposal generation system. All narrative stays in markdown.

## Objective
Define a minimal structured JSON payload produced by LLM that enables deterministic portfolio valuation without parsing markdown. The JSON carries only what the downstream engine cannot compute or infer on its own.

The payload must carry:
- Recommended product identity and allocation amount.
- Funding source (what was sold/trimmed to fund the recommendation).
- Scenario return assumptions at market, asset-class, and instrument level.

The payload must not carry:
- Computed portfolio totals.
- Computed scenario ending values.
- Computed expected (probability-weighted) portfolio return.
- Narrative content (executive summary, rationale, pros/cons, risk characteristics, alternatives) — these stay in markdown.

## Two-Stage Architecture

1. Stage 1 (LLM)
- Inputs: client profile, product catalog snapshot, guidelines, prompt instructions.
- Outputs: markdown proposal + minimal JSON payload.
- JSON content: computation-required fields only.

2. Stage 2 (Downstream proposal generation)
- Inputs: LLM JSON + raw holdings + same-version product catalog snapshot.
- Outputs: enriched markdown proposal with:
  - Deterministic scenario valuation (product-level PnL, portfolio returns, ending values).
  - Risk disclosures assembled from product metadata and regulatory templates.
  - Performance metrics derived from the product catalog (CAGR, volatility, yield, drawdown).
  - Suggested portfolio allocation computed from `recommended_amount` + current holdings.
  - Probability-weighted return and aggregate summaries.

## Contract Boundaries

### LLM-owned fields
- Recommended product identity and allocation amount.
- Funding source description (what is sold/trimmed to fund the recommendation).
- Scenario assumptions (returns, drivers, confidence, data source labels).
- Structured product hold-to-maturity assumption metadata.

### Python-injected fields
These are NOT output by the LLM. After extraction, Python merges them into the payload:

| Field | Source |
|---|---|
| `schema_version` | Always `"1.0-s1"` |
| `proposal_type` | Known from task config |
| `client_id` | Known from fan-out binding |
| `catalog_context.*` | Catalog version metadata from the run |
| `valuation_context.*` | Known from task config defaults |
| `source_product_id` | Known from client input |

### Scenario field semantics
- `name` — Display label for the scenario (e.g., "Normal", "Upside — Soft Landing").
- `description` — 1-3 sentence qualitative summary of the macro backdrop and key themes driving the assumptions.
- `assumption_rationale` — Bullet-point justification for individual assumption choices.

### Downstream-owned fields
- Product-level PnL values.
- Portfolio-level scenario return and ending value.
- Probability-weighted return and aggregate summaries.
- Risk disclosures.
- Performance metrics (product contrast).
- Suggested portfolio allocation table.
- All narrative sections (executive summary, product rationale, pros/cons, alternatives, client needs, references).

## Design Decisions

### DD1: JSON alongside markdown
The pipeline remains markdown-compatible, with JSON extracted as a machine-readable companion output. Narrative lives only in markdown.

### DD2: Exactly three scenarios
- normal
- upside
- downside

### DD3: Probability suggested, not mandatory
- Probability is recommended when justified.
- If any scenario includes probability, all three scenarios must include probability.
- If present, probabilities must sum to 1.0 (tolerance 0.001).
- If absent, downstream computes per-scenario outputs without expected-value metrics.

### DD4: Instrument assumptions override asset-class assumptions
Instrument-level `return_pct` overrides asset-class `return_pct` when both exist for the same instrument. Fallback is downstream behavior; the LLM does not need to enforce it.

### DD5: Structured products use hold-to-maturity assumptions in this phase
Structured product scenario assumptions are hold-to-maturity only until more sophisticated pricing is introduced.

### DD6: Strict enums for deterministic downstream parsing
All enumerated fields are strict. Unknown enum values cause validation failure → `llm_json = None`, markdown-only fallback.

| Enum | Validates JSON Field |
|---|---|
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

### DD7: Instrument IDs are catalog-bound
Instrument IDs in scenario assumptions must come from the same product catalog snapshot version used to generate the proposal.

## LLM JSON Schema (v1.0-s1)

The JSON the LLM outputs. Python-injected fields are shown here for completeness — the LLM only produces `recommended_product`, `funding_source`, and `scenario_set`.

```json
{
  "schema_version": "1.0-s1",
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
  "recommended_product": {
    "product_id": "ETF-BND",
    "recommended_amount": 500000
  },
  "funding_source": [
    {
      "instrument_id": "USIG-2026",
      "action": "redeem",
      "amount": 500000,
      "note": "Maturing corporate bond releases principal for reinvestment"
    }
  ],
  "scenario_set": {
    "scenario_set_id": "core_3_case_v1",
    "scenarios": [
      {
        "scenario_id": "normal",
        "name": "Normal",
        "description": "Moderate growth, rates range-bound, inflation near target. Equities deliver long-run average returns; credit spreads stable.",
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
          {
            "asset_class": "cash",
            "return_pct": 3.50,
            "source": "historical_average",
            "source_period": "2021-2025"
          },
          {
            "asset_class": "fixed_income",
            "return_pct": 4.50,
            "source": "historical_average",
            "source_period": "2021-2025"
          },
          {
            "asset_class": "equity",
            "return_pct": 10.00,
            "source": "historical_average",
            "source_period": "2016-2025"
          }
        ],
        "instrument_returns": [
          {
            "instrument_id": "US3MT",
            "return_pct": 3.50,
            "decomposition": {
              "income_return_pct": 3.50,
              "price_return_pct": 0.00
            },
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
          "Rates remain range-bound and coupon accrues in normal conditions.",
          "Asset class assumptions follow historical averages with conservative adjustment."
        ]
      },
      {
        "scenario_id": "upside",
        "name": "Upside",
        "description": "Strong growth, risk-on rally, rates ease. Equity multiples expand; credit spreads compress.",
        "probability": 0.25,
        "market_drivers": [],
        "asset_class_returns": [],
        "instrument_returns": [],
        "assumption_rationale": []
      },
      {
        "scenario_id": "downside",
        "name": "Downside",
        "description": "Recession or credit event, flight to safety. Equities sell off; credit spreads widen; Treasuries rally.",
        "probability": 0.15,
        "market_drivers": [],
        "asset_class_returns": [],
        "instrument_returns": [],
        "assumption_rationale": []
      }
    ]
  }
}
```

## Strict Enum Definitions

### `scenario_id` (exactly 3 required)
- normal
- upside
- downside

### `assumption_type`
- level
- period_return
- spread
- volatility
- regime_flag

### `return_convention`
- simple_annual
- total_period
- annualized_compounded

### `unit`
- pct
- bps
- index_level
- boolean

### `asset_class`
- cash
- money_market
- fixed_income
- investment_grade_credit
- high_yield_credit
- government_bonds
- inflation_linked_bonds
- equity
- developed_equity
- emerging_equity
- multi_asset
- alternatives
- commodities
- real_estate
- fx

### `source`
- historical_average
- historical_stress_window
- implied_market
- house_view
- model_derived

### `confidence`
- high
- medium
- low

### `model_type` (phase 1)
- range_accrual_coupon
- fixed_coupon_note
- autocall_note

### `valuation_basis` (phase 1)
- hold_to_maturity

### `action` (funding_source)
- redeem — principal returned involuntarily at maturity (bond matures, note called)
- reduce — partially trim a holding; remaining position stays open
- sell — fully exit a position, zeroing it out

## Validation Rules

1. Core shape
- `schema_version` must be `1.0-s1`.
- `scenario_set.scenarios` must contain exactly three entries.
- Required `scenario_id` set must be exactly `{normal, upside, downside}`.

2. Probability rules
- Probability is optional.
- If any probability is present, all three must be present.
- When present, total probability must be 1.0 with tolerance 0.001.

3. Units and return conventions
- All `return_pct` and pct-based driver values are percentages, not decimals.
- Example: `5.94` means `5.94%`, not `0.0594`.

4. Instrument ID governance
- Every `instrument_returns[].instrument_id` must exist as `product_id` in the catalog identified by `catalog_context.*`.
- Unknown instrument ID is invalid.
- Duplicate instrument ID in the same scenario is invalid.

5. Structured product constraint
- Structured product assumptions must use `valuation_basis = hold_to_maturity` in phase 1.
- Mark-to-market pricing fields are out of scope and should be rejected.

6. LLM output boundary
- LLM JSON must not include computed portfolio-level totals, ending values, or probability-weighted portfolio metrics.

## Downstream Proposal Generation Responsibilities

The downstream system produces the enriched proposal output from the LLM JSON plus catalog and holdings data. Its responsibilities:

### Deterministic valuation (scenario engine)
- Product-level PnL: `start_value * return_pct / 100`.
- Portfolio scenario return: weighted return sum over current and suggested holdings.
- Scenario ending value: `start_portfolio_value * (1 + portfolio_return_pct / 100)`.
- Probability-weighted expected return: `sum(probability * scenario_portfolio_return_pct)`, only when scenario probabilities are provided.
- **Precedence rule:** Instrument-level `return_pct` overrides asset-class `return_pct` when both exist. Fall back to asset-class return if instrument-level is missing.

### Risk disclosures
- Assemble regulatory boilerplate from product metadata (structured product warnings, deposit scheme disclaimers, principal-at-risk statements).
- Conditionally include product-specific risk notes.

### Performance metrics (product contrast)
- Derive from the product catalog: CAGR, volatility, max drawdown, yield for both source and recommended product.

### Suggested portfolio allocation
- Compute full per-holding table (current MV, suggested MV, weight, delta, remark) from current holdings + `recommended_product.recommended_amount`.

These computed outputs are assembled alongside the LLM markdown narrative to produce the complete proposal.

## Prompt-Level Output Markers

The LLM response should include:
- Markdown proposal body (all narrative sections as usual).
- Proposal JSON block between:
  - `---** PROPOSAL_JSON **---`
  - `---** END_PROPOSAL_JSON **---`

## Acceptance Criteria (Spec)

| ID | Criterion | Expected |
|---|---|---|
| AC1 | End-to-end JSON validity | Payload parses as valid JSON, `schema_version = 1.0-s1`, contains exactly 3 scenarios with IDs `normal`/`upside`/`downside`, all enum fields within allowed values, all `return_pct` fields are percentages, structured product assumptions use `valuation_basis = hold_to_maturity` only, probabilities optional but consistent if present, no duplicate `instrument_id` within a scenario, and all `instrument_id` values resolve to valid `product_id` entries in the same-version catalog |
| AC2 | Output boundary | No computed portfolio totals in LLM JSON |
| AC3 | Markdown regression | Markdown proposal output unchanged (all existing sections present, no content regression) when JSON extraction succeeds or fails |
| AC4 | Minimal output | LLM JSON contains only `recommended_product`, `funding_source`, and `scenario_set` as LLM-owned fields — no narrative fields |

## Implementation Notes

### Files to touch

| File | Change |
|---|---|
| `src/planbot/proposal_json_schema.py` (new) | Pydantic model matching this spec for extraction-time validation |
| `data/planbot/reinvestment_proposal/crewai/tasks.yaml` | Add `PROPOSAL_JSON` marker instruction to `expected_output` |
| `data/planbot/shared/proposal_section_instructions/scenario_analysis_instruction.md` | Append condensed schema reference block |
| `src/planbot/workflow.py` | Add `extract_proposal_json_from_llm_output()` helper |
| `src/planbot/crew_workflow.py` | Call extraction after LLM response; store result in `PlanBotResult` |
| `src/integrations/reinvestment_proposal.py` | Pass `proposal_json` through to API response |
| `src/integrations/server.py` | Include `proposal_json` in FastAPI response body |
| `tests/test_reinvestment_proposal.py` | Unit tests for extraction (valid, missing, malformed) and integration test for API passthrough |

### How the JSON schema reaches the LLM

The LLM receives the schema contract via the scenario analysis instruction file. Append the following to `scenario_analysis_instruction.md`:
- The example JSON from `## LLM JSON Schema (v1.0-s1)`.
- The `## Strict Enum Definitions` section in full.
- A bullet list of the validation rules, condensed to 1-line each.

### Extraction and graceful degradation

The parser (`extract_proposal_json_from_llm_output()`) should:
- Locate `---** PROPOSAL_JSON **---` / `---** END_PROPOSAL_JSON **---` delimiters.
- Parse JSON content.
- Validate against the Pydantic model (strict enum checking).
- Return `None` if extraction or validation fails — the markdown proposal still succeeds.

### Field population contract (LLM vs inject)

| Field | Populated by | Notes |
|---|---|---|
| `schema_version` | Python (inject) | Always `"1.0-s1"` |
| `proposal_type` | Python (inject) | Known from task config |
| `client_id` | Python (inject) | Known from fan-out binding |
| `catalog_context.*` | Python (inject) | Catalog version metadata |
| `valuation_context.*` | Python (inject) | Known from task config defaults |
| `source_product_id` | Python (inject) | Known from client input |
| `recommended_product.*` | LLM | `product_id` + `recommended_amount` only |
| `funding_source.*` | LLM | Which holdings are sold/trimmed |
| `scenario_set.*` | LLM | Scenario return assumptions |

## Sprint 2 Preview

Sprint 2 (see `proposal_JSON_output_s2.md`) extends this contract by adding narrative fields (`executive_summary`, `pros_and_cons`, `alternative_products`, `client_needs`, `references_used`, and extended `recommended_product` fields) to the JSON. The sprint 1 contract remains a valid subset.

## References
- data/planbot/shared/proposal_section_instructions/scenario_analysis_instruction.md
- docs/prod_spec/product_catalog/product_catalog.md
- docs/prod_spec/proposal_JSON_output_s2.md
