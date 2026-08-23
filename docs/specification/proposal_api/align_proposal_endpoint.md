# Objective

The following endpoints eventually output a proposal (a markdown investment recommendation):

| # | Endpoint | Proposal type |
|---|----------|---------------|
| 1 | `POST /api/v1/product-investor-matcher` | Match clients × products, produce a per-pair fit proposal |
| 2 | `POST /api/v1/reinvestment-proposals` | Reinvestment proposal for explicit (client, maturing product) pairs |
| 3 | `POST /api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings` | Discover maturing holdings, then reinvestment proposal per client |
| 4 | `POST /api/v1/product-opportunity-proposal` | Single product-opportunity proposal for one client–product pair |
| 5 | `POST /api/v1/product-opportunity-proposal-automatch` | Batch product-opportunity proposals via product-investor matching |
| 6 | `POST /api/v1/portfolio-review` | Portfolio health review for one client |

This spec singles out the **common input** and **common output** across these six endpoints, so a caller can switch between them with minimal change and so any future proposal endpoint reuses the same contract.  Each proposal keeps additional input/output specific to itself, defined in its own spec.

## Scope

- **Sprint 1 (done)** — aligned the **common output** (canonical `proposal_markdown` + `output_filename`) and the **`market_outlook` + `market_outlook_source`** input across all six endpoints.
- **Sprint 2 (deferred)** — all remaining input/output alignment: `products` representation, `client_id` vs `client_selection`, common control knobs, and the `client_id`/`product_id` identifier naming. Tracked in §Outstanding issues.

# Common input

Every proposal takes the following common inputs.  Where an endpoint does not yet accept a field, it is listed in the alignment matrix (§Alignment) and in §Outstanding issues.

## `client` — target client(s)

Identifies which client(s) the proposal is generated for.

| Field | Type | Notes |
|---|---|---|
| `client_id` | string (comma-delimited list allowed) | Canonical client identifier, e.g. `PB-HK-000007-5`. |
| `client_selection` | object | Alternate form used by the matcher/automatch endpoints: a filter dict passed to the client `search` API. Supported keys: `client_id` (str or list), `risk_rating`, `age`, `product_types_in_holdings`, `concentration_score`, `cash_score`. |

## `products` + `product_source` — product(s) under consideration

Identifies which product(s) the proposal considers.

| Field | Type | Notes |
|---|---|---|
| `product_source` | enum (`default_yaml` \| `request_payload`) | `default_yaml` resolves group/profile names defined in `config_planbot.yaml` under `product_groups`; `request_payload` treats the ids as literal. Default `default_yaml`. |
| `products` (a.k.a. `product_ids`) | string or list | A predefined profile/group name, or one/more literal `product_id`s (comma-delimited accepted). |

In the reinvestment endpoints the "product" is the **maturing source product** (`source_product_id`); in the product-opportunity endpoint it is the **suggested product** (`product_id`).  Conceptually these are all the same "product(s) under consideration" input.

## `market_outlook` + `market_outlook_source` — market narrative

| Field | Type | Notes |
|---|---|---|
| `market_outlook` | string (markdown) | Free-form market narrative injected into the LLM context. |
| `market_outlook_source` | enum (`request` \| `static`) | Selects where the market narrative comes from. Default `request`. |

Sourcing rule:

- `request` — use the `market_outlook` markdown from the request body. If the request omits it, fall back to the static default.
- `static` — ignore the request `market_outlook` and always use the static default (`data/planbot/shared/market_outlook/*.md`).

Precedence for `market_outlook_source` (request overrides config, config supplies the default):

1. Use the request's `market_outlook_source` if provided.
2. Otherwise use the yaml `default_source`.
3. The chosen value then drives resolution per the sourcing rule above.

**YAML change** — encode this behavior explicitly instead of the implicit `source_priority` + `fallback_to_static` pair.  In all four proposals, replace:

```yaml
- id: market_outlook
  source_priority:
    - request.market_outlook_text
    - data/planbot/shared/market_outlook/*.md

# input_policy:
#   per_input:
#     market_outlook: fallback_to_static   # ← removed
```

with:

```yaml
- id: market_outlook
  sources:
    request: request.market_outlook_text
    static: data/planbot/shared/market_outlook/*.md
  default_source: request      # maps to the API field `market_outlook_source`
```

> `sources` (not `source`) is used because `source` is already the engine's resolution-strategy key (`file` / `api` / `runtime_or_static`) in `pipeline_engine.py`.

The `input_policy.per_input.market_outlook: fallback_to_static` entry is removed — the request→static fallback is now expressed by `sources.request` together with `default_source: request`.

**Roll-out (action)** — DONE. All four proposals now use `sources` + `default_source`; all six endpoints accept `market_outlook` + `market_outlook_source`. Internal key note: the engine's request key is `market_outlook_text` (mapped via `sources.request: request.market_outlook_text`); the user-facing API field is `market_outlook`.

## Common control knobs (scoring + response)

