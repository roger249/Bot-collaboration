# Proposal API — Common Input / Output Contract

> Reference for building a **new** proposal endpoint. Captures the *current*
> (implemented) common input and output shared by all proposal endpoints, so a
> new endpoint reuses the same contract with minimal friction.
>
> Source of truth: `src/integrations/proposal_server.py` (Pydantic models) and
> `docs/specification/data_api/openapi_proposal.json` (proposal server OpenAPI).
> See `align_proposal_endpoint.md` for the full rationale, per-endpoint alignment
> matrix, and Sprint-2 deferred items.

## Endpoints covered

| Endpoint | Proposal type |
|---|---|
| `POST /api/v1/product-investor-matcher` | Match clients × products, per-pair fit proposal |
| `POST /api/v1/reinvestment-proposals` | Reinvestment for explicit (client, maturing product) pairs |
| `POST /api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings` | Discover maturing holdings → reinvestment per client |
| `POST /api/v1/product-opportunity-proposal` | Single product-opportunity proposal (one pair) |
| `POST /api/v1/product-opportunity-proposal-automatch` | Batch product-opportunity via matching |
| `POST /api/v1/portfolio-review` | Portfolio health review (one client) |
| `POST /api/v1/llm-product-matcher` | LLM-driven product matching for one client (no IRS/PFS) |

---

## Common input

A new proposal endpoint should accept these fields (plus its own specifics).

### Target client

| Field | Type | Required | Notes |
|---|---|---|---|
| `client_id` | string | * | Canonical client identifier, e.g. `PB-HK-000007-5`. Single value for single-client endpoints. |
| `client_selection` | object | * | Filter dict for batch endpoints (matcher/automatch). Keys: `client_id` (str or list), `risk_rating` (int or `[min,max]`), `age`, `product_types_in_holdings`, `concentration_score`, `cash_score`. |

\* A proposal takes **one** of these two forms, not both. Single-client endpoints use `client_id`; batch endpoints use `client_selection`.

### Product(s) under consideration

| Field | Type | Default | Notes |
|---|---|---|---|
| `product_source` | enum | `default_yaml` | `default_yaml` resolves `product_groups` profile names in `config_planbot.yaml`; `request_payload` treats ids as literal. |
| `product_ids` (a.k.a. `products`) | `list[str]` | varies | Profile/group names or literal `product_id`s. |

Single-pair endpoints express the product differently (see per-endpoint below):
reinvestment uses `source_product_id` (maturing product); opportunity uses
`product_id` (suggested product). Conceptually both are "the product under
consideration".

### Market narrative

| Field | Type | Default | Notes |
|---|---|---|---|
| `market_outlook` | string (markdown) | `null` | Free-form market narrative injected into the LLM context. |
| `market_outlook_source` | enum | `request` (via yaml `default_source`) | `request` → use `market_outlook`, fall back to static; `static` → always use the static default. |

Precedence for `market_outlook_source`: request field → yaml `default_source`
(`config_planbot.yaml` → `pipeline.<id>.inputs[].default_source`) → `request`.
The static default is `data/planbot/shared/market_outlook/*.md`.

---

## Common output

Every endpoint returns a proposal result carrying, at minimum:

| Field | Type | Notes |
|---|---|---|
| `proposal_markdown` | string | The generated proposal in markdown. |
| `output_filename` | string | File path where the markdown was persisted. |

Minimum shape (single-proposal endpoints return this directly):

```json
{
  "output_filename": "runs/<proposal>/<proposal>_<client_id>_<date>.md",
  "proposal_markdown": "# <Proposal>\n\n## Executive Summary\n..."
}
```

Multi-client endpoints wrap this in a list (`results_by_client`, `final_proposals`,
or `proposals`) plus a top-level status/summary block.

> `client_id` / `product_id` are **not** part of the common output (deferred to
> Sprint 2 — their naming/semantics still vary per endpoint). Each endpoint
> still returns them in its own shape.

---

## Common control knobs (reinvestment endpoints today)

Candidate for promotion to common input in a later sprint. Currently present on
the two reinvestment endpoints only:

