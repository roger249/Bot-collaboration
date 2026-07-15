Reinvestment Proposal API Refactor
=================================

## Overview

The current reinvestment proposal is generated from static files only. The next step is to refactor the proposal generation flow so that all client, holding, and product data are retrieved through Python APIs first, and then exposed through a FastAPI endpoint for remote invocation.

The goals are:

1. Replace file-based client and product inputs with API-backed retrieval.
2. Preserve the current reinvestment proposal output structure and quality.
3. Keep the proposal generator callable as a local Python function before wrapping it with FastAPI.
4. Make the API contract stable enough that the same payload can be used locally or remotely.

This spec covers the reinvestment proposal only. It does not redesign the proposal text itself, only how the input data are gathered and assembled for the LLM.

## Scope

### In scope

- Reinvestment proposal generation for one client at a time.
- Retrieval of client profile and holdings from the client API.
- Retrieval of source products and candidate reinvestment products from the product API.
- Assembly of a structured proposal context for the LLM.
- Local Python API first, then FastAPI wrapper.

### Out of scope

- Rewriting the product catalog or client APIs themselves.
- Changing the reinvestment proposal narrative format beyond what is needed to consume API data.
- Full parallel orchestration across many proposals in this first draft.
- UI work.

## Current state

Today the reinvestment proposal is fed by files such as:

- client profile markdown and CSV
- product catalog markdown and CSV
- market outlook markdown files
- static proposal instructions and section templates

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

### Phase 1: Python API

Implement a Python function that:

1. Accepts a request payload containing the client identifier and proposal options.
2. Fetches client profile and holdings from the client API.
3. Identifies maturity/reinvestment trigger holdings, if applicable.
4. Fetches reinvestment candidate products from the product API.
5. Builds a structured context payload for the LLM.
6. Returns the proposal context plus selected references.

### Phase 2: FastAPI wrapper

Expose the same Python function as an HTTP endpoint so the main module can call it remotely.

The FastAPI wrapper should be thin and should not contain proposal logic.

## Proposed workflow

### 1. Identify the reinvestment trigger

The proposal starts from a source holding or a set of source holdings that release cash for reinvestment.

Preferred trigger options:

- a source `product_id`
- a client identifier plus a holdings filter
- a maturity window from the client API

The first version should support the most direct trigger:

- client ID + source product ID

Later versions can add maturity-window discovery.

### 2. Retrieve client context

Use the client API to retrieve:

- full client profile
- holdings
- derived risk readiness fields if needed

The reinvestment proposal should not read client CSV files directly.

### 3. Retrieve candidate products

Use the product API to retrieve:

- source product metadata
- reinvestment candidates from `search_reinvestment_candidates`
- optional product detail by `product_id`

The proposal should not read product catalog markdown or CSV directly.

### 4. Build proposal context

Transform the retrieved data into a structured proposal context for the LLM.

The context should include:

- client summary
- current holdings summary
- source product summary
- candidate product list
- market outlook snippets
- product descriptions or catalog summaries
- scoring explanations and shortlist rationale

### 5. Generate the proposal

Pass the assembled context to the existing proposal-writing prompt and render the final report.

## Python API design

### `generate_reinvestment_proposal(...)`

A local Python function should be the primary entry point.

Suggested signature:

```python
generate_reinvestment_proposal(
    client_id: str,
    source_product_id: str,
    top_k_per_product_type: int = 2,
    top_n_candidates: int = 10,
    risk_rating_hard_filter: bool = False,
    include_market_outlook: bool = True,
    include_candidate_explanations: bool = True,
      include_debug_scores: bool = False,
) -> dict
```

### Input fields

- `client_id`: the client to generate the proposal for.
- `source_product_id`: the current or maturing product to reinvest from.
- `top_k_per_product_type`: diversification cap for candidate selection.
- `top_n_candidates`: maximum number of candidate products passed to the LLM.
- `risk_rating_hard_filter`: whether to enforce the hard risk filter in the product API.
- `include_market_outlook`: whether to attach market outlook references.
- `include_candidate_explanations`: whether to attach scoring and shortlist rationale.
- `include_debug_scores`: whether to return the intermediate score-card output used during migration testing.

### Output fields

The Python function should return a dictionary containing at least:

- `client_id`
- `source_product_id`
- `client_profile`
- `client_holdings`
- `source_product`
- `candidate_products`
- `proposal_context`
- `references`
- `rendered_output_path` (if the proposal is also rendered immediately)
- `debug_scores` (optional; included only when `include_debug_scores = True`)

## FastAPI contract

### Endpoint

Proposed endpoint:

- `POST /api/v1/reinvestment-proposals`

### Request body

