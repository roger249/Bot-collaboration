Reinvestment Proposal API Refactor
=================================

## Overview

The current reinvestment proposal is generated from static files only. The next step is to refactor the proposal generation flow so that all client, holding, and product data are retrieved through remote FastAPI endpoints.

The goals are:

1. Replace file-based client and product inputs with API-backed retrieval.
2. Preserve the current reinvestment proposal output structure and quality.
3. Keep the proposal generator callable as a local Python function while using remote FastAPI calls for client/product retrieval.
4. Make the API contract stable enough that the same payload can be used by local callers and remote callers.

This spec covers the reinvestment proposal only. It does not redesign the proposal text itself, only how the input data are gathered and assembled for the LLM.

### Sprint 1 status (completed)

| Deliverable | Status | Files |
|---|---|---|
| `generate_reinvestment_proposal(...)` builder | ✅ | `src/integrations/reinvestment_proposal.py` |
| `POST /api/v1/reinvestment-proposals` endpoint | ✅ | `src/integrations/server.py` |
| API-backed client/product catalog overrides for CrewAI | ✅ | generated under `runs/reinvestment_proposal/_generated/` |
| Unit tests (mocked) | ✅ 17 tests | `tests/test_reinvestment_proposal.py` |
| Integration test (single-client, real LLM) | ✅ | `tests/test_run_client_investment_proposal.py` |
| Integration test (multi-client, up to 5, real LLM) | ✅ | `tests/test_run_client_investment_proposal.py` |
| FastAPI HTTP switch for data retrieval | 🔜 Sprint 2 | `docs/prod_spec/reinvestment_proposal_sprint2.md` |

**Implementation note (v1):** Data retrieval currently uses direct Python imports (`src.integrations.client_api`, `src.integrations.product_tool`). Switching to FastAPI HTTP calls is deferred to Sprint 2. The API contract and response shapes are identical regardless of transport.

## Scope

### In scope

- Reinvestment proposal generation for one or more targets per request (`reinvestment_targets`), processed by iterating target pairs.
- Current trigger mode for this API: caller provides `reinvestment_targets` directly (`client_id` + `source_product_id` per target).
- Retrieval of client profile and holdings from the integration APIs (local Python in v1; FastAPI HTTP in Sprint 2).
- Retrieval of source products and candidate reinvestment products from the integration APIs (local Python in v1; FastAPI HTTP in Sprint 2).
- Assembly of a structured `llm_input` payload for the LLM.
- Local proposal builder with integration API data retrieval (local Python in v1; FastAPI HTTP target for Sprint 2).

### Out of scope

- Rewriting the product catalog or client APIs themselves.
- Changing the reinvestment proposal narrative format beyond what is needed to consume API data.
- Full parallel orchestration across many proposals in this first draft.
- Automatic client/source discovery orchestration (call `search_holdings_maturing`, derive `reinvestment_targets`, then invoke this API).
- UI work.

## Current state

**Before Sprint 1:** The reinvestment proposal was fed by files such as:

- client profile markdown and CSV
- product catalog markdown and CSV
- market outlook markdown files
- static proposal instructions and section templates

**After Sprint 1:** The proposal builder now retrieves client/profile/holdings from the integration APIs, fetches reinvestment candidates via the product API, generates API-backed product catalog reference files, and invokes CrewAI with all references overridden. Both client profile and product catalog data come from the API layer — no static client/product files are read. Data retrieval uses direct Python imports in v1; FastAPI HTTP switch is deferred to Sprint 2.

The generated output includes:

- executive summary
- recommended product
- risk characteristics
- detailed justification and product-fit reasoning
- suggested portfolio tables
- scenario analysis
- risk disclosures
- references

The proposal content should remain similar. The refactor only changes the data-loading mechanism.

## Target architecture

### Phase 1: Python proposal builder

Implement a Python function that:

1. Accepts a request payload containing reinvestment targets and proposal options.
2. Fetches client profile and holdings from the integration APIs (local Python in v1).
3. Accepts trigger inputs directly (`reinvestment_targets`) without doing maturity discovery internally.
4. Fetches reinvestment candidate products from the integration APIs (local Python in v1).
5. Builds a structured context payload for the LLM.
6. Returns per-client generation outputs according to `response_mode`, plus optional debug/context fields controlled by include flags.

