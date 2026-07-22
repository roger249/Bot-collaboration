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
5. Accept pre-selected product lists as API input; product selection logic is out of scope for this service.

It does not redesign the proposal text itself, only how the input data are gathered and assembled for the LLM.

## Scope

### In scope

- Product-client matching proposal generation for one or more target clients.
- API-first retrieval for client profile, holdings, and product catalog data.
- Accepting pre-selected product IDs as part of the request payload.
- Supporting two invocation modes: direct `client_ids` and helper client discovery.
- Deterministic matching score generation before LLM narrative generation.
- Local Python entry point and FastAPI endpoint using the same payload schema.

### Out of scope

- Redesign of proposal writing style or output section names.
- UI development.
- Rebuilding client or product master-data services.
- Product discovery or product pre-selection logic.
- Advanced optimization (parallel fan-out, compact prompt serialization) in this initial phase.

## Current state and problem

- Current flow relies on static files for client and product context.
- Product selection logic is currently mixed into proposal generation concerns.
- The proposal writer and data retrieval concerns are coupled, making migration and testing harder.

## Target outcomes

1. Proposal generation can be triggered with only API data dependencies.
2. Product list is passed in from upstream selection logic and reused as-is.
3. Matching scorecards are reproducible and available for debug/trace.
4. The same business payload can be used for both local and remote invocation.
5. Callers can choose either explicit client IDs or helper-based client discovery.

## API boundary

Boundary definition for this module:

- This module accepts only:
	- selected products (`candidate_product_ids`) from upstream selector logic, and
	- either explicit `client_ids` or helper discovery criteria.
- This module owns:
	- client enrichment retrieval,
	- PFS/matching score computation,
	- proposal generation and formatting.
- This module does not own:
	- product discovery/selection,
	- UI-driven shortlist logic,
	- bank campaign logic for promoted/top-selling product generation.

### End-to-end flow

Please refer to `docs/prod_spec/product_client_matching.d2` for the data flow of this proposal

The input to this module is a selected list of products, and the client DB.  

Selected product in general are selected by external means from the entire product catalog.  Potential routes are

- Hand picked by teh relationship manager on the UI.
- Products promoted by the bank.
- Top selling products in the last month

1. Receive request containing client targets and pre-selected product IDs.
2. Retrieve client profile and holdings from client API.
3. Retrieve product metadata/details for the passed-in product IDs.
4. Build product fitness scorecard per (client, product) pair.
5. Select top-N products per client after filtering and ranking.
6. Build `llm_input` payload with client, scorecards, candidate products, and market context.
7. Generate final proposal markdown using existing prompt template.
8. Return output according to response mode (`path`, `markdown`, `both`) with optional debug blocks.

Helper flow (client discovery mode):

1. Receive request containing pre-selected product IDs and client-discovery parameters.
2. Build IRS/PFS-based client list (top-N or threshold based).
3. Invoke the same core proposal pipeline as direct mode using discovered `client_ids`.

## Initial design

### Service boundaries

- Matching proposal service owns orchestration, scorecard assembly, and LLM input construction.
- Client API owns client profile and holdings retrieval.
- Product API owns searchable product catalog and product metadata.
- FastAPI wrapper stays thin and delegates to the local Python builder.
- Helper endpoint owns only client list discovery orchestration and delegates generation to the same builder.

### Core modules (logical)

