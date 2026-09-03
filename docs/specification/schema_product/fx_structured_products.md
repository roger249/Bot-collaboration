# FX Structured Products — Product Catalog Mapping Spec

> Status: **Draft** (all open decisions resolved; see §8)
> Scope: Map two FX structured products — **FX Accumulator** and **FX TARF** — into the existing single-table product catalog.

## 1. Source files

| File | Product | Content state |
| --- | --- | --- |
| [`docs/test data/fx_accumulator.md`](../../test data/fx_accumulator.md) | FX Accumulator | Populated — 4 currency directions × 3M/6M tenors (8 concrete variants) |
| [`docs/test data/fx_tarf.md`](../../test data/fx_tarf.md) | FX TARF (Target Redemption Forward) | Populated — 3 currency pairs (USD/HKD, GBP/USD, AUD/USD) × mixed tenors/directions (6 concrete variants) |

> **Scope rule:** this spec is limited strictly to the **14 trades present in the
> two sample files** (8 Accumulator + 6 TARF). No additional variants are
> introduced beyond those, and every row in §4 maps one-to-one to a table in
> `fx_accumulator.md` or `fx_tarf.md`.

> **Naming note:** the source file names the product **Target Redemption Forward
> (TRF)**. **Agreed:** `sub_type` = `FX TARF` is the canonical internal label;
> `TARF` (Target Accrual Redemption Forward) and `TRF` refer to the same
> structure.

## 2. Current schema recap (two-part split)

The `products` table (`data/planbot/db/planbot.duckdb`) already implements the two-part split:

1. **Common fields** — fixed columns on every row:
   `product_id`, `isin`, `name`, `ticker`, `trading_currency`, `risk_rating`,
   `expected_return`, `region`, `country`, `sector`, `remarks`, `product_type`,
   `vehicle`, plus the `investment_note` text column.
2. **Product-specific JSON** — the `type_specific` TEXT column holding a JSON
   object whose keys vary by `product_type`. A second JSON column,
   `performance_history`, holds period→metric maps.

Adding a new `product_type` does **not** require any DDL change — only a new
`_synthesize_*()` function, a classification rule, and an insert block in the
seeder (`src/test_data/product_catalog_seed.py`).

## 3. Classification decision

| Question | Decision | Rationale |
| --- | --- | --- |
| Which `product_type`? | `structured_product` | `structured_product.sub_type` already enumerates **"FX Accumulator"**. The `fx` type is reserved for *plain* spot/forward currency rows (deferred CURRENCY rows in the CSV) and is marked "reserved for the future" in `product_catalog_schema.md`. Both target products are barrier/gearing structures, not plain FX. |
| `sub_type` value | `FX Accumulator`, `FX TARF` | Distinguishes the two structures for query/LLM consumption. |
| `vehicle` | `Structure` | Matches the schema doc (`Direct, ETF, Mutual Fund, Structure`). |
| `sector` | `FX` | Consistent with existing `sector: "FX"` usage in `config_marketdata.yaml`. |
| `performance_history` | `{}` | OTC structures have no historical return/risk series. |
| `expected_return` | `null` | Derivative structures have no projected yield baseline. |

### 3.1 `product_family` and underlying differentiation (agreed)

- **`product_family` = `structured_product`.** `get_product_family()` in
  `src/shared/product_family.py` has no entry for `structured_product`, so it
  falls through to the type string (`"structured_product"`). **Agreed:** keep
  this behaviour — `structured_product` is the family name. No code change.
- **`structured_product` covers both packaging forms** via `sub_type`: the FX
  form (`FX Accumulator`, `FX TARF`) and the note form (`structured_note`,
  `CMT RA`, `FCN`, autocallable). The single `product_type` + `sub_type`
  discriminator is sufficient; no second `product_type` is introduced.
- **Underlying differentiation stays out of `product_family`.** When we later
  need to tell FX vs rate vs equity structures apart, filter/score on the
  existing `type_specific.underlying_asset_type` field (`fx`, `interest_rate`,
  `equity`, `index`, `commodity`, `basket`) — not on family. `product_family`
  is a structural (packaging) axis; `underlying_asset_type` is a risk-driver
  axis. Merging them would explode the family vocabulary and lose the
  "has done structured products before" experience signal.

### 3.2 Concentration-class precision (future enhancement)