### Phase 2: Reinvestment FastAPI wrapper

Expose the same Python function as an HTTP endpoint so the main module can call the full proposal service remotely.

The FastAPI wrapper should be thin and should not contain proposal logic.

## Proposed workflow

### 1. Identify the reinvestment trigger

The proposal starts from a source holding or a set of source holdings that release cash for reinvestment.

Preferred trigger options:

- a source `product_id`
- one or more client identifiers plus a holdings filter
- a maturity window from the client API

The first version should support the most direct trigger:

- `reinvestment_targets` with explicit (`client_id`, `source_product_id`) per target

Later versions can add a separate orchestration endpoint that first calls maturity discovery and then invokes this generation API.

### 2. Retrieve client context

Use the integration APIs to retrieve:

- full client profile
- holdings
- derived risk readiness fields if needed

The reinvestment proposal should not read client CSV files directly.

### 3. Retrieve candidate products

Use the integration APIs to retrieve:

- source product metadata
- reinvestment candidates from `search_reinvestment_candidates`
- optional product detail by `product_id`

The proposal should not read product catalog markdown or CSV directly.

### 4. Build llm_input payload

Transform the retrieved data into a structured `llm_input` payload for the LLM.

The context should include:

- client summary
- current holdings summary
- source product summary
- candidate product list
- market outlook snippets
- product descriptions or catalog summaries
- scoring explanations and shortlist rationale

### 5. Generate the proposal

Pass the assembled `llm_input` payload to the existing proposal-writing prompt and render the final report.

## Python API design

### `generate_reinvestment_proposal(...)`

A local Python function should be the primary entry point.

Suggested signature:

```python
generate_reinvestment_proposal(
   reinvestment_targets: list[dict[str, str]],
   max_per_product_type: int = 2,
   top_n_per_client: int = 10,
   risk_rating_hard_filter: bool = True,
   response_mode: str = "path",  # one of: path, markdown, both
   include_llm_input: bool = False,
   include_market_outlook: bool = True,
   include_candidate_explanations: bool = True,
   include_debug_scores: bool = False,
) -> dict
```

### Input fields

- `reinvestment_targets`: list of target objects. Each object must contain:
   - `client_id`
   - `source_product_id`
- `max_per_product_type`: diversification cap for candidate selection.
- `top_n_per_client`: maximum number of candidate products passed to the LLM.
- `risk_rating_hard_filter`: boolean, whether to enforce the hard risk filter in the product API. Default is `True`.
- `response_mode`: one of `path`, `markdown`, `both`. Default is `path`.
- `include_llm_input`: whether to include the assembled LLM input block in API output. Default is `False` (not included).
- `include_market_outlook`: whether to attach market outlook references.
- `include_candidate_explanations`: whether to attach scoring and shortlist rationale.
- `include_debug_scores`: whether to return the intermediate score-card output used during migration testing. Default is `False`.

### Output fields

The Python function should return a dictionary containing at least:

- `results_by_client`: list of per-client result objects. Each item contains:
   - `client_id`
   - `source_product_id`
   - `candidate_products`
   - `llm_input` (optional; included only when `include_llm_input = True`)
   - `output_path` when `response_mode` is `path` or `both`
   - `markdown_output` when `response_mode` is `markdown` or `both`
   - `debug_scores` (optional; included only when `include_debug_scores = True`)

## FastAPI contract

### Endpoint

Proposed endpoint:

- `POST /api/v1/reinvestment-proposals`

### Request body

```json
{
   "reinvestment_targets": [
      {"client_id": "PB-HK-000001-8", "source_product_id": "ETF-HYG"},
      {"client_id": "PB-HK-000002-6", "source_product_id": "BOND-ABC"}
   ],
   "max_per_product_type": 2,
   "top_n_per_client": 10,
   "risk_rating_hard_filter": true,
   "response_mode": "path",
   "include_llm_input": false,
   "include_debug_scores": false,
   "include_market_outlook": true,
   "include_candidate_explanations": true
}
```

