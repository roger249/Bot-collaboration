# LLM Product Matcher (POC)

> Status: Draft. Proof-of-concept spec.

## 1. Overview

The current `product_investor_matching` flow (see `config/config_planbot.yaml`) pre-computes a **Product Fitness Score (PFS)** over a preselected product set, then hands the ranked results to the LLM. The LLM's role is therefore limited to re-ranking already-scored candidates.

This POC inverts that responsibility: the LLM performs product matching itself by querying the product catalog through a tool (`search_similar`) — **without any pre-computed PFS**. Web search is **deferred** to a future enhancement (see §10). The report **must use the same output format as the current `product_investor_matching`** (see §5).

## 2. Objectives

1. Expose `search_similar` as a CrewAI tool so the LLM can query the product catalog directly.
2. Build a new proposal (`llm_product_matcher`) modeled on `product_investor_matching` that hands the LLM the product-query tool.
3. Produce a matcher report in the **same format** as the current `product_investor_matching` output, by reusing its format template and task prompt.
4. Expose a batch API endpoint (like `/api/v1/product-opportunity-proposal-automatch`) that takes `client_id` directly, so **no investor-readiness (IRS) filter** is required.

## 3. Scope

### In scope

- A `ProductSearchTool` wrapping `src/integrations/product_tool.search_similar`.
- A new `llm_product_matcher` proposal (CrewAI agent/task + `config_planbot.yaml` section).
- Client profiles + holdings still fed as references (readiness score, RM notes, holdings), but **no PFS tables**.
- Externalized config (tool params, model, output paths) in YAML.
- **Output format parity** with the current `product_investor_matching` (reuse `proposal_format.md` + task prompt).
- A batch API endpoint (`/api/v1/llm-product-matcher`) taking `client_id` directly — **no IRS/readiness filter** (see §6).

### Out of scope (POC)

- **Web search**: no web-search tool is attached in this POC. Deferred to §10.
- **Investor-readiness (IRS) filtering**: `client_id` is supplied directly, so the readiness scorecard gate is bypassed.
- PFS scorecards (existing `product_investor_matching` remains unchanged).
- **Downstream parsing** (feeding `llm_product_matcher` output through `_extract_top_pairs` / `_pairs.json`) — not required for the POC; parity is about the *report format*, not the parser.

## 4. Tools

### 4.1 `ProductSearchTool` (new)

Wrap `search_similar` from `src/integrations/product_tool.py`. It already returns a clean `{"results": [...]}` dict and reads config + DuckDB through adapters — no I/O refactor needed.

