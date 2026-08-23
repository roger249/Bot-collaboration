# Prompt / Debug Output Standardization (Discussion)

> Status: Draft — for discussion. No implementation.

## 1. Objective

Standardize how each proposal endpoint returns "what was sent to the LLM" for
diagnostics. The new `llm-product-matcher` endpoint introduced the canonical
pair — **`output_prompt_to_llm` (input) → `prompt_to_llm` (output)** — but the
four other proposals still rely on a different, inconsistent set of flags.
This doc (a) proposes adding the new pair to the four others, and (b) surfaces
the overlapping flags so we can decide whether to merge them.

## 2. Current state

### 2.1 Proposal types vs. endpoints

| Proposal type | Endpoint(s) |
|---|---|
| `product_investor_matching` | `POST /api/v1/product-investor-matcher` |
| `reinvestment` | `POST /api/v1/reinvestment-proposals`, `POST .../propose_reinvestment_for_maturing_holdings` |
| `product_opportunity` | `POST /api/v1/product-opportunity-proposal`, `POST .../product-opportunity-proposal-automatch` |
| `portfolio_review` | `POST /api/v1/portfolio-review` |
| `llm_product_matcher` (new) | `POST /api/v1/llm-product-matcher` |

### 2.2 Debug / prompt-related inputs and outputs today

| Proposal | Debug/prompt inputs | Debug/prompt outputs |
|---|---|---|
| `llm_product_matcher` | `output_prompt_to_llm` (bool) | `prompt_to_llm` (str — exact `prompt_snapshot.md`) |
| `reinvestment` (both endpoints) | `include_llm_input`, `include_debug_scores`, `include_market_outlook`, `response_mode` | `llm_input` (structured summary), `debug_scores` (scorecard) |
| `product_investor_matching` | — | — |
| `product_opportunity` | — | `metadata` (dict — partial) |
| `portfolio_review` | — | — |

### 2.3 Two different "prompt" concepts already exist

| Mechanism | Returns | Is it the actual prompt? |
|---|---|---|
| `include_llm_input` → `llm_input` | `build_llm_input()` — a **curated structured summary** (client_profile, holdings, source_product, candidates, output_instructions) | **No** |
| `prompt_snapshot.md` (always written by `run_crew_planbot`) | task prompt + full reference sections, Markdown | **Yes** (user-prompt side) |

Key observation: `include_llm_input` is a **misnomer** — it returns a *summary
of inputs*, not the prompt sent to the LLM. The thing that actually captures the
prompt (`prompt_snapshot.md`) is written to disk on every run but never surfaced
in any API response (only `PlanBotResult.prompt_path`, consumed internally).

## 3. Proposal — add `output_prompt_to_llm` / `prompt_to_llm` to the four others

Add the canonical pair to `product_investor_matching`, `reinvestment`,
`product_opportunity`, and `portfolio_review`:

- **Input**: `output_prompt_to_llm: bool = false` — one **top-level** request
  flag controlling the whole API call.
- **Output**: `prompt_to_llm: str | None` — emitted **per proposal item**
  (inside each result object in the list — `results_by_client[]`, `proposals[]`,
  `final_proposals[]`, or the single-client response body), holding the exact
  `prompt_snapshot.md` content for that item's LLM call. It is present
  (non-null) only when the flag is true. It is **declared in the Pydantic
  response model** (`response_model`) so it appears in the OpenAPI schema,
  rather than added dynamically like the legacy `llm_input`/`debug_scores`
  fields were.

  The request flag stays top-level (one switch for the whole call); the response
  field is per-item because each item corresponds to one LLM invocation and
  therefore one prompt. For the single-call matcher (`product_investor_matching`),
  the aggregate `product_investor_matching_markdown` has one prompt, so
  `prompt_to_llm` is attached to that aggregate object.

Decisions folded in (from the earlier discussion):

- **Drop `include_llm_input` / `llm_input`** — the full prompt snapshot
  supersedes the curated summary; retire `build_llm_input()` in the same change.
- **Drop `include_debug_scores` / `debug_scores`** — the prompt already carries
  the inputs the scorecard derives from.
- **Keep `include_market_outlook`** — it is a *content* toggle (renders the
  market-outlook section in the proposal), not a debug flag.
- **Naming** — keep `output_prompt_to_llm`. Convention: `include_*` means
  "include X **into the prompt**" (a content toggle, e.g. `include_market_outlook`,
  `include_references`), whereas `output_*` means "emit X **in the API
  response**". Since this flag controls the response payload (not the prompt
  content), `output_prompt_to_llm` is the correct name — `include_prompt_to_llm`
  would be misleading. The two API `include_*` debug flags are dropped in this
  refactor anyway, so no renaming ambiguity remains.

Implementation is trivial and uniform: `run_crew_planbot` already returns
`PlanBotResult.prompt_path`, so each integration just reads that file (or the
already-composed snapshot string) and echoes it back — identical to what
`llm_product_matcher.py` already does.