### Response body

```json
{
   "status": "success",
   "results_by_client": [
      {
         "client_id": "PB-HK-000001-8",
         "source_product_id": "ETF-HYG",
         "candidate_products": [
            {"product_id": "ETF-BND", "fitness_score": 8.35}
         ],
         "output_path": "runs/reinvestment_proposal/PB-HK-000001-8.md"
      }
   ]
}
```

Response mode behavior:

- `candidate_products` is always included in each `results_by_client` item for downstream use.
- `path`: return `output_path` (plus always-on fields such as `client_id`, `source_product_id`, `candidate_products`).
- `markdown`: return `markdown_output` (plus always-on fields such as `client_id`, `source_product_id`, `candidate_products`).
- `both`: return both `output_path` and `markdown_output` (plus always-on fields).
- `include_llm_input`: when `True`, include `llm_input` in each `results_by_client` item; default `False` omits it
- `include_debug_scores`: when `True`, include `debug_scores` in each `results_by_client` item; default `False` omits it

## Data retrieval contract

### Client API usage (v1: local Python; Sprint 2: remote FastAPI)

The reinvestment proposal generator should call the client APIs for:

- `search_by_id(client_id)` (v1) / `GET /api/v1/clients/{client_id}` (Sprint 2)
- `search_holdings_maturing(...)` if needed for maturity-triggered reinvestment discovery
- `search(...)` only if filtering by portfolio criteria is needed for shortlist selection

### Product API usage (v1: local Python; Sprint 2: remote FastAPI)

The reinvestment proposal generator should call the product APIs for:

- `search_by_product_id(pid)` (v1) / `GET /api/v1/products/{product_id}` (Sprint 2)
- `search_reinvestment_candidates(...)` (v1) / `POST /api/v1/products/reinvestment-candidates` (Sprint 2)
- `search_similar(...)` only if direct similarity control is needed

## LLM context assembly

The `llm_input` payload should be structured and deterministic.

### Format (v1)

API data is injected into the LLM prompt as **JSON**. This keeps the first version simple and avoids introducing a serialization layer before the API flow is stable.

**Prompt compatibility**: The current CrewAI reinvestment task definition `reinvestment_proposal_task` in `data/planbot/reinvestment_proposal/crewai/tasks.yaml` already states "The reference materials are provided at the end of the user prompt as a structured JSON." No prompt changes are needed — the same task instructions and proposal format work for both local-file and API-backed flows. The only difference is how the data content block is assembled: file reads for `localfile` entry point, API calls for `api` entry point.

### Format (future)

A compact format using **pipe-delimited rows with a header line** for flat data (holdings) and **key=value blocks** for nested data (products). This reduces token usage by ~3–4× vs Markdown and ~2× vs JSON. See the Outstanding section for details.

### Required context blocks

1. Client block
   - client ID
   - risk rating
   - age / demographics if available
   - cash and concentration scores if available

2. Current holdings block
   - holdings summary
   - maturing positions
   - current portfolio risk notes

3. Source product block
   - product description
   - source product rationale
   - maturity / reinvestment trigger reason

4. Candidate products block
   - shortlist with product IDs, product types, risk ratings, expected returns, and fit scores
   - brief rationale for each candidate

5. Market outlook block
   - relevant market outlook references selected from market-data inputs

6. Output instruction block
   - proposal outline
   - tone and risk disclosure requirements

## Migration plan

### Step 1: Extract llm_input builder

Move the reinvestment proposal input preparation into a Python function that can be called from tests without rendering the final markdown.

### Step 2: Swap static file readers for APIs

Replace file-based loading of:

- client profile markdown
- client CSV rows
- product catalog markdown
- product catalog CSV rows

with API calls.

### Step 3: Add candidate shortlist API integration

Use the product reinvestment candidate API to assemble the shortlist before invoking the LLM.

### Step 4: Add FastAPI wrapper

Expose the same Python function through a thin HTTP layer.

### Step 5: Implement reinvestment endpoint ✅ DONE