- **Wrapper location**: `src/planbot/product_search_tool.py` (mirrors `yfinance_tool.py` / `crawl4ai_tool.py`).
- **Pattern**: `crewai.tools.BaseTool` subclass with an `args_schema` Pydantic model and a `_run()` that returns a **string** (`search_similar` returns a dict, so serialize with `json.dumps`).
- **Two entry points** (both exposed, per the LLM's likely need to start from a known holding):
  1. **`product_id`** — anchor on an existing product, delegating to `search_similar_to_product` (auto-excludes the anchor).
  2. **Raw attribute query** — flattened top-level fields (`risk_rating`, `expected_return`, `product_type`, `asset_class`, `region`, `sector`, `time_to_maturity`, `coupon`, `trade_date`), assembled into the `query` dict inside `_run` (avoids nested-dict tool-arg pitfalls).

Underlying `search_similar` signature:

```python
search_similar(
    query: dict | None = None,          # risk_rating, expected_return, product_type,
    *,                                  # asset_class, region, sector, time_to_maturity,
    top_n: int = 3,                     # coupon, trade_date
    risk_rating_hard_filter: bool = True,
    diversification: bool = True,
    max_candidates_per_product_type: int = 2,
    exclude_product_ids: list[str] | None = None,
) -> dict   # {"results": [{product_id, name, product_type, risk_rating,
            #               expected_return, investment_note, similarity_score}, ...]}
```

- **Registration**: add a `ProductSearch` branch to `_build_tool_instance()` in `src/planbot/crew_workflow.py`.
- **Attachment**: list it under the agent's `tools` field in `data/planbot/llm_product_matcher/crewai/agents.yaml`.

## 5. New proposal definition

Add a `llm_product_matcher` section to `config/config_planbot.yaml`, modeled on `product_investor_matching`:

```yaml
llm_product_matcher:
  task: llm_product_matcher_task
  data_root: data/planbot/llm_product_matcher
  crewai_config_folder: data/planbot/llm_product_matcher/crewai
  references_root: data/planbot/llm_product_matcher
  output_root: runs/llm_product_matcher
  output_filename: llm_product_matcher.md
  llm_model: deepseek_tool
  references:
    proposal_instructions_and_format:
      - name: proposal_instructions/*.md      # reuse the existing proposal_format.md
        purpose: Instructions and format for generating the proposal
    # client_profiles + product_catalogs resolved at runtime (no PFS).
    # guidelines + market_outlook globs mirror product_investor_matching.
```

CrewAI config files (new folder, no shared-file edit to existing matcher):

- `data/planbot/llm_product_matcher/crewai/agents.yaml`
  - role/goal/backstory adapted from `investment_advisor_agent`
  - `tools: [ProductSearch]`
- `data/planbot/llm_product_matcher/crewai/tasks.yaml`
  - `description`: instruct the LLM to use the product tool to discover candidates; **reuse the current `product_investor_matching` task prompt verbatim, minus the PFS-specific guidance** (e.g. "Only recommend products that have a fitness score entry", "Use the Product Fitness Scores table").
  - `expected_output`: reference `proposal_instructions/proposal_format.md`, same as the current matcher.

### 5.1 Output format (shared with current matcher)

The output must follow `data/planbot/product_investor_matching/proposal_instructions/proposal_format.md`, which defines these sections:

1. **Executive Summary** — YAML-instruction block + an 8-column table (`Client ID (Name)` | `Buying Score` | `Suggested Product & Position` | `Funding Source` | `Fitness Score` | `Expected Return – Suggested` | `Expected Return – Source` | `Key Rationale`), ≤10 clients, descending buying score.
2. **Top clients with detail analysis** — per-client `###` sections with elaborated justification.
3. **Alternative suggestion** — `####` sub-section under each client.
4. **References** — per the section-instruction reference.

Because there is **no PFS** in this POC, the `Fitness Score` column is **decided by the LLM**: it produces its own suitability estimate (1–5, mirroring the existing buying-score scale) **and must provide a justification** for the score in the rationale. The section/column structure is preserved by reusing the same `proposal_format.md` + task prompt; the task prompt's PFS-specific guidance is replaced with an instruction for the LLM to derive and justify its own fitness score from `search_similar` results, client profile, and market outlook.

The POC is exposed through the endpoint defined in §6 (which invokes `run_crew_planbot(proposal_name="llm_product_matcher", ...)` under the hood).

## 6. API endpoint

### 6.1 `POST /api/v1/llm-product-matcher`

Modeled on `/api/v1/product-opportunity-proposal-automatch`, but the client universe is supplied **directly** (`client_ids`), so the investor-readiness (IRS) scorecard gate is **not** applied. Client profiles are still fetched via the client API and fed to the LLM as references; the LLM does the matching with `ProductSearch` and produces the shared-format report.

Request (`LlmProductMatcherRequest`):

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `product_source` | enum `default_yaml` \| `request_payload` | No | Product-universe source. Default `default_yaml` (group names under `product_groups` expand; `request_payload` = literal IDs). |
| `product_ids` | `list[str]` | No | Product universe. Default `["bank_recommended"]`. |
| `client_ids` | `list[str]` | Yes | Client IDs to match, passed directly — **no IRS filter**. |
| `market_outlook` | `str` | No | Market narrative for LLM context; falls back to file-globbed market outlook. |
| `top_n` | `int` (1–20) | No | Output limit after descending buying-score sort. Default `3`. |

Response (`LlmProductMatcherResponse`):

| Field | Type | Description |
| --- | --- | --- |
| `run_id` | `str` | Run identifier. |
| `summary` | `object` | `status`, `total_clients`, `top_n_returned`. |
| `llm_product_matcher_markdown` | `str` | The generated report (shared `product_investor_matching` format). |
| `final_proposals` | `list` | Extracted client×product pairs (optional for the POC — derived via `_extract_top_pairs` since the format is identical). |
| `warnings` / `errors` | `list` | Diagnostic lists. |

Flow (single request):

1. Fetch client profiles + holdings by `client_ids` (client API `search_by_id`).
2. Resolve the product universe from `product_ids` / `product_source`.
3. Build the reference payload (client profiles, guidelines, market outlook) — **no PFS, no IRS**.
4. Invoke `run_crew_planbot(proposal_name="llm_product_matcher", ...)` with the `ProductSearch`-armed agent.
5. Return the report markdown (+ optionally extracted pairs).

## 7. Data flow

```
client_ids (direct input) ──► client API search_by_id ──► client profiles + holdings
        │
        ▼
LLM (CrewAI, llm_product_matcher agent)     [no IRS, no PFS]
   ├─ tools: ProductSearch  ──► search_similar ──► DuckDB/adapter product rows
   └─ references: client_profiles (RM notes + holdings), guidelines, market outlook
        │
        ▼
runs/llm_product_matcher/llm_product_matcher.md   (same format as product_investor_matching; no PFS)
```

## 8. Acceptance criteria

| AC ID | Criterion |
| --- | --- |
| AC1 | `ProductSearchTool` invokes `search_similar` and returns ranked products (serialized JSON string). |
| AC2 | `ProductSearchTool` is registered in `_build_tool_instance()` and attached to the `llm_product_matcher` agent. |
| AC3 | `llm_product_matcher` proposal runs end-to-end via `run_crew_planbot` without PFS tables. |
| AC4 | Output follows `proposal_format.md` — contains the Executive Summary 8-column table, per-client detail sections, Alternative suggestion, and References (same structure as `product_investor_matching`). |
| AC5 | Tool parameters (defaults, model, output path) are externalized to YAML, not hard-coded. |
| AC6 | Existing `product_investor_matching` behavior is unchanged. |
| AC7 | Unit tests: one normal flow + one exception path for `ProductSearchTool` (per project standard). |
| AC8 | `POST /api/v1/llm-product-matcher` accepts `client_ids` directly (no IRS) and returns the shared-format report markdown. |

## 9. Outstanding issues

1. **Tool input shape for `search_similar`** — `query` is a nested dict, which some models emit incorrectly. **Resolved**: flatten to top-level fields (`risk_rating`, `expected_return`, `product_type`, …) and build the `query` dict inside `_run` (Option B).
2. **Client universe / IRS** — **Resolved**: `client_id` is a direct endpoint input; the investor-readiness (IRS) filter is bypassed entirely.

## 10. Future enhancements

### 10.1 Web search

Give the LLM a web-search tool so it can gather market/product context on its own, instead of relying solely on the market-outlook references. Options surveyed:

- **Tavily (`TavilySearchTool`)** — bundled in `crewai-tools==1.14.4`, needs `TAVILY_API_KEY`. Search engine (query → ranked results with content). Recommended for production-grade use.
- **DuckDuckGo (`DuckDuckGoSearchTool`)** — keyless, but requires adding `duckduckgo-search` + `langchain-community` dependencies and uses DDG's unofficial API (rate-limited/flaky).
- **Existing scrapers** (`Crawl4AI` / `ScrapeWebsite` / `Firecrawl`) — keyless but URL-only (no keyword discovery); keep as a "fetch a specific URL" companion.

Decision deferred — not part of the POC. When picked, register a new branch in `_build_tool_instance()` and add the tool to `data/planbot/llm_product_matcher/crewai/agents.yaml` `tools`.