The reinvestment endpoints share a set of scoring/response knobs.  These are candidates for promotion to the common input once the other endpoints adopt them:

| Field | Type | Notes |
|---|---|---|
| `max_candidates_per_product_type` | int (1–10) | Diversification cap per product type. Default `2`. |
| `max_candidates_per_client` | int (1–50) | Max candidate products passed to the LLM per client. Default `10`. |
| `risk_rating_hard_filter` | bool | Only products with `risk_rating <= client.risk_rating` are considered. Default `true`. |
| `response_mode` | enum (`path` \| `markdown` \| `both`) | How the proposal is returned. Default `path`. |
| `include_market_outlook` | bool | Render the market outlook section in the proposal. Default `true`. |
| `output_prompt_to_llm` | bool | Include the exact prompt sent to the LLM (as `prompt_to_llm`, per result item). Default `false`. |

# Common output

Every endpoint returns, at minimum, a proposal result carrying:

| Field | Type | Description |
|---|---|---|
| `proposal_markdown` | string | The generated proposal in markdown. (`product_investor_matching_markdown` is the matcher's distinct aggregate-level document.) |
| `output_filename` | string | File path where the markdown was persisted. |

**Naming unification (action)** — DONE. `proposal_markdown` + `output_filename` are now the canonical names across all endpoints (the reinvestment `markdown_output`/`output_path` were renamed). The matcher's `product_investor_matching_markdown` is a distinct aggregate-level field — kept separate.

> `client_id` and `product_id` are **excluded from the common output for now** — each endpoint still returns them in its own specific shape. See §Outstanding issues #7.

The minimum common shape is therefore a per-proposal object carrying the generated markdown and its persisted file path:

```json
{
  "output_filename": "runs/.../<proposal>_<date>.md",
  "proposal_markdown": "# <Proposal>\n\n## Executive Summary\n..."
}
```

Multi-client endpoints (reinvestment, matcher, automatch) wrap this object in a list (`results_by_client`, `final_proposals`, or `proposals`) and add a top-level status/summary block.  Single-client endpoints (product-opportunity, portfolio-review) return the object directly.

# Alignment

Current state of each endpoint against the common input/output above.  ✅ = conforms, ⚠️ = differs (see note).

| Endpoint | `client` | `products`/`product_source` | `market_outlook` (markdown) | `market_outlook_source` | Common output shape |
|---|---|---|---|---|---|
| `product-investor-matcher` | ✅ (`client_selection`) | ✅ (`product_source` + `product_ids`) | ✅ | ✅ | ⚠️ aggregate `product_investor_matching_markdown` + `final_proposals[].proposal_markdown` (no per-proposal `output_filename`) |
| `reinvestment-proposals` | ⚠️ `reinvestment_targets[].client_id` | ⚠️ `reinvestment_targets[].source_product_id` | ✅ | ✅ | ✅ |
| `reinvestment-proposals/propose_reinvestment_for_maturing_holdings` | ❌ (discovers clients) | ❌ (discovers maturing product) | ✅ | ✅ | ✅ |
| `product-opportunity-proposal` | ✅ (`client_id`) | ✅ (`product_id`) | ✅ | ✅ | ✅ |
| `product-opportunity-proposal-automatch` | ✅ (`client_selection`) | ✅ (`product_source` + `product_ids`) | ✅ | ✅ | ✅ |
| `portfolio-review` | ✅ (`client_id`) | — (no product input) | ✅ | ✅ | ✅ |

# Outstanding issues

All items below are deferred to **Sprint 2**.

1. **`products` representation** (Sprint 2) — The note above says "comma-delimited `product_id`", but the API currently models this as `product_ids: list[str]` (and `product_source` as an enum).  Should the common input be a comma-delimited string, a list, or both accepted?
2. **`client_id` vs `client_selection`** (Sprint 2) — Three endpoints take a plain `client_id` (or `reinvestment_targets[].client_id`), while the matcher and automatch take a `client_selection` filter dict.  Should these unify on one common "client" input, and if so which form?
5. **Common control knobs** (Sprint 2) — `response_mode`, `include_*`, and the scoring knobs exist only on the reinvestment endpoints.  Are they meant to become part of the common input for all proposals, or remain reinvestment-specific?
6. **`product_id` vs `source_product_id` vs `candidate_product_id`** (Sprint 2) — The reinvestment response's `candidate_products[].product_id` is actually a **candidate** product id (a replacement candidate), not the input product; the input product is `source_product_id`. This makes `product_id` ambiguous, which is one reason it is held out of the common output (§#7). Consider renaming `candidate_products[].product_id` → `candidate_product_id` for clarity.
7. **`client_id` / `product_id` excluded from common output** (Sprint 2) — For now the minimum common output is only `proposal_markdown` + `output_filename`. `client_id` and `product_id` are excluded because their naming and semantics still vary per endpoint (see the naming-unification action in §Common output and §#6). Revisit adding them back once the field-name unification and candidate-id naming are settled.