# Demo Test Data Baseline

> **Status**: SPECIFICATION (finalized — awaiting implementation authorization)
>
> Fixes the exact `client_id` / `product_id` and the data baseline the demo
> (and its pytest equivalent) run against, so the demos are deterministic and
> re-runnable.  Complements `demo_flow.md` (narrative) and `demo_tool_api.md`
> (HTTP mutation/reset surface).

## 1. Fixed IDs

| Demo | Client | Product(s) | Endpoint |
|---|---|---|---|
| 1 — RM note | `PB-HK-000001-8` (David Kim, risk 4) | `bank_recommended` group | `POST /api/v1/product-opportunity-proposal-automatch` |
| 2 — structured product | `PB-HK-000002-6` (Sarah Chen, risk 5) | `structures` group (6 × `FX-TARF-*`) | `POST /api/v1/product-opportunity-proposal-automatch` |
| 3 — reinvestment | discovered (see §4) | maturing bond `PROD053` / `PROD054` | `POST /api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings` |

These IDs are stable in the current DuckDB; see §5 for how they are locked into
a baseline and restored.

## 2. Demo 1 — RM note (`qualitative_profile`)

**Client:** `PB-HK-000001-8` (David Kim, risk 4, "Long-term capital growth").

### 2.1 Canonical baseline (what `reset` restores)

The current persisted value is the canonical baseline.  Capture it verbatim:

```
Experienced executive with strong income stream. Actively manages portfolio; prefers evidence-based decisions. Open to structured products and tactical equity plays. Has expressed concern about inflation eroding idle cash. Two children approaching university age — education funding is a near-term priority.
```

### 2.2 Mutation (what `PATCH /api/v1/demo/clients/PB-HK-000001-8` sets)

A technology-leaning rewrite of the same profile:

```
Experienced executive with strong income stream. Actively manages portfolio; prefers evidence-based decisions. Strongly favours the technology sector and is comfortable with high-concentration growth exposure. Two children approaching university age — education funding is a near-term priority.
```

The observable assertion (§`demo_flow.md` 1.3): the recommended `product_id`
changes to a technology fund (`PROD001` Tech Leaders Equity Fund, risk 4), or
the same product is re-justified with a technology rationale.

> **Note (accepted).**  David Kim's `like_products` is already
> `['technology', 'structured products', 'tactical equity']`, which favours tech
> via the separate `similarity_product_note_in_like_products` dimension in
> **both** runs.  This is **accepted for now** (David Kim is the chosen client).
>  If the RM-note flip is not clearly visible in the live run, neutralize
> `like_products` in the Demo 1 baseline as the retune step.

## 3. Demo 2 — structured product (FX TARF)

**Client:** `PB-HK-000002-6` (Sarah Chen, risk 5, "Regular income").
**Product group:** `structures` → the 6 seeded `FX-TARF-*` products
(`FX-TARF-USDHKD-6M-B`, `FX-TARF-USDHKD-1Y-B`, `FX-TARF-GBPUSD-4M-S`,
`FX-TARF-GBPUSD-6M-S`, `FX-TARF-AUDUSD-4M-S`, `FX-TARF-AUDUSD-6M-S`).

**No data change required** — the products and the client's RM note (already
references "USD/HKD settlement needs … open to an FX TARF") are seeded.  The
client's `risk_rating = 5` matches the structures' `risk_rating = 5`, so the
hard risk filter does not drop them.

The expected assertion: the top recommendation is a `structured_product`
(`FX-TARF-*`), most plausibly `FX-TARF-USDHKD-6M-B` (matches her USD/HKD note).

## 4. Demo 3 — reinvestment (maturing bond)

Two bonds carry an explicit maturity in the current data:

| `product_id` | name | maturity | holders (current) |
|---|---|---|---|
| `PROD053` | US Treasury 4.375% 31Aug26 | `2026-08-31` | `PB-HK-000007-5`, `PB-HK-000012-5`, `PB-HK-000018-2` |
| `PROD054` | US Treasury 3.75% 30Jun27 | `2027-06-30` | `PB-HK-000009-1`, `PB-HK-000021-6` |

