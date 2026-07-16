Product Investor Matching Proposal API Refactor
===============================================

## Overview

The current product investor matching proposal is generated from static files only. Please refer to `config/config_planbot.yaml` for the current execution. The spec is to refactor the proposal generation flow so that all client, holding, and product data are retrieved through remote FastAPI endpoints.

A similar implementation has been done for the reinvestment proposal.  Please refer to `docs/prod_spec/reinvestment_proposal_api.md` for more information.

The goals are:

1. Replace file-based client and product inputs with API-backed retrieval.
2. Preserve the current proposal output structure and quality.
3. Keep the proposal generator callable as a local Python function while using remote FastAPI calls for client/product retrieval.
4. Make the API contract stable enough that the same payload can be used by local callers and remote callers.

It does not redesign the proposal text itself, only how the input data are gathered and assembled for the LLM.

## Scope

### In scope

- Product-client matching proposal generation for one or more target clients.
- API-first retrieval for client profile, holdings, and product catalog data.
- Product search/filter API enhancement for richer screening conditions.
- Deterministic matching score generation before LLM narrative generation.
- Local Python entry point and FastAPI endpoint using the same payload schema.

### Out of scope

- Redesign of proposal writing style or output section names.
- UI development.
- Rebuilding client or product master-data services.
- Advanced optimization (parallel fan-out, compact prompt serialization) in this initial phase.

## Current state and problem

- Current flow relies on static files for client and product context.
- Product screening criteria are constrained and not uniformly expressed.
- The proposal writer and data retrieval concerns are coupled, making migration and testing harder.

## Target outcomes

1. Proposal generation can be triggered with only API data dependencies.
2. Product pre-screening supports categorical lists and numeric ranges consistently.
3. Matching scorecards are reproducible and available for debug/trace.
4. The same business payload can be used for both local and remote invocation.

# Dataflow

Please refer to `docs/prod_spec/product_client_matching.d2` for the data flow of this proposal

## Initial design

### End-to-end flow

1. Receive request containing client targets and product screening constraints.
2. Retrieve client profile and holdings from client API.
3. Retrieve candidate products from product API via enhanced search contract.
4. Build product fitness scorecard per (client, product) pair.
5. Select top-N products per client after filtering and ranking.
6. Build `llm_input` payload with client, scorecards, candidate products, and market context.
7. Generate final proposal markdown using existing prompt template.
8. Return output according to response mode (`path`, `markdown`, `both`) with optional debug blocks.

### Service boundaries

- Matching proposal service owns orchestration, scorecard assembly, and LLM input construction.
- Client API owns client profile and holdings retrieval.
- Product API owns searchable product catalog and product metadata.
- FastAPI wrapper stays thin and delegates to the local Python builder.

### Core modules (logical)

- Request validator
- Client context retriever
- Product candidate retriever
- Matching score engine
- LLM input builder
- Proposal renderer
- Response formatter

## Python API design

### `generate_product_client_fit_proposal(...)`

Suggested signature:

```python
generate_product_client_fit_proposal(
		client_ids: list[str],
		product_filters: dict | None = None,
		top_n_per_client: int = 10,
		min_match_score: float | None = None,
		response_mode: str = "path",  # one of: path, markdown, both
		include_llm_input: bool = False,
		include_debug_scores: bool = False,
		include_market_outlook: bool = True,
) -> dict
```

### Input fields

- `client_ids`: one or more client IDs.
- `product_filters`: search constraints sent to product search API.
- `top_n_per_client`: max shortlisted products per client.
- `min_match_score`: optional threshold to suppress weak matches.
- `response_mode`: `path`, `markdown`, or `both`.
- `include_llm_input`: include assembled LLM context in output when true.
- `include_debug_scores`: include scorecard breakdown and filtering trace when true.
- `include_market_outlook`: include market references in context when true.

### Output fields

- `status`
- `results_by_client`: list of per-client results with:
	- `client_id`
	- `candidate_products`
	- `matching_scores`
	- `output_path` when response mode includes `path`
	- `markdown_output` when response mode includes `markdown`
	- `llm_input` when `include_llm_input = true`
	- `debug_scores` when `include_debug_scores = true`
- `errors`: optional list for partial failures

## FastAPI contract

### Endpoints

- `POST /api/v1/product-client-fit-proposals`
- `POST /api/v1/products/search` (enhanced filter contract)

### Proposal request body (example)

```json
{
	"client_ids": ["PB-HK-000001-8", "PB-HK-000002-6"],
	"product_filters": {
		"risk_rating": [2, 3, 4],
		"expected_return": {"min": 0.03, "max": 0.08},
		"product_type": ["bond", "etf"],
		"asset_class": ["fixed_income"],
		"region": ["APAC", "Global"],
		"sector": ["Financials", "Utilities"],
		"time_to_maturity": {"min": "6m", "max": "5y"},
		"coupon": {"min": 0.02, "max": 0.07},
		"trade_date": "2026-07-16"
	},
	"top_n_per_client": 10,
	"min_match_score": 6.5,
	"response_mode": "path",
	"include_llm_input": false,
	"include_debug_scores": false,
	"include_market_outlook": true
}
```