```json
{
  "client_id": "PB-HK-000001-8",
  "source_product_id": "ETF-HYG",
  "top_k_per_product_type": 2,
  "top_n_candidates": 10,
  "risk_rating_hard_filter": false,
  "include_market_outlook": true,
  "include_candidate_explanations": true
}
```

### Response body

```json
{
  "client_id": "PB-HK-000001-8",
  "source_product_id": "ETF-HYG",
  "status": "success",
  "proposal_context": {
    "client_profile": {},
    "client_holdings": [],
    "source_product": {},
    "candidate_products": []
  },
   "debug_scores": {
      "investor_readiness_score": {
         "client_id": "PB-HK-000001-8",
         "total_score": 72.5,
         "component_scores": {
            "cash_score": 8.0,
            "concentration_score": 6.5,
            "active_score": 3.0,
            "life_stage_score": 5.0
         },
         "filter_reason": "client selected as a reinvestment candidate"
      },
      "product_fitness_scores": [
         {
            "client_id": "PB-HK-000001-8",
            "product_id": "ETF-BND",
            "fitness_score": 8.35,
            "component_scores": {
               "risk_rating_match_score": 9.0,
               "concentration_score": 8.5,
               "has_similar_investment_experience_score": 10.0,
               "better_product_score": 6.2
            },
            "filter_reason": "passed hard risk gate and ranked in the top-k shortlist"
         }
      ]
   },
  "output_path": "runs/reinvestment_proposal/PB-HK-000001-8.md"
}
```

## Data retrieval contract

### Client API usage

The reinvestment proposal generator should call the client API for:

- `search_by_id(client_id)`
- `search_holdings_maturing(...)` if needed for maturity-triggered reinvestment discovery
- `search(...)` only if filtering by portfolio criteria is needed for shortlist selection

### Product API usage

The reinvestment proposal generator should call the product API for:

- `search_by_id(product_id)`
- `search_reinvestment_candidates(...)`
- `search_similar(...)` only if direct similarity control is needed

## LLM context assembly

The proposal context should be structured and deterministic.

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

### Step 1: Extract proposal context builder

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

## Acceptance criteria

| # | Criterion | Verification |
|---|---|---|
| AC1 | Reinvestment proposal generation can run from a Python function without reading client/product static files | Unit test with mocked APIs |
| AC2 | The Python function retrieves client and product data only through the APIs | Code review and integration test |
| AC3 | Candidate selection uses `search_reinvestment_candidates` and honors `top_k_per_product_type` | Unit test with known candidate pool |
| AC4 | The proposal context includes client, holdings, source product, candidates, and market outlook blocks | Snapshot test of assembled context |
| AC5 | The same Python function is callable through a FastAPI endpoint | HTTP integration test |
| AC6 | Output remains compatible with the current reinvestment proposal structure | Golden-file comparison against existing sample output |
| AC7 | Missing API data is handled gracefully and logged per client | Failure-path unit test |
| AC8 | The refactor does not require the LLM prompt to read static client/product files | Prompt assembly test |
| AC9 | Optional debug score-card output is returned when `include_debug_scores = True` and contains the client/product filtering information used during migration testing | Unit test with mocked client/product filters |

## Outstanding

1. Maturity-trigger discovery is not fully defined.
   - The current draft supports `client_id + source_product_id` first.
   - It is still unclear whether maturity-window discovery should live in the client API, the proposal service, or both.

2. Candidate product explanation ownership is not fixed.
   - The spec says to include scoring explanations and shortlist rationale.
   - It is still undefined whether those explanations are assembled by the proposal service or generated by the LLM.

3. The FastAPI response contract is still partial.
   - The request body is defined.
   - It is still unclear whether the endpoint should return only the final markdown or both markdown and structured context payload.

4. Batch fan-out is deferred.
   - The current draft is one-client-at-a-time.
   - It is still undefined whether the service should later support multiple clients in a single request.

5. Market outlook source selection is not yet standardized.
   - The current proposal format and output should remain unchanged in this phase.
   - Any redesign of the markdown structure or output contract should be deferred until after the API-backed flow is stable.

## Debug output

During migration testing, the service should be able to return debug score-card output used to filter out products or clients.

The debug payload should be optional and must not alter the normal markdown output.

Required debug data:

- investor readiness score for the client
- product fitness scores for shortlisted candidates
- per-component scores for each score card
- any gating reason that caused a product or client to be excluded

## Recommendation

Start with a local Python API that accepts `client_id` and `source_product_id`, because that gives the cleanest migration path from file-backed generation to API-backed generation.

Once that is stable, wrap it in FastAPI with the same request/response schema so the main module can call it remotely without changing business logic.