For now, `structured_product` is treated as its own concentration/asset class
(the `_derive_asset_class` fall-through), separate from holdings' `Cash/Equities/
Fixed Income/Alternatives`. This is a coarse approximation: two structures with
very different risk drivers (e.g. an FX TARF vs. a rate range-accrual note)
would be bucketed together for concentration scoring.

**Future enhancement:** add a `risk_factor` (a concentration/risk-driver key)
to the product so concentration scoring can group by the actual underlying risk
driver — e.g. `fx`, `interest_rate`, `equity`, `index`, `commodity` — rather
than by wrapper type. This is not implemented now; `structured_product` remains
a single separate concentration class until then.

## 4. Product granularity (one row per variant)

The accumulator source describes 8 distinct instruments (currency direction ×
tenor); the TARF source describes 6 (currency pair × tenor). The catalog
convention is **one row per instrument** — each variant is a single row, exactly
as with all other existing products — with flat JSON scalars in `type_specific`
(no nested `terms[]` array). This is the agreed design.

| # | Currency pair | Direction | Tenor | Provider | Proposed `product_id` |
| --- | --- | --- | --- | --- | --- |
| 1 | USD/HKD | Buy USD / Sell HKD | 3M | UBS | `FX-ACC-USDHKD-3M-B` |
| 2 | USD/HKD | Buy USD / Sell HKD | 6M | HSBC | `FX-ACC-USDHKD-6M-B` |
| 3 | EUR/USD | Buy EUR / Sell USD | 3M | BNP Paribas | `FX-ACC-EURUSD-3M-B` |
| 4 | EUR/USD | Buy EUR / Sell USD | 6M | JPMorgan | `FX-ACC-EURUSD-6M-B` |
| 5 | USD/JPY | Buy USD / Sell JPY | 3M | UBS | `FX-ACC-USDJPY-3M-B` |
| 6 | USD/JPY | Buy USD / Sell JPY | 6M | HSBC | `FX-ACC-USDJPY-6M-B` |
| 7 | USD/JPY | Buy JPY / Sell USD | 3M | BNP Paribas | `FX-ACC-USDJPY-3M-S` |
| 8 | USD/JPY | Buy JPY / Sell USD | 6M | JPMorgan | `FX-ACC-USDJPY-6M-S` |

> Source: [`docs/test data/fx_accumulator.md`](../../test data/fx_accumulator.md) —
> §1 USD/HKD Accumulators, §2 EUR/USD Accumulators, §1 USD/JPY Accumulators,
> §2 JPY/USD Accumulators.

The TARF source describes 6 distinct instruments across two profiles:

- **Buy base / Sell quote** (USD/HKD) — 2 instruments, 6M/1Y tenors, daily
  fixings, strike *below* spot (a discount).
- **Sell base / Buy quote** (GBP/USD, AUD/USD) — 4 instruments, 4M/6M tenors,
  monthly fixings, *enhanced* strike *above* spot.

| # | Currency pair | Direction | Tenor | Provider | Proposed `product_id` |
| --- | --- | --- | --- | --- | --- |
| 9 | USD/HKD | Buy USD / Sell HKD | 6M | UBS | `FX-TARF-USDHKD-6M-B` |
| 10 | USD/HKD | Buy USD / Sell HKD | 1Y | HSBC | `FX-TARF-USDHKD-1Y-B` |
| 11 | GBP/USD | Sell GBP / Buy USD | 4M | BNP Paribas | `FX-TARF-GBPUSD-4M-S` |
| 12 | GBP/USD | Sell GBP / Buy USD | 6M | JPMorgan | `FX-TARF-GBPUSD-6M-S` |
| 13 | AUD/USD | Sell AUD / Buy USD | 4M | UBS | `FX-TARF-AUDUSD-4M-S` |
| 14 | AUD/USD | Sell AUD / Buy USD | 6M | HSBC | `FX-TARF-AUDUSD-6M-S` |

> Source: [`docs/test data/fx_tarf.md`](../../test data/fx_tarf.md) — §1 USD/HKD
> Target Redemption Forwards, §2 GBP/USD TARF, §3 AUD/USD TARF.

## 5. Common-field mapping

| Common field | Value / rule | Notes |
| --- | --- | --- |
| `product_id` | `FX-ACC-{PAIR}-{TENOR}-{B\|S}` / `FX-TARF-{PAIR}-{TENOR}-{B\|S}` | `B` = buy base, `S` = sell base. |
| `isin` | `null` | OTC, no ISIN. |
| `name` | e.g. `"3-Month USD/HKD FX Accumulator (Buying USD)"` | Human/LLM-readable. |
| `ticker` | `null` | OTC. |
| `trading_currency` | base currency (USD / EUR / JPY / GBP / AUD) | Settlement currency of the accumulated notional. |
| `risk_rating` | `5` | Leveraged, capital-at-risk, KO/gearing exposure (agreed). |
| `expected_return` | `null` | No reliable proxy — derivative structure with no historical return series (agreed). |
| `region` | `null` | Not geography-specific. |
| `country` | `null` | — |
| `sector` | `FX` | — |
| `remarks` | One-line structure behaviour summary | e.g. "Buy USD/HKD at 0.13% strike discount; 2× gearing below strike; daily KO at 7.8490." |
| `product_type` | `structured_product` | — |
| `vehicle` | `Structure` | — |
| `investment_note` | House-view narrative | Generated via `_generate_investment_note()` (extend with an FX-structured branch). |
| `type_specific` | JSON per §6 | — |
| `performance_history` | `{}` | — |

## 6. `type_specific` JSON mapping

### 6.1 Proposed key set for FX structured products

Reuse the existing `structured_product` keys where possible, and add a small
set of FX-specific keys. Proposed full key set (documented in
`bank_data_contract.md` §3.3.1 as indicative, not closed):

**Reused from `structured_product`:** `sub_type`, `provider`,
`principal_protection`, `capital_at_risk`, `underlying_asset_type`,
`underlying_assets`, `strike_level`, `knock_out_level`, `knock_in_level`,
`barrier_type`, `early_redemption`, `payout_structure`, `maturity`.

**FX-specific additions:** `currency_pair`, `base_currency`, `quote_currency`,
`direction`, `spot_reference`, `gearing`, `guaranteed_period`,
`fixing_frequency`, `notional_per_fixing`, `notional_currency`, `tenor`.

- `direction` ∈ `buy_base` | `sell_base` (TARF has both profiles; the
  Accumulator is buy-base only).
- `fixing_frequency` ∈ `daily` (Accumulator + USD/HKD TARF) | `monthly`
  (GBP/USD and AUD/USD TARF — 4/6 monthly fixings).
- `strike_level` is *below* spot for buy-base profiles (a discount) and *above*
  spot for sell-base profiles (an enhanced strike).

> **Key shape (agreed):** FX keys are **flattened** into `type_specific` at the
> top level (no nested `fx` sub-object), consistent with the existing flat
> `structured_product` keys and the seeder's `_synthesize_*()` convention.

> **`provider` domain (agreed):** one of four common counterparties — `UBS`,
> `HSBC`, `BNP Paribas`, `JPMorgan` — assigned round-robin across the 14 rows
> (§4). Replaces the earlier `"Bank Internal"` placeholder.

> The existing `structured_product` key set (coupon_*, autocallable,
> participation_rate, basket_type) is oriented to notes/autocallables and is
> mostly `null` for these two products; it is carried as `null` where not
> applicable.

### 6.2 FX Accumulator mapping (example: 3M USD/HKD, variant #1)

```json
{
  "sub_type": "FX Accumulator",
  "provider": "UBS",
  "underlying_asset_type": "fx",
  "underlying_assets": ["USD/HKD"],
  "currency_pair": "USD/HKD",
  "base_currency": "USD",
  "quote_currency": "HKD",
  "direction": "buy_base",
  "spot_reference": 7.842,
  "strike_level": 7.832,
  "knock_out_level": 7.849,
  "barrier_type": "daily",
  "gearing": 2.0,
  "guaranteed_period": "First 1 month (20 fixings)",
  "fixing_frequency": "daily",
  "notional_per_fixing": 50000,
  "notional_currency": "USD",
  "tenor": "3m",
  "principal_protection": "none",
  "capital_at_risk": 1.0,
  "early_redemption": true,
  "payout_structure": "Buy base currency at strike discount while spot below KO; 2x notional when spot below strike.",
  "maturity": null
}
```

Field-to-source map (per variant):

| `type_specific` key | Source in `fx_accumulator.md` |
| --- | --- |
| `currency_pair` / `base_currency` / `quote_currency` | Currency pair column / direction heading |
| `spot_reference` | **Spot Reference** |
| `strike_level` | **Strike Rate (Discount)** (absolute rate; discount % → `remarks`) |
| `knock_out_level` | **Knock-Out (KO) Level** |
| `gearing` | **Gearing / Leverage** (`2×` → `2.0`) |
| `guaranteed_period` | **Guaranteed Period** |
| `fixing_frequency` | **Fixing Frequency** |
| `notional_per_fixing` / `notional_currency` | **Notional per Day** |
| `tenor` | 3-Month / 6-Month heading |
| `direction` | Section title (Buying USD vs. Buying JPY) |

### 6.3 FX TARF mapping (example: 4M GBP/USD TRF, variant #11)

TARF reuses the accumulator key set but **differs in two ways**: (1) it has
**no spot-level KO barrier** — termination is driven by an accumulated target
profit, so `knock_out_level` and `knock_in_level` are `null`; and (2) it adds a
`target_redemption_cap` group describing the redemption target.

The source contains two TARF profiles that map onto the same key set with
different values:

| Profile | Pairs | `direction` | Strike vs. spot | `fixing_frequency` | Tenor |
| --- | --- | --- | --- | --- | --- |
| Buy base | USD/HKD | `buy_base` | discount (below) | `daily` | 6M / 1Y |
| Sell base | GBP/USD, AUD/USD | `sell_base` | enhanced (above) | `monthly` | 4M / 6M |

```json
{
  "sub_type": "FX TARF",
  "provider": "BNP Paribas",
  "underlying_asset_type": "fx",
  "underlying_assets": ["GBP/USD"],
  "currency_pair": "GBP/USD",
  "base_currency": "GBP",
  "quote_currency": "USD",
  "direction": "sell_base",
  "spot_reference": 1.3590,
  "strike_level": 1.359,
  "knock_out_level": null,
  "knock_in_level": null,
  "barrier_type": null,
  "gearing": 2.0,
  "guaranteed_period": "First 1 month (1 fixing)",
  "fixing_frequency": "monthly",
  "notional_per_fixing": 1000000,
  "notional_currency": "GBP",
  "tenor": "4m",
  "target_redemption_cap": 250,
  "target_redemption_cap_unit": "pips",
  "target_redemption_cap_currency": null,
  "target_redemption_cap_note": "250 pips (USD 25,000 total gain)",
  "principal_protection": "none",
  "capital_at_risk": 1.0,
  "early_redemption": true,
  "payout_structure": "Sell base currency at enhanced strike; auto-terminate once target profit is accrued; 2x notional when spot rises above strike.",
  "maturity": null
}
```

The buy-base profile differs in three fields: `direction`, `strike_level`
(discount, below spot), and `fixing_frequency` (`daily`), and its
`target_redemption_cap` is a **currency amount** rather than pips. Example
(6M USD/HKD, variant #9):

```json
{
  "sub_type": "FX TARF",
  "provider": "UBS",
  "underlying_asset_type": "fx",
  "underlying_assets": ["USD/HKD"],
  "currency_pair": "USD/HKD",
  "base_currency": "USD",
  "quote_currency": "HKD",
  "direction": "buy_base",
  "spot_reference": 7.842,
  "strike_level": 7.834,
  "knock_out_level": null,
  "knock_in_level": null,
  "barrier_type": null,
  "gearing": 2.0,
  "guaranteed_period": "First 1 month (20 fixings)",
  "fixing_frequency": "daily",
  "notional_per_fixing": 100000,
  "notional_currency": "USD",
  "tenor": "6m",
  "target_redemption_cap": 150000,
  "target_redemption_cap_unit": "currency_amount",
  "target_redemption_cap_currency": "HKD",
  "target_redemption_cap_note": "HKD 150,000 (~1.0% total return cap)",
  "principal_protection": "none",
  "capital_at_risk": 1.0,
  "early_redemption": true,
  "payout_structure": "Buy base currency at strike discount; auto-terminate once target profit is accrued; 2x notional when spot falls below strike.",
  "maturity": null
}
```

TARF-specific additions (not used by Accumulator):

| `type_specific` key | Type | Meaning |
| --- | --- | --- |
| `target_redemption_cap` | number | Raw redemption-target value (e.g. `150000`, `250`). |
| `target_redemption_cap_unit` | string | `currency_amount` \| `pips` — how the cap is expressed. |
| `target_redemption_cap_currency` | string\|null | ISO code when `unit = currency_amount` (HKD); else `null`. |
| `target_redemption_cap_note` | string | Free-text with the relative framing (e.g. `~1.0% total return cap`). |

> The target cap is expressed two ways in the source: as an absolute
> **currency amount** (USD/HKD → HKD) or as **pips** (GBP/USD, AUD/USD). The
> parenthetical phrases like "USD 25,000 total gain" are framing notes, not a
> distinct unit. The `*_unit`/`*_currency`/`*_note` fields normalise this
> without losing the original framing. **Agreed:** keep these unit-specific
> fields as the source of truth; no additional `target_redemption_cap_pct` field
> is added.

Field-to-source map (per TARF variant):

| `type_specific` key | Source in `fx_tarf.md` |
| --- | --- |
| `currency_pair` / `base_currency` / `quote_currency` | Currency pair column / profile heading |
| `spot_reference` | **Spot Reference** (buy-base) / **Current Spot Reference** (sell-base) |
| `strike_level` | **Strike Rate (Discount)** (buy-base) / **Enhanced Strike ($K$)** (sell-base, above spot) |
| `target_redemption_cap*` | **Target Redemption Cap** (buy-base) / **Knock-Out Target ($T$)** (sell-base) |
| `gearing` | **Gearing / Leverage** (`2×` → `2.0`) |
| `guaranteed_period` | **Guaranteed Period** |
| `fixing_frequency` | **Fixing Frequency** (`daily` vs `monthly`) |
| `notional_per_fixing` / `notional_currency` | **Daily Base Notional** (buy-base) / **Notional per Fixing** (sell-base) |
| `tenor` | 6-Month / 1-Year heading (buy-base) or 4-Month / 6-Month heading (sell-base) |
| `direction` | Profile heading — "Buying … / Selling …" → `buy_base`; "Selling … / Buying …" → `sell_base` |

## 7. Implementation changes required (three-layer sync)

1. **DuckDB schema** — *no change*. `type_specific` is already JSON; `structured_product` requires no new columns.
2. **Test data / seeder** (`src/test_data/product_catalog_seed.py`):
   - Add `_synthesize_fx_tarf(variant) -> dict` now (Accumulator `_synthesize_fx_accumulator` later).
   - **Phase 1 (now): seed only the 6 FX TARF variants** (rows 9–14) from `fx_tarf.md`.
   - **Incremental / localized**: use `INSERT OR REPLACE` targeting only the `FX-TARF-*` `product_id`s. Do **not** run the existing `seed()` flow's `DELETE FROM products`; all other rows in the DuckDB must remain intact (they contain manual patches).
   - Add a standalone insert path (separate from the destructive `seed()` main flow) using the shared `DDL_COLUMNS` / `_otc_to_general()` pattern.
   - No snapshot/restore is required for an insert-only operation, but re-running the destructive `seed()` is still forbidden until the other product types are migrated to the same incremental path.
3. **API contract docs**:
   - `docs/specification/data_api/bank_data_contract.md` §3.3.1 — add a `structured_product` row documenting its `type_specific` keys; §4 — add `structured_product` (and `Structure` under `vehicle`).
   - `docs/specification/schema_product/product_catalog_schema.md` — add FX-specific keys to the `structured_product` block.
   - `openapi_data.json` — `product_type` is a free string (not a closed enum), so **no regeneration** is strictly required; regenerate only if the description is updated.

## 8. Resolved decisions (review 2026-09-03)

| # | Decision |
| --- | --- |
| 1 | `risk_rating` = `5` for all FX structured products (leveraged, capital-at-risk, KO/gearing exposure). |
| 2 | `expected_return` = `null` — no reliable proxy exists for these derivative structures. |
| 3 | Concentration-class precision is deferred: `structured_product` is treated as a single separate concentration class for now; a future `risk_factor` field will let concentration scoring group by the actual risk driver (see §3.2). |
| 4 | Seeding is **incremental / localized to FX TARF** first: `INSERT OR REPLACE` only the `FX-TARF-*` rows; never `DELETE FROM products`. Other DuckDB rows stay intact (manual patches preserved). |