### Proposal response body (example)

```json
{
	"status": "success",
	"results_by_client": [
		{
			"client_id": "PB-HK-000001-8",
			"candidate_products": [
				{"product_id": "BOND-XYZ", "match_score": 8.2}
			],
			"matching_scores": [
				{"product_id": "BOND-XYZ", "fit": 8.2, "readiness": 7.8}
			],
			"output_path": "runs/client_product_fit_analysis/PB-HK-000001-8.md"
		}
	]
}
```

## Tasks

### Product tool enhancement

Add a search API that able to search by below

- `risk_rating`
- `expected_return`
- `product_type`
- `asset_class`
- `region`
- `sector` (mapped to `sector` in products table)
- `time_to_maturity` — accepted in d, w, m, y
- `coupon` — dividend of a MF/ETF, coupon for bond
- `trade_date` — default to system date if not specified; used to compute `time_to_maturity`

Note below

- categoric value accepts list.
- numeric attribute shall accept range

### Product search filter semantics

- Categorical fields (`risk_rating`, `product_type`, `asset_class`, `region`, `sector`) accept single value or list.
- Numeric fields (`expected_return`, `coupon`) accept exact or range object (`min`, `max`).
- `time_to_maturity` accepts exact or range with unit suffix (`d`, `w`, `m`, `y`).
- `trade_date` defaults to server system date if omitted.
- Invalid range (`min > max`) must return validation error.

### Product search response (minimum)

- `products`: list of matched products with key attributes used for scoring.
- `applied_filters`: normalized filter object after default handling.
- `total_count`: count of matched products before shortlist trimming.

## LLM input contract

`llm_input` should be deterministic JSON in this initial phase.

Required blocks:

1. Client profile summary.
2. Holdings summary and concentration indicators.
3. Candidate product summaries.
4. Matching scorecard results and rationale.
5. Market outlook snippets (optional by flag).
6. Proposal output instruction block.

## Error handling and observability

- Per-client failure should not fail the whole batch unless no client succeeds.
- Return partial success with `errors` entries containing `client_id`, `code`, and `message`.
- Log request correlation ID and per-client processing stage.
- No `print` statements; use module-level Python logging.

## Test strategy

- Unit tests (mock APIs) for normal and exception flows.
- Contract tests for request validation and response shape.
- Integration test for endpoint -> builder path with representative payload.
- Snapshot test for `llm_input` required blocks and non-empty required proposal sections.

## Acceptance criteria

| # | Criterion | Verification |
|---|---|---|
| AC1 | Proposal generation runs from a Python function without reading static client/product files | Unit test with file-reader mocks asserting not called |
| AC2 | Builder retrieves client data through client API contract only | Unit test with mocked client API and call assertions |
| AC3 | Builder retrieves product data through enhanced product search API contract only | Unit test with mocked product API and call assertions |
| AC4 | Product search accepts categorical lists and numeric ranges for specified fields | Contract test with valid request examples |
| AC5 | `time_to_maturity` supports `d`, `w`, `m`, `y` and computes against `trade_date` defaulting to system date | Unit tests for parsing and default-date behavior |
| AC6 | Invalid filter payloads return explicit validation errors (including invalid ranges) | Negative contract tests |
| AC7 | Matching score output contains deterministic per-client, per-product score entries | Snapshot/unit test with fixed fixtures |
| AC8 | Proposal endpoint supports `path`, `markdown`, and `both` response modes | Endpoint integration tests for each mode |
| AC9 | Optional blocks are controlled by flags (`include_llm_input`, `include_debug_scores`, `include_market_outlook`) | Unit test matrix |
| AC10 | Required proposal sections are present and non-empty in generated markdown | Content validation test against required headers |
| AC11 | Batch request supports partial success and returns per-client errors without dropping successful clients | Integration test with mixed valid/invalid clients |
| AC12 | Logging uses Python logging module and records correlation ID and stage transitions | Unit test with log capture |

## Open decisions

1. Whether minimum score threshold is fixed in config or fully caller-controlled.
2. Whether market outlook retrieval remains local reference loading or moves to API in this phase.
3. Whether debug score schema should align exactly with current investor readiness score artifact format.

## Recommended initial implementation order

1. Define and validate request/response models.
2. Implement product search filter normalization and validation.
3. Implement builder orchestration with mocked API adapters.
4. Add endpoint wrapper and response-mode handling.
5. Add tests for AC1 to AC12 before broad rollout.

