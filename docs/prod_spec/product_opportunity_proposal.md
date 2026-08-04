Product Opportunity Proposal API
================================

## Overview

The Product Opportunity Proposal generates a full investment recommendation
proposal (markdown) for a specific client–product pair.  It is the final stage
of the proposal pipeline after the Product-Investor Matcher has identified
which clients are ready and which products are suitable.

This Proposal will also be invoked from the UI with a manually selected client, product and rationale judged by a investment advise

### End-to-End Data Flow

```
Request (client_id, product_id, rationale, options)
       │
       ▼
┌──────────────────────────────┐
│ 1. Resolve Input Data        │
│    - Client profile via API  │  ← `GET /client/search_by_id`
│    - Client holdings via API │  ← (included in ClientProfile)
│    - Product profile via API │  ← `GET /product/search_by_product_id`
│    - Alternative products    │  ← `GET /product/search_similar`
│    - Product fitness scores  │  ← computed or optionally cached
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ 2. Build API Resolver        │
│    - In-memory construction  │  ← same pattern as reinvestment proposal
│    - api_resolver() callable  │     (Phase A: direct DB calls;
│      serves client, holdings, │      Phase B: HttpApiResolver)
│      product, alternatives,   │
│      rationale to CrewAI      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ 3. LLM Proposal Generation   │
│    - CrewAI agent/task       │  ← configured in config_planbot.yaml
│    - Produces full markdown  │     under `product_opportunity_proposal`
│      proposal per the TOC    │
└──────────────┬───────────────┘
               │
               ▼
       Proposal Markdown
       (Investment Recommendation + Supporting Analysis)
```

The proposal follows the structure defined in
`docs/prod_spec/proposal_sections.md`, covering:

- **Investment Recommendation** — suggested product & position, funding
  source, expected return/risk profile change, pros & cons, alternatives.
- **Supporting Analysis** — executive summary, product specification, asset
  allocation pie chart, portfolio constituents table, scenario analysis,
  risk disclaimer.

### APIs Exposed

This sprint exposes **two** FastAPI endpoints.

---

## API 1: `product_opportunity_proposal`

**Purpose:** Generate a single proposal for one client–product pair.  This is
the "manual" / single-shot endpoint, usable directly by an RM or called
internally by the automatch endpoint.

### Request

| Parameter     | Type    | Required | Description |
|---------------|---------|----------|-------------|
| `client_id`   | string  | Yes      | Client identifier. |
| `product_id`  | string  | Yes      | Primary suggested product. |
| `rationale`   | string  | No       | Freeform markdown describing why this product fits the client. Supplied by the RM (manual entry) or passed through from `product_investor_matcher` output. |
| `run_matcher` | boolean | No       | If `true`, run `product_investor_matching` and use its output as rationale/fitness scores. If `false` (default), the caller must supply `rationale` directly. Default: `false`. |
| `market_outlook` | string | No    | Market narrative to include in LLM context. If omitted, uses a default or empty outlook. |
| `alternative_count` | int | No   | Number of alternative products to include. Default: 3. |

### Internal Processing

1. **Data Retrieval** — All data fetched via FastAPI:
   - Client profile: `GET /client/search_by_id/{client_id}`
   - Product profile: `GET /product/search_by_product_id/{product_id}`
   - Alternative products: extracted from the LLM matcher output
     (per-client ``Alternative suggestion`` bullets).
     Format: `- PRODUCT_ID Name (fitness X.XX) …`.
     Parse via regex `-\s+([A-Za-z]+[-.]?[\w.-]+)\s`.
     **Fallback:** if no alternatives are found, use
     `search_similar_to_product(primary_product, …)`.

     > `search_similar_to_product` is a shared utility in `src/integrations/product_tool.py`.  It composes `_build_similarity_query_from_product` with `search_similar` and auto-excludes the anchor.  Also used by `search_reinvestment_candidates` and the reinvestment proposal flow.
   - Product fitness scores and rationale (when `run_matcher=true`):
     obtained from `product_investor_matcher`.  Scores are
     **reused** rather than recomputed.
   - When `run_matcher=false` (default), caller supplies rationale;
     fitness scores are computed inline using the
     existing scorer (`docs/prod_spec/score_card/product_fitness_score.md`).

