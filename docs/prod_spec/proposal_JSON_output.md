# Proposal JSON Output Specification

## Version
- Spec version: 1.0
- Date: 2026-07-23
- Scope: Reinvestment proposal flow first, extensible to other proposal types later.

## Objective
Define a structured JSON payload produced by LLM that can be consumed by a downstream proposal generation system without parsing markdown narrative.

The payload must carry:
- LLM decision and rationale fields.
- Scenario assumptions at market, asset-class, and instrument level.

The payload must not carry:
- Computed portfolio totals.
- Computed scenario ending values.
- Computed expected (probability-weighted) portfolio return.

## Two-Stage Architecture

1. Stage 1 (LLM)
- Inputs: client profile, product catalog snapshot, guidelines, prompt instructions.
- Outputs: markdown proposal + JSON payload.
- JSON content: assumptions and rationale only.

2. Stage 2 (Downstream proposal generation)
- Inputs: LLM JSON + raw holdings + same-version product catalog snapshot.
- Outputs: enriched markdown proposal (or structured output) with:
  - Deterministic scenario valuation (product-level PnL, portfolio returns, ending values).
  - Risk disclosures assembled from product metadata and regulatory templates.
  - Performance metrics derived from the product catalog (CAGR, volatility, yield, drawdown).
  - Probability-weighted return and aggregate summaries.

## Contract Boundaries

### LLM-owned fields
- Recommended product, allocation amount, and narrative rationale.
- Recommended product risk characteristics.
- Alternative product suggestions and justification.
- Funding source description (what is sold/trimmed to fund the recommendation).
- Client needs inferred from the client profile.
- Scenario assumptions (returns, drivers, confidence, data source labels).
- Structured product hold-to-maturity assumption metadata.

### Scenario field semantics
- `name` — Display label for the scenario (e.g., "Normal", "Upside — Soft Landing").
- `description` — 1-3 sentence qualitative summary of the macro backdrop and key themes driving the assumptions (e.g., "Moderate growth, rates range-bound, inflation near target."). This is the narrative that sets context for why the assumptions are what they are.
- `assumption_rationale` — Bullet-point justification for individual assumption choices (e.g., "Rates remain range-bound and coupon accrues…").

### Downstream-owned fields
- Product-level PnL values.
- Portfolio-level scenario return and ending value.
- Probability-weighted return and aggregate summaries.
- Risk disclosures.
- Performance metrics (product contrast).

## Design Decisions

### DD1: JSON alongside markdown
The pipeline remains markdown-compatible, with JSON extracted as a machine-readable companion output.

### DD2: Exactly three scenarios
The scenario contract in v1.0 uses exactly three scenarios:
- normal
- upside
- downside

### DD3: Probability suggested, not mandatory
- Probability is recommended when justified.
- If any scenario includes probability, all three scenarios must include probability.
- If present, probabilities must sum to 1.0 (tolerance 0.001).
- If absent, downstream computes per-scenario outputs without expected-value metrics.

### DD4: Instrument assumptions override asset-class assumptions
If both assumptions are provided for an instrument:
- instrument-level return wins
- asset-class return is fallback only

This is a downstream valuation rule (see Downstream Proposal Generation Responsibilities). The LLM does not need to enforce it.

### DD5: Structured products use hold-to-maturity assumptions in this phase
Structured product scenario assumptions are hold-to-maturity only until more sophisticated pricing is introduced.

### DD6: Strict enums for deterministic downstream parsing
All enumerated fields in this document are strict. Unknown enum values are invalid payloads. Each enum maps to a specific JSON field as follows:

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

Enforcement is at extraction time via Pydantic `Literal` types. Any field value not in the allowed set causes validation failure → `llm_json = None`, markdown-only fallback.

### DD7: Instrument IDs are catalog-bound
Instrument IDs in scenario assumptions must come from the same product catalog snapshot version used to generate the proposal.

## LLM JSON Schema (v1.0)