- Request validator
- Client context retriever
- Product details retriever
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
		candidate_product_ids: list[str],
		top_n_per_client: int = 10,
		min_match_score: float | None = None,
		response_mode: str = "path",  # one of: path, markdown, both
		include_llm_input: bool = False,
		include_debug_scores: bool = False,
		include_market_outlook: bool = True,
) -> dict
```

### `generate_product_client_fit_proposal_by_discovery(...)`

Suggested signature:

```python
generate_product_client_fit_proposal_by_discovery(
	candidate_product_ids: list[str],
	top_n_clients: int = 20,
	min_readiness_score: float | None = None,
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
- `candidate_product_ids`: pre-selected product IDs provided by upstream logic.
- `top_n_per_client`: max shortlisted products per client.
- `min_match_score`: optional threshold to suppress weak matches.
- `response_mode`: `path`, `markdown`, or `both`.
- `include_llm_input`: include assembled LLM context in output when true.
- `include_debug_scores`: include scorecard breakdown and filtering trace when true.
- `include_market_outlook`: include market references in context when true.

Helper-mode additional fields:

- `top_n_clients`: max clients selected by helper path.
- `min_readiness_score`: optional readiness threshold for helper client filtering.

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

- `POST /api/v1/product-client-fit-proposals` (direct mode: caller passes `client_ids`)
- `POST /api/v1/product-client-fit-proposals/discover-clients` (helper mode)

### Proposal request body (example)

```json
{
	"client_ids": ["PB-HK-000001-8", "PB-HK-000002-6"],
	"candidate_product_ids": ["BOND-XYZ", "ETF-ABCD", "MF-789"],
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

### Helper request body (example)

```json
{
	"candidate_product_ids": ["BOND-XYZ", "ETF-ABCD", "MF-789"],
	"top_n_clients": 20,
	"min_readiness_score": 6.0,
	"top_n_per_client": 10,
	"min_match_score": 6.5,
	"response_mode": "path",
	"include_llm_input": false,
	"include_debug_scores": false,
	"include_market_outlook": true
}
```

### Helper response body (example)

```json
{
	"status": "success",
	"discovered_client_ids": ["PB-HK-000001-8", "PB-HK-000002-6"],
	"results_by_client": [
		{
			"client_id": "PB-HK-000001-8",
			"candidate_products": [
				{"product_id": "BOND-XYZ", "match_score": 8.2}
			],
			"output_path": "runs/client_product_fit_analysis/PB-HK-000001-8.md"
		}
	]
}
```

## Tasks

### API input enhancement

Update proposal API request model to require `candidate_product_ids`.

Rules:

- `candidate_product_ids` must be non-empty.
- Deduplicate IDs while preserving first-seen order.
- Enforce max list size via config (to cap runtime/token usage).
- Return validation error when list is empty or exceeds configured max.

Direct-mode rules:

- `client_ids` must be non-empty.
- `client_ids` are deduplicated while preserving first-seen order.

Helper-mode rules:

- Do not accept `client_ids` in helper endpoint payload.
- Helper computes `discovered_client_ids` via IRS/PFS criteria and passes them to the same generation builder.
- If no clients are discovered, return validation/business error with explicit reason.

### Product details retrieval

For each passed-in product ID, fetch required product metadata for scoring and proposal generation.

Minimum behavior:

- If a product ID is not found, record per-client/per-product error and continue where possible.
- If all passed-in products are invalid for a client, return that client result as failed.
- Do not run product search/discovery logic in this service.

### Deferred / out-of-scope

- Product screening/discovery API design and filter semantics are handled by upstream selector services.
- This proposal service consumes only `candidate_product_ids` from the caller.

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
| AC3 | Builder retrieves product data only for caller-provided `candidate_product_ids` | Unit test with mocked product API and call assertions |
| AC4 | Request validation requires non-empty `candidate_product_ids` and enforces configured max list size | Contract tests and negative tests |
| AC5 | Duplicate product IDs in `candidate_product_ids` are deduplicated while preserving first-seen order | Unit test for normalization behavior |
| AC6 | Missing/invalid product IDs are handled gracefully with partial-failure reporting | Integration test with mixed valid/invalid products |
| AC7 | Matching score output contains deterministic per-client, per-product score entries | Snapshot/unit test with fixed fixtures |
| AC8 | Direct-mode endpoint accepts explicit `client_ids` and supports `path`, `markdown`, and `both` response modes | Endpoint integration tests for each mode |
| AC9 | Optional blocks are controlled by flags (`include_llm_input`, `include_debug_scores`, `include_market_outlook`) | Unit test matrix |
| AC10 | Required proposal sections are present and non-empty in generated markdown | Content validation test against required headers |
| AC11 | Batch request supports partial success and returns per-client errors without dropping successful clients | Integration test with mixed valid/invalid clients |
| AC12 | Logging uses Python logging module and records correlation ID and stage transitions | Unit test with log capture |
| AC13 | Helper endpoint discovers clients via IRS/PFS rules and then invokes the same core generation path | Integration test with mocked discovery and builder call assertion |
| AC14 | Helper endpoint returns `discovered_client_ids` and fails explicitly when none are discovered | Negative and positive contract tests |

## Open decisions

1. Whether minimum score threshold is fixed in config or fully caller-controlled.
2. Whether market outlook retrieval remains local reference loading or moves to API in this phase.
3. Whether debug score schema should align exactly with current investor readiness score artifact format.
4. Whether caller is allowed to pass product metadata directly (bypassing product detail lookup by ID).
5. Whether helper endpoint should expose full IRS/PFS discovery trace by default or only under debug flag.

## Recommended initial implementation order

1. Define and validate request/response models.
2. Implement `candidate_product_ids` validation and normalization.
3. Implement direct and helper endpoint request validators.
4. Implement helper client discovery orchestration and delegation to the same builder.
5. Add endpoint wrappers, response-mode handling, and tests for AC1 to AC14 before broad rollout.