2. **Payload Construction** — Build an `api_resolver` callable following the
   same pattern as `_build_fit_analysis_resolver()` in the matcher.
   The resolver serves `API_CLIENT_PROFILE`, `API_HOLDINGS`,
   and `API_PRODUCT_CATALOG` paths to CrewAI's `run_crew_planbot`.
   No temp files.  The resolver includes:
   - Client profile + holdings
   - Primary product specification
   - Alternative products with fitness scores
   - Rationale (from matcher or RM)
   - Market outlook
   - Proposal instructions + section guidelines (from `config_planbot.yaml`
     references, resolved via `runtime_reference_overrides`)

3. **LLM Invocation** — CrewAI agent/task configured under
   `product_opportunity_proposal` in `config_planbot.yaml`.

### Response

```json
{
  "client_id": "C001",
  "product_id": "P042",
  "output_filename": "runs/product_opportunity_proposal/product_opportunity_proposal_C001.md",
  "proposal_markdown": "<full markdown proposal>",
  "metadata": {
    "model": "deepseek_tool",
    "tokens_used": 12345,
    "alternative_products": ["P017", "P088", "P103"],
    "product_fitness_scores": {
      "P042": 8.2,
      "P017": 7.1,
      "P088": 6.5,
      "P103": 5.9
    }
  }
}
```

### Error Scenarios

| Condition | HTTP Status | Detail |
|-----------|-------------|--------|
| Client not found | 404 | `CLIENT_NOT_FOUND` |
| Product not found | 404 | `PRODUCT_NOT_FOUND` |
| LLM invocation failure | 502 | `LLM_ERROR` with retry flag |
| Risk rating hard-gate blocks product | 200 | Proposal with `status: "blocked"` and reason |

---

## API 2: `product_opportunity_proposal_automatch`

**Purpose:** Batch endpoint — runs product-investor matching, then generates
one proposal per eligible client–product pair.  This is the "lights-out"
automated workflow.

### Request

| Parameter              | Type    | Required | Description |
|------------------------|---------|----------|-------------|
| `product_ids`          | list[str] | Yes   | Product universe to consider. |
| `client_selection`     | object  | No       | Client filter criteria (region, risk_rating range, etc.). If omitted, all clients are considered. |
| `market_outlook`       | string  | No       | Market narrative for LLM context. |
| `readiness_pool_size`  | int     | No       | Top-K clients by investor readiness score. Only used when `run_matcher=true`. Default: 15 (from config). |
| `run_matcher`          | boolean | No       | If `true`, execute `product_investor_matching` inline. If `false` (default), read the latest matching output from `runs/product_investor_matching/`. Default: `false`. |
| `max_proposals`        | int     | No       | Cap on total proposals generated. Default: 10. Set 0 or -1 for unlimited. |

### Internal Processing

1. **Product-Investor Matching** — If `run_matcher=true`, invoke the
   `product_investor_matcher` endpoint inline (in-memory handoff, no file
   I/O).  If `false`, load the latest matching run from
   `runs/product_investor_matching/` by filename sort.

2. **Fan-Out** — For each (client, product) pair in the matching output,
   call the same internal logic as `product_opportunity_proposal`.
   Fitness scores from the matcher are reused (not recomputed).
   Sequential iteration (concurrency deferred to Sprint 2).

3. **Result Assembly** — Collect all proposal responses into a batch result.

> **Note on CrewAI config:** The `product_opportunity_proposal` section in
> `config_planbot.yaml` references file globs for `client_profiles`,
> `product_catalogs`, and `market_outlook`.  At runtime, these are
> resolved in-memory via `HttpApiResolver` + `runtime_reference_overrides`
> — no YAML changes required.  Same pattern as the reinvestment proposal.

### Response

```json
{
  "matcher_run_id": "2026-08-03T14-22-00",
  "total_clients_matched": 8,
  "total_proposals_generated": 8,
  "proposals": [
    {
      "client_id": "C001",
      "product_id": "P042",
      "output_filename": "runs/product_opportunity_proposal/product_opportunity_proposal_C001_P042.md",
      "proposal_markdown": "<markdown>",
      "metadata": { ... }
    }
  ],
  "errors": []
}
```