> **Scope note**: this returns the **user-prompt side only** (the
> `prompt_snapshot.md` scope). The CrewAI system prompt (agent role/goal/
> backstory + tool schemas) is *not* captured here. Deeper diagnostics (tool
> interaction, ReAct loop) remain the job of `log/crewai_trace.log` — out of
> scope for the API response.

## 4. Flag decisions

Adding `output_prompt_to_llm` to the reinvestment endpoints overlapped with two
existing flags there. The decisions below resolve those overlaps.

### 4.1 `include_llm_input` (→ `llm_input`) vs. `output_prompt_to_llm` (→ `prompt_to_llm`)

These are the closest analogues, and they serve *different* purposes:

| | `include_llm_input` / `llm_input` | `output_prompt_to_llm` / `prompt_to_llm` |
|---|---|---|
| Content | Curated **structured summary** (a subset of fields, re-keyed) | **Exact** prompt snapshot (task + full references) |
| Shape | JSON dict | Markdown string |
| Value | Compact, machine-parseable | Faithful, human-readable, "what the LLM actually saw" |

**Decision: drop `include_llm_input` entirely, retain only `output_prompt_to_llm`.**

The full prompt snapshot (`prompt_to_llm`) supersedes the curated summary — it
contains *all* the inputs in their final, prompt-ready form, so the re-keyed
`build_llm_input()` subset adds no diagnostic value beyond what the prompt
already exposes. Rationale:

- **One source of truth** — `prompt_snapshot.md` is what the LLM actually
  consumed; a separately-assembled `llm_input` can drift from it.
- **Less surface** — one flag instead of two, no misnomer to maintain.
- **Programmatic consumers lose little** — the prompt snapshot is deterministic
  Markdown; anything machine-parseable in `llm_input` is already recoverable by
  parsing the snapshot or calling the data APIs directly.

Consequently `build_llm_input()` is retired (or demoted to internal-only) and the
`include_llm_input` field is removed from both reinvestment endpoints, together
with its tests (`test_reinvestment_proposal.py::test_include_llm_input_*`,
`test_build_llm_input_*`).

### 4.2 `include_debug_scores` (→ `debug_scores`)

A third "debug" flag, also reinvestment-only. It returns the intermediate
scorecard (readiness + candidate similarity).

**Decision: drop `include_debug_scores` entirely.**

The full prompt snapshot (`prompt_to_llm`) already carries the inputs that the
scorecard is derived from; the intermediate readiness/similarity numbers add
little beyond what the prompt exposes. This leaves a single diagnostic flag —
`output_prompt_to_llm` — with no grouping question to resolve.

### 4.3 `include_market_outlook` (content toggle, NOT a debug flag)

Unlike the two flags above, `include_market_outlook` controls the **content of
the proposal itself** (whether the market-outlook section is rendered), not
whether diagnostic data is returned. It is **kept as-is** and is the only
surviving `include_*` request field after the two drops. Its `include_` prefix
is therefore no longer part of a "debug family" — it's a content knob.

### 4.4 `response_mode` (`path` / `markdown` / `both`)

Reinvestment-only. It's orthogonal (it controls *which* core output is returned,
not diagnostics). **Rule (confirmed): diagnostic flags are independent of
`response_mode`** — `output_prompt_to_llm` returns `prompt_to_llm` on top of
whatever the mode returns, and is **not** gated/suppressed by `response_mode`.
This matches how the existing `include_*` flags already behave.

## 5. Open questions

*None outstanding.*

## Appendix A — the `include_*` inventory

`include_*` appears in **four different scopes**; only the first is API-facing.

**1. API request fields (reinvestment endpoints only):**

| Field | Default | Purpose | Category | Fate |
|---|---|---|---|---|
| `include_llm_input` | `false` | return `llm_input` (structured input summary) | debug | **drop** (§4.1) |
| `include_debug_scores` | `false` | return `debug_scores` (scorecard) | debug | **drop** (§4.2) |
| `include_market_outlook` | `true` | render market-outlook section in the *proposal* | content | keep |

**2. Prompt-packaging YAML** (`config_planbot.yaml` → `pipeline.<id>.prompt_packaging.llm_payload`):

- `include_references: true` — whether the reference JSON payload is included in the prompt.

**3. Pipeline input `include` flags** (`pipeline.<id>.inputs[].include`, consumed
as `include_by_id`):

- e.g. `client_profile.include.investor_readiness_score: true` — whether the IRS
  section is rendered into the client profile reference.
- e.g. `product_catalog.include.product_fitness_scores` — whether the PFS table
  is appended.

**4. Internal helpers / tool args** (not API-facing):

- Formatters: `include_suggested_section`, `include_holdings_section`,
  `include_alternatives_section`.
- YFinance tool: `include_quote_summary`, `include_financial_statement`,
  `include_price_history`.

> Note: `include_candidate_explanations` appears only in the reinvestment API
> spec doc (`reinvestment_proposal_api.md`), **not** in the implementation.