Implemented `POST /api/v1/reinvestment-proposals` in `src/integrations/server.py` as a thin endpoint wrapper that delegates to the proposal builder. See Sprint 1 status above for details.

## Acceptance criteria

| # | Criterion | Verification |
|---|---|---|
| AC1 | Reinvestment proposal generation can run from a Python function without reading client/product static files | Unit test with mocked APIs |
| AC2 | The Python function retrieves client and product data only through the APIs | Code review and integration test |
| AC3 | Candidate selection uses `search_reinvestment_candidates` and honors `max_per_product_type` | Unit test with known candidate pool |
| AC4 | The `llm_input` payload includes client, holdings, source product, candidates, and market outlook blocks | Snapshot test of assembled payload |
| AC5 | The same Python function is callable through a FastAPI endpoint | HTTP integration test |
| AC6 | Output remains compatible with the current reinvestment proposal structure | Validate required section headers (in expected order), ensure each required section is non-empty, and check critical anchors (recommended product ID and risk disclosure presence) |
| AC7 | Missing API data is handled gracefully and logged per client | Failure-path unit test |
| AC8 | The refactor does not require the LLM prompt to read static client/product files | Prompt assembly test |
| AC9 | Optional debug score-card output is returned when `include_debug_scores = True` and contains the client/product filtering information used during migration testing | Unit test with mocked client/product filters |

## Outstanding

Items intentionally deferred from this spec. Tracked here for follow-up.

| # | Item | Suggested Approach |
|---|---|---|
| N/A | No open Sprint 1 items. | Sprint 2 scope is defined separately — see `docs/prod_spec/reinvestment_proposal_sprint2.md`. |

## Debug output

During migration testing, the service should be able to return debug score-card output used to filter out products or clients.

The debug payload should be optional and must not alter the normal markdown output.

Required debug data:

- investor readiness score for the client
- product fitness scores for shortlisted candidates
- per-component scores for each score card
- any gating reason that caused a product or client to be excluded

## Recommendation

Sprint 1 delivered a working end-to-end pipeline. The builder accepts `reinvestment_targets`, fetches all data from the integration APIs, overrides static reference files with API-backed content, and invokes CrewAI to generate real proposals.

Sprint 2 priorities (see `docs/prod_spec/reinvestment_proposal_sprint2.md`):
1. Switch data retrieval to FastAPI HTTP calls.
2. Add a discovery/orchestration endpoint.
3. Add bounded concurrency.
4. Add compact LLM input format.
5. Add deterministic candidate explanations.

## Not for implementation now

| # | Issue | Rationale | Review point |
|---|---|---|---|
| N1 | Introduce parallel fan-out strategy in v1 | Iterative multi-target processing via `reinvestment_targets` is already in current scope. What is deferred is the parallel/concurrency policy, which adds retry/log/output complexity and partial-failure handling requirements. | Keep iterative processing in v1. Revisit bounded parallelism only after iterative `reinvestment_targets` path is stable and tested. |
| N2 | Replace JSON prompt payload with token-optimized compact serialization in v1 | JSON-first path is simpler for migration and debugging; compact format can be phase 2 optimization | Keep JSON for v1 and schedule compact format after contract stabilization. |
| N3 | Candidate product explanation ownership is not fixed. The spec says to include scoring explanations and shortlist rationale. Unclear whether assembled by the proposal service or generated by the LLM. | Deferred from current implementation scope. | Revisit once core API-backed flow is stable; keep shortlist logic deterministic if implemented in service. |
| N4 | Add a discovery/orchestration endpoint for maturity-driven runs. | Current API intentionally accepts explicit `reinvestment_targets` only. A separate orchestrator is needed to call `search_holdings_maturing`, derive `reinvestment_targets`, and then invoke this API. | Implement in a later sprint as a separate endpoint; keep responsibilities split between discovery and generation. |
| N5 | Token-optimized context format. v1 uses JSON for API data injection. For production, a more token-efficient format is desirable. | Optimization can be postponed until contract stability is proven. | Keep JSON in v1; evaluate compact serialization after stabilization. |