| Field | Type | Default | Notes |
|---|---|---|---|
| `max_candidates_per_product_type` | int (1–10) | `2` | Diversification cap per product type. |
| `max_candidates_per_client` | int (1–50) | `10` | Max candidates passed to the LLM per client. |
| `risk_rating_hard_filter` | bool | `true` | Only products with `risk_rating <= client.risk_rating`. |
| `response_mode` | enum | `path` | `path` / `markdown` / `both`. |
| `include_market_outlook` | bool | `true` | Render the market outlook section in the proposal. |
| `output_prompt_to_llm` | bool | `false` | Include the exact prompt sent to the LLM (as `prompt_to_llm`, per result item). |

---

## Per-endpoint input / output

### 1. product-investor-matcher

Input: `product_source`, `product_ids`, `client_selection`, `top_n` (default 3),
`market_outlook`, `market_outlook_source`.

Output:

```json
{
  "run_id": "run-...",
  "summary": { "status": "success", "total_clients_retrieved": 0, "clients_after_readiness": 0, "top_n_returned": 0 },
  "product_investor_matching_markdown": "...",
  "final_proposals": [
    { "client_id": "...", "product_id": "...", "investment_amount": "", "funding_source": "",
      "buying_score": 0, "rationale": "", "proposal_markdown": "...", "error": null }
  ],
  "warnings": [],
  "errors": []
}
```

### 2. reinvestment-proposals

Input: `reinvestment_targets` (`[{client_id, source_product_id}]`, min 1), plus
the common control knobs, `market_outlook`, `market_outlook_source`.

Output:

```json
{
  "status": "success",
  "results_by_client": [
    { "client_id": "...", "source_product_id": "...", "candidate_products": [...],
      "output_filename": "...", "proposal_markdown": "...", "error": null }
  ]
}
```

### 3. propose_reinvestment_for_maturing_holdings

Input: `within_days` (default 365), `as_of_date`, `max_clients` (default 2), plus
the common control knobs, `market_outlook`, `market_outlook_source`.

Output: same shape as endpoint 2.

### 4. product-opportunity-proposal

Input: `client_id`, `product_id`, `rationale` (default `""`),
`suggested_products_and_rationale` (default `""`), `run_matcher` (default false),
`market_outlook`, `market_outlook_source`, `alternative_count` (default 3).

Output:

```json
{
  "client_id": "...",
  "product_id": "...",
  "output_filename": "...",
  "proposal_markdown": "...",
  "metadata": {}
}
```

### 5. product-opportunity-proposal-automatch

Input: `product_source`, `product_ids` (default `["bank_recommended"]`),
`client_selection`, `run_matcher` (default false), `max_proposals` (default 10),
`market_outlook`, `market_outlook_source`.

Output:

```json
{
  "matcher_run_id": "...",
  "total_clients_matched": 0,
  "total_proposals_generated": 0,
  "proposals": [
    { "client_id": "...", "product_id": "...", "output_filename": "...",
      "proposal_markdown": "...", "metadata": {} }
  ],
  "errors": []
}
```

### 6. portfolio-review

Input: `client_id`, `market_outlook`, `market_outlook_source`.

Output:

```json
{
  "client_id": "...",
  "output_filename": "...",
  "proposal_markdown": "..."
}
```

### 7. llm-product-matcher

Input: `client_id`, `market_outlook`, `market_outlook_source`,
`output_prompt_to_llm` (default `false`).

Output:

```json
{
  "client_id": "...",
  "output_filename": "...",
  "proposal_markdown": "...",
  "prompt_to_llm": "# Prompt Snapshot\n..."
}
```

> `prompt_to_llm` is present only when `output_prompt_to_llm=true`.  The LLM
discovers products itself via the `ProductSearchTool` tool and web research, so there
is no `product_source` / `product_ids` input, and no investor-readiness (IRS)
filter is applied.

---

## Checklist for a new proposal endpoint

1. Accept `client_id` **or** `client_selection` per single/batch semantics.
2. Accept `market_outlook` + `market_outlook_source` (both optional).
3. Return `proposal_markdown` + `output_filename` (canonical common output).
4. If it selects products, reuse `product_source` + `product_ids`.
5. Regenerate specs with `./.venv/bin/python scripts/export_openapi.py`.
6. Add a normal-flow + exception unit test (minimal regression pair).
