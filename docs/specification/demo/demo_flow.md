# Proposal Server — Demo Flow

> **Status**: Draft — flow only.  Concrete client/product IDs, test-data
> mutations, and a runnable demo script are filled in during the next phase.

This document defines the end-to-end demo of the proposal server.  It walks
through three scenarios, each demonstrating a distinct capability of the
product–client matcher and the proposal pipeline.

> Exact client/product IDs and the test-data baseline are pinned in
> `docs/specification/demo/demo_test_data.md`.  The HTTP mutation/reset surface
> is specified in `docs/specification/demo/demo_tool_api.md`.

## Demo cases

| # | Story | What it proves |
|---|---|---|
| 1 | The RM note shapes the recommendation | The LLM changes the recommended product (and its narrative) when the client's `qualitative_profile` (RM note) is edited. |
| 2 | Structured products can be proposed | The matcher surfaces structured products (FX TARF/accumulator) for a suitable client. |
| 3 | Reinvestment on maturity | The server discovers maturing holdings and recommends a replacement product. |

Each demo is **scriptable**: one API call (or a before/after pair of calls) with
a single observable assertion.

---

## Prerequisites

1. The proposal server is running (see `README.md` §1–3), with:
   - `BACHERLIER_API_KEY` (and/or the provider key backing the configured model) set.
   - DuckDB test data seeded (`data/planbot/db/planbot.duckdb`).
2. Swagger UI at `http://localhost:8000/docs` for ad-hoc calls, or a small script
   that posts to the endpoints below.
3. The FX TARF products + tuned clients from
   `docs/how_to/how_to_add_fx_tarf.md` are present (6 `FX-TARF-*` products;
   clients `PB-HK-000002-6`, `PB-HK-000009-1`, `PB-HK-000017-4`).
4. **Demo control endpoints enabled** — `config_planbot.yaml` → `demo_tools.enabled: true`
   (see `docs/specification/demo/demo_tool_api.md`).  These provide the
   mutation + reset steps below over HTTP (no direct SQL).

---

## Demo 1 — The RM note shapes the recommendation

**Objective:** show the **LLM actually changes the recommended product** (and
its narrative justification) when the client's `qualitative_profile` (RM note)
is edited — proving the note drives the recommendation, not just cosmetics.

### 1.1 Baseline run

1. Call `POST /api/v1/product-opportunity-proposal-automatch` with the demo
   client and a product universe:

   ```json
   {
     "product_source": "default_yaml",
     "product_ids": ["bank_recommended"],
     "client_selection": { "client_id": ["<CLIENT_ID>"] },
     "run_matcher": true,
     "max_proposals": 1
   }
   ```

2. Note the `proposals[0].product_id` (the recommended product).

### 1.2 Mutate the RM note (demo-control endpoint)

Update the client's RM note to express a new preference (technology), then keep
everything else identical.

```text
PATCH /api/v1/demo/clients/<CLIENT_ID>
```

```json
{ "qualitative_profile": "<TECH-LEANING RM NOTE>" }
```

### 1.3 Re-run and compare

1. Repeat the **exact** request from 1.1.
2. Assert the recommendation **changed in narrative**: the recommended
   `product_id` is different, or the same product is now justified with a
   technology rationale.

> **This is the point of the demo.**  If the LLM does **not** change the
> recommendation after the RM-note edit, that is a signal to **retune** the
> prompt or the scorecard weights (specifically
> `product_fitness_weights.similarity_to_RM_note`) until the note carries enough
> weight.  The `similarity_to_RM_note` component (deterministic, visible in the
> matcher / fitness response) is the diagnostic to confirm *why* the LLM did or
> didn't move.

### 1.4 Reset (teardown)

```text
POST /api/v1/demo/reset
```

---

## Demo 2 — Structured products can be proposed

**Objective:** show the matcher proposing a structured product (FX TARF /
accumulator) to a client who can take the risk.

1. Call `POST /api/v1/product-opportunity-proposal-automatch` with the
   `structures` group (defined in `config/config_planbot.yaml` →
   `product_groups.structures`, **not** `config.yaml`):

   ```json
   {
     "product_source": "default_yaml",
     "product_ids": ["structures"],
     "client_selection": { "client_id": ["<CLIENT_ID>"] },
     "run_matcher": true,
     "max_proposals": 1
   }
   ```