Partial failure: If one client's proposal generation fails, it is recorded
in `errors[]` and processing continues for remaining clients.  The HTTP
response is 200 as long as at least one proposal succeeded.

### Error Scenarios

| Condition | HTTP Status | Detail |
|-----------|-------------|--------|
| No eligible clients after readiness filter | 200 | `NO_ELIGIBLE_CLIENTS` warning, empty proposals |
| Matcher output file not found (run_matcher=false) | 400 | `MATCHER_OUTPUT_MISSING` |
| All proposals failed | 200 | Empty proposals, errors[] populated |
| Product universe empty | 400 | `EMPTY_PRODUCT_UNIVERSE` |

---

## Migration from Legacy Pipeline

The current `client_product_fit_analysis_proposals` pipeline in
`config/config_planbot.yaml` will be **deprecated** and replaced by this
API-driven flow.  Key changes:

| Aspect | Legacy | New (This Sprint) |
|--------|--------|--------------------|
| Data source | Static files (CSV, MD) | FastAPI endpoints |
| Handoff | Temp files on disk | In-memory (same as reinvestment) |
| Configuration | `config_planbot.yaml` pipeline section | API parameters + config for LLM references only |
| Concurrency | N/A | Sequential (deferred) |

The CrewAI agent/task configuration (`product_opportunity_proposal` section in
`config_planbot.yaml`) and reference files (proposal instructions, section
guidelines, financial needs docs) remain **unchanged** — only the data
retrieval and orchestration layer is refactored.

**Reference implementation:** `docs/prod_spec/reinvestment_proposal_s3.md`
and `src/integrations/reinvestment_proposal.py`.  The same pattern
(in-memory resolver → payload builder → LLM invocation → response assembly)
applies.

> **Phase A / Phase B:** Follows the same dual-mode pattern as the
> reinvestment proposal.
> - **Phase A** (default, `get_client_product_from_db: false`): Direct
>   calls to `search_by_id`, `search_by_product_id`,
>   `search_similar_to_product`, `search_product_by_fitness_score`.
> - **Phase B** (`get_client_product_from_db: true`): All client and
>   product data fetched via `HttpApiResolver` against the data service.
>   Controlled by `config_planbot.yaml` → `common.get_client_product_from_db`.

---

### Implementation Tasks

1. **Fix `_extract_top_pairs` regex & add alternative extraction.**  The LLM output structure (confirmed 2026-08-04 from `product_investor_matching_run-20260803-155239.md`):

   **Summary table** (8 columns):
   `| Client ID (Name) | Buying Score | Suggested Product & Position | Funding Source | Fitness Score | ER Suggested | ER Source | Key Rationale |`

   Parse per row:
   | Field | Source col | Regex |
   |-------|-----------|-------|
   | `client_id` | 1 | `[A-Z]{2}-[A-Z]{2}-\d{6,7}-\d` |
   | `buying_score` | 2 | `\d+` |
   | `product_id` | 3 | `[A-Za-z]+[-.]?[\w.-]+` (first token) |
   | `investment_amount` | 3 | `\$([\d,]+)` or `([\d,]+)` before `%` |
   | `funding_source` | 4 | entire cell |
   | `rationale` | 8 | entire cell |

   **Per-client alternatives** (under `#### Alternative suggestion`):
   Each line: `- PRODUCT_ID Name (fitness X.XX) …rest…`
   Extract `product_id` via `-\s+([A-Za-z]+[-.]?[\w.-]+)\s`.

   All patterns externalized to `config_planbot.yaml` under
   `product_investor_matching.matcher.extract_patterns`.