```json
{
  "schema_version": "1.0",
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
        "detail": "Investment-grade portfolio; low default risk. Not subject to single-issuer concentration."
      },
      {
        "category": "Market Risk",
        "detail": "Moderate duration (~6 years); sensitive to interest rate movements. Diversified holdings mitigate idiosyncratic risk."
      },
      {
        "category": "Liquidity",
        "detail": "High. ETF trades on-exchange with tight bid-ask spreads. Daily redemptions available."
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
      "justification": "Shorter duration (1.9 years) offers lower interest-rate sensitivity and higher capital stability. Suitable if the client prioritizes capital preservation over total return."
    },
    {
      "product_id": "ETF-USHY",
      "product_name": "iShares Broad USD High Yield Corporate Bond ETF",
      "justification": "Higher yield potential (~8%) compensates for increased credit risk. Suitable if the client can accept moderate drawdowns for income enhancement."
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
  },
  "references_used": [
    {
      "name": "client_profile_PB-HK-000001-8_profile.md",
      "section": "client_profiles"
    },
    {
      "name": "selected_etf.csv",
      "section": "product_catalogs"
    },
    {
      "name": "market_outlook.md",
      "section": "guidelines"
    }
  ]
}
```

## Strict Enum Definitions

### `proposal_type`
- reinvestment

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
- `schema_version` must be `1.0`.
- `scenario_set.scenarios` must contain exactly three entries.
- Required `scenario_id` set must be exactly `{normal, upside, downside}`.

2. Probability rules
- Probability is optional.
- If any probability is present, all three must be present.
- When present, total probability must be 1.0 with tolerance 0.001.

3. Units and return conventions
- All `return_pct` and pct-based driver values are percentages, not decimals.
- Example: `5.94` means `5.94%`, not `0.0594`.
- `fit_score` is a decimal in range 0.0–1.0. Example: `0.87` means 87/100.

4. Instrument ID governance
- Every `instrument_returns[].instrument_id` must exist as `product_id` in the catalog identified by:
  - `catalog_context.catalog_version_id`
  - `catalog_context.catalog_as_of_date`
- Unknown instrument ID is invalid.
- Duplicate instrument ID in the same scenario is invalid.

5. Structured product constraint
- Structured product assumptions must use `valuation_basis = hold_to_maturity` in phase 1.
- Mark-to-market pricing fields are out of scope and should be rejected.

6. LLM output boundary
- LLM JSON must not include computed portfolio-level totals, ending values, or probability-weighted portfolio metrics.

## Downstream Proposal Generation Responsibilities

The downstream system produces the enriched proposal output from the LLM JSON plus catalog and holdings data. Its responsibilities fall into three categories:

### Deterministic valuation (scenario engine)
- Product-level PnL: `start_value * return_pct / 100`.
- Portfolio scenario return: weighted return sum over current and suggested holdings.
- Scenario ending value: `start_portfolio_value * (1 + portfolio_return_pct / 100)`.
- Probability-weighted expected return: `sum(probability * scenario_portfolio_return_pct)`, only when scenario probabilities are provided.
- **Precedence rule:** Instrument-level `return_pct` overrides asset-class `return_pct` when both exist for the same instrument. If instrument-level assumption is missing, fall back to the asset-class return.

### Risk disclosures
- Assemble regulatory boilerplate from product metadata (structured product warnings, deposit scheme disclaimers, principal-at-risk statements).
- Conditionally include product-specific risk notes (credit risk, liquidity risk, callable features).

### Performance metrics (product contrast)
- Derive from the product catalog: CAGR, volatility, max drawdown, yield for both the source product and recommended product.
- Produce side-by-side comparison table for the enriched output.

### Suggested portfolio allocation
- Compute the full per-holding table (current MV, suggested MV, weight, delta, remark per line) from the current holdings data + `recommended_product.recommended_amount`.
- No additional LLM-owned field needed.

These computed outputs are assembled alongside the LLM markdown narrative to produce the complete proposal.

## Prompt-Level Output Markers

The LLM response should include:
- Markdown proposal body.
- Proposal JSON block between:
  - `---** PROPOSAL_JSON **---`
  - `---** END_PROPOSAL_JSON **---`

## Acceptance Criteria (Spec)