### 4.0 Related clients — the `PROD053` holders

The demo exercises `PROD053` (the bond that matures within the pinned window).
Its three holders, in the order the discovery endpoint returns them:

| Order | `client_id` | Name | `PROD053` market value |
|---|---|---|---|
| 1 | `PB-HK-000007-5` | Akira Tanaka | `3,360,000` |
| 2 | `PB-HK-000012-5` | Harrison Holdings Ltd. | `1,750,000` |
| 3 | `PB-HK-000018-2` | Emily Zhang | `924,000` |

The discovery endpoint orders results by `(days_to_mature asc, market_value desc)`.
Since all three holders hold the **same** `PROD053` bond, their `days_to_mature`
is identical (`30` with the pinned `as_of_date`), so the tie-break is
`market_value desc` — i.e. the ordering above is **deterministic**, and with
`max_clients: 1` the returned client is always **`PB-HK-000007-5` (Akira Tanaka)**.

### 4.1 Determinism problem

The discovery endpoint defaults `as_of_date` to `date.today()`, and its maturity
window is `0 <= (maturity − as_of_date) <= within_days`.  Because the maturity
dates are **fixed in seed data** but `date.today()` moves, "maturing within N
days" is **not stable over time**:

- `PROD053` already matured relative to the session date (2026-09-08) → **not**
  discovered today.
- `PROD054` is ~295 days out → discovered today with `within_days: 365`, but
  will **drift out** of a 365-day window as real time passes.

### 4.2 Resolution — pin `as_of_date` (no data patch needed)

The reinvestment endpoints accept `as_of_date`.  Pin it in the Demo 3 test so
the demo is deterministic regardless of when it runs:

```json
{
  "as_of_date": "2026-08-01",
  "within_days": 60,
  "max_clients": 1,
  "response_mode": "both"
}
```

With `as_of_date = 2026-08-01` and `within_days = 60`, `PROD053` (matures
2026-08-31) is **30 days out** → reliably discovered.  This requires **no data
change**.  The test asserts **≥1 client** with a maturing holding; with
`max_clients: 1` the returned client is deterministically
**`PB-HK-000007-5` (Akira Tanaka)** — see §4.0.

> **Alternative (if a "live" date is preferred):** add a dedicated demo bond
> whose `type_specific.maturity` is always `CURRENT_DATE + 30 days` (a rolling
> fixture).  This needs a *long-term* seeder change and is deferred — see §7.

## 5. Baseline lock-in and reset

`reset` (`POST /api/v1/demo/reset`) restores the canonical values in §2.1 (and,
once Demos 2/3 need mutation, their baselines too).  The canonical baseline is a
small static map of `(table, key, column) → original value`:

```text
clients.qualitative_profile[PB-HK-000001-8] = "<§2.1 value>"
```

No rows are added or deleted by the demo baseline itself; the FX-TARF products
and their tuned clients are already seeded (see
`docs/how_to/how_to_add_fx_tarf.md`).

## 6. Acceptance criteria

1. `PB-HK-000001-8` exists with risk 4 and the §2.1 canonical note.
2. `PB-HK-000002-6` exists with risk 5 and a USD/HKD FX-TARF RM note.
3. `bank_recommended` and `structures` product groups resolve to the seeded IDs
   in §1 (no missing `product_id`s).
4. The 6 `FX-TARF-*` products are present with `product_type=structured_product`.
5. `PROD053` / `PROD054` are present with the maturities in §4.
6. `POST /api/v1/demo/reset` restores `qualitative_profile` for `PB-HK-000001-8`
   to the §2.1 value.
7. Demo 3 runs deterministically using a pinned `as_of_date` (§4.2).

## 7. Decisions (resolved)

1. **Demo 1 client** — `PB-HK-000001-8` (David Kim), keeping his existing
   `like_products` (accepted pre-existing tech bias).
2. **Demo 3 determinism** — pin `as_of_date: "2026-08-01"` (no rolling fixture).
3. **Demo 3 assertion** — assert **≥1 client** with a maturing holding, not a
   specific client.