2. **Extract step 9 into new API.**  Move the per-pair `run_crew_planbot(proposal_name="product_opportunity_proposal")` logic from `product_investor_matcher()` step 9 into `src/integrations/product_opportunity_proposal.py`.  Enrich the resolver (holdings, alternatives, fitness scores, rationale).  Expose two FastAPI endpoints in `proposal_server.py`.
3. **Remove step 9 from matcher.**  Delete the entire `for pair in top_pairs:` loop (lines 313–373) from `product_investor_matcher()`.  The matcher stops at ranking and returns `final_proposals` as an empty list.
4. **Rename matcher function.**  Rename `match_products_to_investors` → `product_investor_matcher` in `src/integrations/product_investor_matcher.py` and `proposal_server.py` to align with the OpenAPI endpoint path `/api/v1/product-investor-matcher`.
5. **Add JSON sidecar to matcher output.**  After `_extract_top_pairs()` produces `list[dict]`, serialize to a `_pairs.json` sidecar alongside the `.md` file.  Implement `_load_latest_matcher_output()` — find the latest `_pairs.json` in `runs/product_investor_matching/`, load structured pairs with `client_id`, `product_id`, `rationale`, `buying_score`.  No markdown parsing at read time.
6. **Create test file.**  Create `tests/test_product_opportunity_proposal.py` with minimum two tests: normal flow + exception condition.
7. **Exclude primary product from alternatives.**  `search_similar_to_product()` automatically excludes the anchor product.  Callers no longer need to pass `exclude_product_ids` manually.


## Acceptance Criteria

| # | Criterion | Verification |
|---|-----------|-------------|
| AC1 | `product_opportunity_proposal` generates a valid proposal given `client_id` + `product_id` with empty rationale | Integration test: call endpoint, assert markdown contains all required TOC sections |
| AC2 | `product_opportunity_proposal_automatch` completes end-to-end via Swagger UI | Manual Swagger test with ≥2 clients |
| AC3 | Proposal output structure matches `docs/prod_spec/proposal_sections.md` (Investment Recommendation + Supporting Analysis sections present, non-empty) | Golden-file diff against legacy pipeline output |
| AC4 | All client, holdings, and product data retrieved via FastAPI — no static file reads | Code review: zero `open()` calls for data files in proposal path |
| AC5 | Product fitness scores are included in proposal metadata | Assert `metadata.product_fitness_scores` is populated and non-empty |
| AC6 | Empty rationale still produces a coherent proposal | Spot-check proposal quality with rationale="" |
| AC7 | `run_matcher=false` correctly loads latest matching run from disk | Integration test: pre-seed a matching output, verify it's picked up |
| AC8 | Partial failure in automatch does not abort remaining clients | Failure injection: make one client fail, assert others succeed |

---

## Sprint 2

| # | Item | Notes |
|---|------|-------|
| S1 | LLM prompt revision | Revise the CrewAI agent/task prompts to align with the proposal structure defined in `docs/prod_spec/proposal_sections.md`. The current prompts were written for an earlier proposal format; Sprint 2 will audit and update all prompt templates (proposal instructions, section guidelines) to ensure the LLM produces each required section (Investment Recommendation → Supporting Analysis) consistently. |
| S2 | Concurrency | Add bounded parallelism with configurable `max_concurrency` (default 1). Structure Sprint 1 fan-out so replacing with `asyncio.gather`/`ThreadPoolExecutor` is a one-line change. Accept `max_concurrency` param as no-op in Sprint 1 for forward-compatibility. |
| S3 | Response size & streaming | Add `response_mode: "inline" \| "file"` parameter. Default `"inline"` for backward compatibility. `"file"` persists proposals to disk and returns file paths instead of inline markdown. Needed if proposals grow with embedded charts (base64). |
| S4 | Refine JSON sidecar format | The `_pairs.json` sidecar (Sprint 1) captures the output of `_extract_top_pairs()`. In Sprint 2, consider having the LLM output structured JSON directly, eliminating the regex extraction step entirely. This requires prompt changes aligned with S1.

---

## Outstanding Issues (Pre-Implementation Review)

### ✅ Ready

- Matcher handles scorecards/filtering/ranking — ready for extraction
- `_build_similarity_query_from_product` helper ready for alternatives
- `product_tool.py` tests pass (21/21)
- CrewAI configs exist; proposal instructions exist
- `proposal_server.py` endpoint registration pattern is clear
- Reference implementation: `src/integrations/reinvestment_proposal.py`
- Output path uses legacy YAML root: `runs/product_opportunity_proposal/product_opportunity_proposal_{client_id}.md`

