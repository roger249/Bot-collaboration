# LLM Product Matcher (POC)

> Status: Draft. Proof-of-concept spec.

## 1. Overview

The current `product_investor_matching` flow (see `config/config_planbot.yaml`) pre-computes a **Product Fitness Score (PFS)** over a preselected product set, then hands the ranked results to the LLM. The LLM's role is therefore limited to re-ranking already-scored candidates.

This POC inverts that responsibility: the LLM performs product matching itself by querying the product catalog through a tool (`search_similar`) — **without any pre-computed PFS**. Web search is provided by **SerpApi** + **`ScrapeWebsiteTool`** (see §4.2); **Tavily** is a future enhancement (see §10). The report **must use the same output format as the current `product_investor_matching`** (see §5).

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
- **Web search** via **SerpApi** (search engine) + **`ScrapeWebsiteTool`** (URL fetch) — see §4.2.

### Out of scope (POC)

- **Tavily** (and DuckDuckGo) web search — deferred to §10.
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

### 4.2 Web search tools (SerpApi + `ScrapeWebsiteTool`)

The LLM needs to gather market/product context beyond the static market-outlook references. Two tools, used as a **pair**:

1. **`SerpApiGoogleSearchTool`** — **search engine**. Google/Google News keyword search via the SerpApi service. Requires `SERPAPI_API_KEY` and a billed SerpApi account. Returns ranked organic results (title + link + snippet).
2. **`ScrapeWebsiteTool`** — **URL fetcher**. Keyless, bundled in `crewai-tools`. Takes a specific URL and returns its page content. It cannot discover URLs on its own, so it is paired with the search engine: *SerpApi finds → ScrapeWebsiteTool fetches*.

> `SerperDevTool` is a **different** provider (Serper.dev, key `SERPER_API_KEY`) — listed here only as a possible drop-in alternative, not the default.

Configuration (externalized to YAML, per AC5):

| Field | Source | Default | Notes |
|---|---|---|---|
| `serpapi_api_key` | env `SERPAPI_API_KEY` | — | Required for the search tool. |
| `serpapi_search_tool` | `config_planbot.yaml` | enabled | Toggle to disable web search. |
| `scrape_website_tool` | `config_planbot.yaml` | enabled | Toggle for the URL fetcher. |

Registration & attachment:

- `SerpApiGoogleSearchTool`: add a branch in `_build_tool_instance()` in `src/planbot/crew_workflow.py` (like `ProductSearch`); the `serpapi` package is required (the tool imports `from serpapi import Client`) and must be added to `pyproject.toml`.
- `ScrapeWebsiteTool`: **already registered** in `_build_tool_instance()` — no code change, only a `tools:` entry.
- Both are listed under the agent's `tools` field in `data/planbot/llm_product_matcher/crewai/agents.yaml` alongside `ProductSearch`.

## 5. New proposal definition

Add a `llm_product_matcher` section to `config/config_planbot.yaml` under `pipeline:`, modeled on `product_investor_matching` (the **current** pipeline format, not the legacy top-level `references` block). The CrewAI keys (`task`, `crewai_config_folder`, `output_root`, `output_filename`, `llm_model`) are **derived from the pipeline id** per the config-consolidation rule, so they are not repeated in YAML:

```yaml
pipeline:
  llm_product_matcher:
    # No `matcher:` block — there is no IRS readiness pool and no downstream
    # `_extract_top_pairs` parsing in this POC (see §3 Out of scope).

    execution:
      model: deepseek_tool
      output:
        folder: runs/llm_product_matcher
        filename_template: llm_product_matcher_{date}.md
      logging:
        level: INFO

    inputs:
      - id: proposal_instructions
        source: file
        paths:
          - data/planbot/llm_product_matcher/proposal_instructions/*.md
        prompt_section: references
        required: true
      - id: section_guides
        source: file
        paths:
          - data/planbot/shared/proposal_section_instructions/*.md
        prompt_section: references
        required: true
      - id: general_guidelines
        source: file
        paths:
          - data/planbot/shared/common/general_guideline.md
        prompt_section: references
        required: true
      - id: financial_needs_guidelines
        source: file
        paths:
          - data/planbot/shared/financial_needs/*.md
        prompt_section: references
        required: true
      - id: client_profile
        required: true
        include:
          investor_readiness_score: true   # readiness score + RM notes fed as reference (no IRS gate)
      - id: market_outlook
        sources:
          request: request.market_outlook_text
          static: data/planbot/shared/market_outlook/*.md
        default_source: request

    input_policy:
      missing_data:
        default: skip
      per_input:
        client_profile: error

    prompt_packaging:
      llm_payload:
        include_references: true

    quality_gates:
      required_sections:
        - client_profile
      fail_on_missing_required_input: true
```

> `client_profile` keeps `investor_readiness_score: true` (the score is shown as reference context) but **no IRS gate** is applied — `client_id` is supplied directly. There is **no `product_catalog` input**: product discovery is done entirely by the LLM through `ProductSearch`, so no pre-rendered product universe (and hence no PFS table) is fed as a reference.

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

