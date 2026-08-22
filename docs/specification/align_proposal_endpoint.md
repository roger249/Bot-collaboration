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

## `market_outlook` — market narrative

| Field | Type | Notes |
|---|---|---|
| `market_outlook` | string (markdown) | Free-form market narrative injected into the LLM context. |

Design rule: `market_outlook` **shall come from the request**, not from static config files.  Today the pipeline config still declares a static fallback (`data/planbot/shared/market_outlook/*.md`) in `source_priority`, and the two reinvestment endpoints accept only an `include_market_outlook: bool` rather than the markdown string.  See §Outstanding issues #3.

## Common control knobs (scoring + response)

The reinvestment endpoints share a set of scoring/response knobs.  These are candidates for promotion to the common input once the other endpoints adopt them:

| Field | Type | Notes |
|---|---|---|
| `max_candidates_per_product_type` | int (1–10) | Diversification cap per product type. Default `2`. |
| `max_candidates_per_client` | int (1–50) | Max candidate products passed to the LLM per client. Default `10`. |
| `risk_rating_hard_filter` | bool | Only products with `risk_rating <= client.risk_rating` are considered. Default `true`. |
| `response_mode` | enum (`path` \| `markdown` \| `both`) | How the proposal is returned. Default `path`. |
| `include_llm_input` | bool | Include the assembled LLM prompt in the response. Default `false`. |
| `include_market_outlook` | bool | Include the market outlook section. Default `true`. |
| `include_debug_scores` | bool | Include debug scoring details. Default `false`. |

# Common output

Every endpoint returns, at minimum, a proposal result carrying:

| Field | Type | Description |
|---|---|---|
| `proposal_markdown` | string | The generated proposal in markdown. (Named `markdown_output` in the reinvestment endpoints; `product_investor_matching_markdown` for the matcher's aggregate document.) |
| `output_filename` (a.k.a. `output_path`) | string | File path where the markdown was persisted. |
| `client_id` | string | Maps the result back to its input client. |
| `product_id` (a.k.a. `source_product_id`) | string | Maps the result back to its input product. |

The minimum common shape is therefore a per-proposal object that pairs the generated markdown with the identifiers that produced it:

```json
{
  "client_id": "PB-HK-000007-5",
  "product_id": "PROD054",
  "output_filename": "runs/.../<proposal>_PB-HK-000007-5_<date>.md",
  "proposal_markdown": "# <Proposal>\n\n## Executive Summary\n..."
}
```

Multi-client endpoints (reinvestment, matcher, automatch) wrap this object in a list (`results_by_client`, `final_proposals`, or `proposals`) and add a top-level status/summary block.  Single-client endpoints (product-opportunity, portfolio-review) return the object directly.

# Alignment

Current state of each endpoint against the common input/output above.  ✅ = conforms, ⚠️ = differs (see note).

| Endpoint | `client` | `products`/`product_source` | `market_outlook` (markdown) | Common output shape |
|---|---|---|---|---|
| `product-investor-matcher` | ✅ (`client_selection`) | ✅ (`product_source` + `product_ids`) | ✅ | ⚠️ aggregate `product_investor_matching_markdown` + `final_proposals[].proposal_markdown` |
| `reinvestment-proposals` | ⚠️ `reinvestment_targets[].client_id` | ⚠️ `reinvestment_targets[].source_product_id` | ❌ (only `include_market_outlook: bool`) | ⚠️ `results_by_client[].markdown_output` |
| `reinvestment-proposals/propose_reinvestment_for_maturing_holdings` | ❌ (discovers clients) | ❌ (discovers maturing product) | ❌ (only `include_market_outlook: bool`) | ⚠️ `results_by_client[].markdown_output` |
| `product-opportunity-proposal` | ✅ (`client_id`) | ✅ (`product_id`) | ✅ | ✅ |
| `product-opportunity-proposal-automatch` | ✅ (`client_selection`) | ✅ (`product_source` + `product_ids`) | ❌ (absent) | ⚠️ `proposals[].proposal_markdown` |
| `portfolio-review` | ✅ (`client_id`) | — (no product input) | ✅ | ✅ |

# Outstanding issues

1. **`products` representation** — The note above says "comma-delimited `product_id`", but the API currently models this as `product_ids: list[str]` (and `product_source` as an enum).  Should the common input be a comma-delimited string, a list, or both accepted?
2. **`client_id` vs `client_selection`** — Three endpoints take a plain `client_id` (or `reinvestment_targets[].client_id`), while the matcher and automatch take a `client_selection` filter dict.  Should these unify on one common "client" input, and if so which form?
3. **`market_outlook` sourcing** — The design rule says the markdown must come from the request and the yaml must stop taking it from static files.  Two things block this: (a) the reinvestment endpoints accept only `include_market_outlook: bool`, not a `market_outlook` string; (b) `product-opportunity-proposal-automatch` has no `market_outlook` field at all.  Confirm the intended direction, then update the yaml `source_priority` (remove the `data/planbot/shared/market_outlook/*.md` fallback) and add the field to the missing endpoints.  Also note the internal naming mismatch: request field `market_outlook` vs pipeline `request_contract` key `market_outlook_text`.
4. **Common output field names** — `proposal_markdown` vs `markdown_output` vs `product_investor_matching_markdown`, and `output_filename` vs `output_path`, are inconsistent.  Should these be renamed to a single canonical set?
5. **Common control knobs** — `response_mode`, `include_*`, and the scoring knobs exist only on the reinvestment endpoints.  Are they meant to become part of the common input for all proposals, or remain reinvestment-specific?