| ID | Criterion | Expected |
|---|---|---|
| AC1 | End-to-end JSON validity | Payload parses as valid JSON, `schema_version = 1.0`, contains exactly 3 scenarios with IDs `normal`/`upside`/`downside`, all enum fields within allowed values, all `return_pct` fields are percentages (e.g. `5.94` means 5.94%, not 0.0594), structured product assumptions use `valuation_basis = hold_to_maturity` only, probabilities optional but consistent if present (all-or-nothing, sum to 1.0 ±0.001), no duplicate `instrument_id` within a scenario, and all `instrument_id` values resolve to valid `product_id` entries in the same-version catalog |
| AC2 | Output boundary | No computed portfolio totals in LLM JSON |
| AC3 | Markdown regression | Markdown proposal output unchanged (all existing sections present, no content regression) when JSON extraction succeeds or fails |

## Implementation Notes

This section is non-normative guidance for the implementation phase.

### Files to touch

| File | Change |
|---|---|
| `src/planbot/proposal_json_schema.py` (new) | Pydantic model matching this spec for extraction-time validation |
| `data/planbot/reinvestment_proposal/crewai/tasks.yaml` | Add `SCENARIO_JSON` marker instruction to `expected_output` |
| `data/planbot/shared/proposal_section_instructions/scenario_analysis_instruction.md` | Already updated; verify reference points to `proposal_JSON_output.md` |
| `src/planbot/workflow.py` | Add `extract_proposal_json_from_llm_output()` helper (parses `---** PROPOSAL_JSON **---` delimiter) |
| `src/planbot/crew_workflow.py` | Call extraction after LLM response; store result in `PlanBotResult` |
| `src/integrations/reinvestment_proposal.py` | Pass `scenario_json` through to API response |
| `src/integrations/server.py` | Include `scenario_json` in FastAPI response body |
| `tests/test_reinvestment_proposal.py` | Unit tests for extraction (valid, missing, malformed) and integration test for API passthrough |

### How the JSON schema reaches the LLM

The LLM receives the schema contract as part of its prompt input. The schema is injected via the scenario analysis instruction file.

Append a condensed schema reference block to `data/planbot/shared/proposal_section_instructions/scenario_analysis_instruction.md` containing:
- The example JSON from the `## LLM JSON Schema (v1.0)` section above.
- The `## Strict Enum Definitions` section in full (the LLM needs to know allowed enum values).
- A bullet list of the validation rules, condensed to 1-line each.

### Extraction and graceful degradation

The parser (`extract_proposal_json_from_llm_output()`) should:
- Locate the `---** PROPOSAL_JSON **---` / `---** END_PROPOSAL_JSON **---` delimiters.
- Parse the content between them as JSON.
- Validate against the Pydantic model (strict enum checking).
- Return `None` if extraction or validation fails — the markdown proposal still succeeds.

### Field population contract (LLM vs pre-fill)

Some fields are pre-filled by Python before the JSON reaches downstream, reducing LLM hallucination risk. The LLM is instructed NOT to output these fields. After extraction, Python injects them into the LLM's partial JSON to produce the complete payload:

| Field | Populated by | Notes |
|---|---|---|
| `schema_version` | Python (inject) | Always `"1.0"` until spec changes |
| `proposal_type` | Python (inject) | Known from task config |
| `client_id` | Python (inject) | Known from fan-out binding |
| `catalog_context.*` | Python (inject) | Inject catalog version metadata from the run |
| `valuation_context.*` | Python (inject) | Known from task config defaults |
| `source_product_id` | Python (inject) | Known from client input |
| `client_needs.*` | LLM | LLM infers needs from client profile (primarily portfolio_review; optional for reinvestment) |
| `executive_summary.*` | LLM | Narrative decisions |
| `recommended_product.*` | LLM | Narrative decisions; includes risk_characteristics |
| `pros_and_cons.*` | LLM | Narrative decisions |
| `alternative_products.*` | LLM | LLM suggests 1–2 alternatives with justification |
| `funding_source.*` | LLM | LLM describes which holdings are sold/trimmed |
| `scenario_set.*` | LLM | Scenario assumptions (the core LLM-owned output) |
| `references_used.*` | LLM | LLM declares which references it actually used during evaluation |

## References
- data/planbot/shared/proposal_section_instructions/scenario_analysis_instruction.md
- docs/prod_spec/product_catalog/product_catalog.md