Because there is **no PFS** in this POC, the `Fitness Score` column is **decided by the LLM**: it produces its own suitability estimate on a **1–5** scale (mirroring the buying-score scale) **and must provide a justification** for the score in the rationale. The 1–5 scale is intentional for this POC and differs from the current PFS `fitness_score` (0–10) — it is a standalone LLM judgement, not a re-expression of the pre-computed PFS. The section/column structure is preserved by reusing the same `proposal_format.md` + task prompt; the task prompt's PFS-specific guidance is replaced with an instruction for the LLM to derive and justify its own 1–5 fitness score from `search_similar` results, client profile, and market outlook.

The POC is exposed through the endpoint defined in §6 (which invokes `run_crew_planbot(proposal_name="llm_product_matcher", ...)` under the hood).

## 6. API endpoint

### 6.1 `POST /api/v1/llm-product-matcher`

Modeled on `/api/v1/product-opportunity-proposal-automatch`, but the client is supplied **directly** (`client_id`), so the investor-readiness (IRS) scorecard gate is **not** applied. The client profile is fetched via the client API and fed to the LLM as references. The product universe is **not an input** — the LLM discovers products itself through `ProductSearch` (which searches the full DuckDB catalog directly), so there is no `product_source` / `product_ids` request field.

Request (`LlmProductMatcherRequest`):

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `client_id` | `str` | Yes | Client ID to match, passed directly — **no IRS filter**. |
| `market_outlook` | `str` | No | Market narrative for LLM context; falls back to file-globbed market outlook. |
| `market_outlook_source` | enum `request` \| `static` | No | Where the market narrative comes from. Default `request` (via yaml `default_source`). `static` ignores `market_outlook` and always uses the static default. |
| `top_n` | `int` (1–20) | No | Output limit after descending buying-score sort. Default `3`. |

Response (`LlmProductMatcherResponse`):

| Field | Type | Description |
| --- | --- | --- |
| `run_id` | `str` | Run identifier. |
| `summary` | `object` | `status`, `total_clients`, `top_n_returned`. |
| `output_filename` | `str` | File path where the report markdown was persisted (canonical common output — see `proposal_api_common_contract.md`). |
| `llm_product_matcher_markdown` | `str` | The aggregate report markdown (shared `product_investor_matching` format). Distinct aggregate-level field, mirroring `product_investor_matching_markdown` — **not** the per-proposal `proposal_markdown`. |
| `warnings` / `errors` | `list` | Diagnostic lists. |

> `final_proposals` (extracted client×product pairs via `_extract_top_pairs`) is **not returned** in this POC — downstream parsing is out of scope (see §3). It will be added later, at which point each item will carry `client_id`, `product_id`, and the canonical `proposal_markdown` (mirrors `MatcherProposal`).

This response conforms to the common output contract: the aggregate document is a distinct field (`llm_product_matcher_markdown`, mirroring `product_investor_matching_markdown`) alongside the canonical `output_filename`.

Flow (single request):

1. Fetch the client profile + holdings by `client_id` (client API `search_by_id`).
2. Build the reference payload (client profiles, guidelines, market outlook) — **no PFS, no IRS, no product universe**.
3. Invoke `run_crew_planbot(proposal_name="llm_product_matcher", ...)` with the `ProductSearch`-armed agent (the LLM discovers products via `search_similar`).
4. Return `output_filename` + the report markdown (`llm_product_matcher_markdown`).

## 7. Data flow

```
client_id (direct input) ──► client API search_by_id ──► client profile + holdings
        │
        ▼
LLM (CrewAI, llm_product_matcher agent)     [no IRS, no PFS]
   ├─ tools: ProductSearch  ──► search_similar ──► DuckDB/adapter product rows
   ├─ tools: SerpApiSearch  ──► web search ──► ranked URLs
   ├─ tools: ScrapeWebsite  ──► fetch URL content ──► market/product context
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
| AC8 | `POST /api/v1/llm-product-matcher` accepts `client_id` directly (no IRS) and returns the shared-format report markdown. |
| AC9 | `SerpApiGoogleSearchTool` is registered in `_build_tool_instance()` and attached to the `llm_product_matcher` agent (alongside `ScrapeWebsiteTool`), and its API key is read from env `SERPAPI_API_KEY`. |

## 9. Outstanding issues

*None outstanding.*

## 10. Future enhancements

### 10.1 Web search — Tavily (future)

**SerpApi + `ScrapeWebsiteTool` are the current pairing** (§4.2). This section covers the deferred alternative engines for future evaluation:

- **Tavily (`TavilySearchTool`)** — bundled in `crewai-tools==1.14.4`, needs `TAVILY_API_KEY`. Search engine (query → ranked results with content). Candidate to replace SerpApi if SerpApi's Google-search licensing/billing becomes a constraint.
- **DuckDuckGo (`DuckDuckGoSearchTool`)** — keyless, but requires adding `duckduckgo-search` + `langchain-community` dependencies and uses DDG's unofficial API (rate-limited/flaky).

Decision deferred — not part of the current POC. When picked, register a new branch in `_build_tool_instance()` (Tavily / DuckDuckGo need a branch; `ScrapeWebsiteTool` already has one) and add the tool to `data/planbot/llm_product_matcher/crewai/agents.yaml` `tools`. The recommended shape remains a search engine + `ScrapeWebsiteTool`: the search engine discovers URLs, `ScrapeWebsiteTool` fetches their full content.