2. Assert the proposal recommends a `structured_product` (e.g. an
   `FX-TARF-*` / `FX-ACC-*` id).

> **Tuned clients already exist.**  Three clients were prepared for exactly this
> in `docs/how_to/how_to_add_fx_tarf.md` (risk_rating `5`, RM note references FX
> TARF): `PB-HK-000002-6`, `PB-HK-000009-1`, `PB-HK-000017-4`.  Reuse one of
> these as `<CLIENT_ID>`.
>
> **Watch-outs.**
> - Structures carry `risk_rating = 5` and `expected_return = null`, so the
>   **risk hard filter** drops them for any client rated < 5 — hence the risk-5
>   tuned clients above.
> - `better_product_score` will be `0` for structures (no `expected_return`) —
>   expected, not a bug; the demo should note it.
> - Further client holdings/attribute tuning may still be needed so the
>   structures rank above the alternatives (see §Test data).

---

## Demo 3 — Reinvestment on maturity

**Objective:** show end-to-end discovery of a maturing position and a
replacement recommendation.

Use the **discovery** endpoint (it scans holdings for bonds maturing within a
window) — not the explicit-targets endpoint:

```
POST /api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings
```

```json
{
  "as_of_date": "2026-08-01",
  "within_days": 60,
  "max_clients": 1,
  "response_mode": "both"
}
```

1. Assert the response lists **≥1 client** with a maturing holding
   (`results_by_client`), plus a generated proposal (`proposal_markdown`)
   recommending a replacement product with a funding source.

> **Determinism.**  `as_of_date` is pinned to `2026-08-01` so `PROD053` (matures
> 2026-08-31) is reliably "30 days out" — the discovery result no longer drifts
> with the system date.  Asserting ≥1 client (not a specific one) sidesteps the
> endpoint's non-deterministic tie-break between holders.

## Test data

All three demos may require **test-data mutation** so each story is reproducible
and self-contained.  Mutation and reset are done **over HTTP** via the demo
control endpoints (see `docs/specification/demo/demo_tool_api.md`), never via
direct SQL:

- **Demo 1** — flip the client's `qualitative_profile` between an original and
  a technology-leaning note (`PATCH /api/v1/demo/clients/<id>`).
- **Demo 2** — ensure the chosen `risk_rating = 5` client's holdings/attributes
  make the FX TARF rank above the alternatives (tune as needed; baseline clients
  already exist in `docs/how_to/how_to_add_fx_tarf.md`).
- **Demo 3** — no injection needed; pin `as_of_date: "2026-08-01"` so the
  seeded maturing bond `PROD053` is discovered deterministically.

All mutations must be **reversible** via `POST /api/v1/demo/reset` (§Teardown).

---

## Teardown

A single `POST /api/v1/demo/reset` restores all mutated test data (the RM note
from Demo 1, any injected maturing bond from Demo 3) so the whole demo is
repeatable.

---

## Decisions (resolved)

1. **RM-note channel** — use the **persisted `qualitative_profile`** (not the
   runtime `rm_prompt`).
2. **Demo 1 assertion** — the **LLM's narrative product change** is the proof;
   retune the prompt / scorecard weights if the note doesn't move the
   recommendation.
3. **Client selection** — reuse existing seed clients; tune holdings/attributes
   as needed (see `docs/how_to/how_to_add_fx_tarf.md` for the 3 FX-TARF clients).
4. **Demo 2 client** — use a `risk_rating = 5` tuned client so structures aren't
   hard-filtered.
5. **Test data** — modify `test_data` for **all** demos, done **over HTTP** via
   the demo control endpoints (mutation + reset), not raw SQL.
6. **Demo tool** — `PATCH /api/v1/demo/clients/{id}` (mutate RM note) +
   `POST /api/v1/demo/reset` (restore baseline); see
   `docs/specification/demo/demo_tool_api.md`.

## Open questions for discussion

1. **Script vs Swagger.**  Should the deliverable be a single runnable script
   (bash/curl or Python) that posts to all three demos and asserts results, or
   Swagger-driven manual steps?