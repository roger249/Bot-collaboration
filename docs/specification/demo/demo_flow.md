# Proposal Server — Demo Flow

> **Status**: Draft — flow only.  Concrete client/product IDs, test-data
> mutations, and a runnable demo script are filled in during the next phase.

This document defines the end-to-end demo of the proposal server.  It walks
through three scenarios, each demonstrating a distinct capability of the
product–client matcher and the proposal pipeline.

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

### 1.2 Mutate the RM note (test-data step)

Update the client's RM note to express a new preference (technology), then keep
everything else identical.

```sql
-- ⚠ test-data mutation — finalized during the "details" phase
UPDATE clients
   SET qualitative_profile = '<TECH-LEANING RM NOTE>'
 WHERE client_id = '<CLIENT_ID>';
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

```sql
UPDATE clients
   SET qualitative_profile = '<ORIGINAL RM NOTE>'
 WHERE client_id = '<CLIENT_ID>';
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
  "within_days": 365,
  "max_clients": 1,
  "response_mode": "both"
}
```

1. Assert the response lists ≥1 client with a maturing holding
   (`results_by_client`), plus a generated proposal (`proposal_markdown`)
   recommending a replacement product with a funding source.

> **Watch-out.**  The discovery endpoint only finds clients who hold a **bond /
> bond_fund maturing within `within_days`**.  If the seed data has no such
> client, this demo needs a test-data fixture (a bond maturing soon) — a detail
> for the next phase.

## Test data

All three demos may require **test-data mutation** so each story is reproducible
and self-contained:

- **Demo 1** — flip the client's `qualitative_profile` between an original and
  a technology-leaning note (already scripted as a before/after `UPDATE`).
- **Demo 2** — ensure the chosen `risk_rating = 5` client's holdings/attributes
  make the FX TARF rank above the alternatives (tune as needed; baseline clients
  already exist in `docs/how_to/how_to_add_fx_tarf.md`).
- **Demo 3** — add a bond/bond_fund holding that matures within the discovery
  window, if none already does.

All mutations must be **reversible** (see §Teardown).

---

## Teardown

A single **reset** should restore all mutated test data (the RM note from
Demo 1, any injected maturing bond from Demo 3) so the whole demo is repeatable.
Ideally this is a small script (`<demo-reset>`), not hand-edited SQL.

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
5. **Test data** — modify `test_data` for **all** demos (RM note, structured
   product suitability, a maturing bond for Demo 3).

## Open questions for discussion

1. **Script vs Swagger.**  Should the deliverable be a single runnable script
   (bash/curl or Python) that posts to all three demos and asserts results, or
   Swagger-driven manual steps?