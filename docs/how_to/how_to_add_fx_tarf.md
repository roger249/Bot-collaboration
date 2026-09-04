# How to add FX TARF to the data

This document describes every change applied to `data/planbot/db/planbot.duckdb`
so an external system (read by an LLM) can reproduce the same state by referring
to this DuckDB as the source of truth.

Scope of changes below:

1. **6 new `products` rows** — FX TARF structured products.
2. **3 `clients.qualitative_profile` updates** — RM notes edited so FX TARF can
   be recommended to those clients.

No rows were deleted. No schema (`CREATE TABLE` / `ALTER TABLE`) changes were
made.

---

## 1. New products: FX TARF (6 rows)

`product_type = 'structured_product'`, `sub_type = 'FX TARF'`. Inserted via
`INSERT OR REPLACE` keyed on `product_id` (incremental — no `DELETE FROM products`).

Common columns for all six rows:

| Column | Value |
| --- | --- |
| `isin` | `NULL` |
| `ticker` | `NULL` |
| `risk_rating` | `5` |
| `expected_return` | `NULL` |
| `region` | `NULL` |
| `country` | `NULL` |
| `sector` | `'FX'` |
| `product_type` | `'structured_product'` |
| `vehicle` | `'Structure'` |
| `performance_history` | `'{}'` |
| `type_specific` | JSON (one example below; read the rest from DuckDB) |
| `investment_note` | house-view narrative (one example below; read the rest from DuckDB) |

Per-row details:

| # | `product_id` | `name` | `trading_currency` | Direction | Strike vs spot | Fixing freq | Tenor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `FX-TARF-USDHKD-6M-B` | `6-Month USD/HKD Target Redemption Forward (Buying USD)` | USD | buy_base | discount (below) | daily | 6m |
| 2 | `FX-TARF-USDHKD-1Y-B` | `1-Year USD/HKD Target Redemption Forward (Buying USD)` | USD | buy_base | discount (below) | daily | 1y |
| 3 | `FX-TARF-GBPUSD-4M-S` | `4-Month GBP/USD Target Redemption Forward (Selling GBP)` | GBP | sell_base | enhanced (above) | monthly | 4m |
| 4 | `FX-TARF-GBPUSD-6M-S` | `6-Month GBP/USD Target Redemption Forward (Selling GBP)` | GBP | sell_base | enhanced (above) | monthly | 6m |
| 5 | `FX-TARF-AUDUSD-4M-S` | `4-Month AUD/USD Target Redemption Forward (Selling AUD)` | AUD | sell_base | enhanced (above) | monthly | 4m |
| 6 | `FX-TARF-AUDUSD-6M-S` | `6-Month AUD/USD Target Redemption Forward (Selling AUD)` | AUD | sell_base | enhanced (above) | monthly | 6m |

### Per-row `type_specific` JSON

> The `type_specific` column is a JSON string. Keys are identical across rows;
> only values differ. The full JSON for all six rows lives in the DuckDB itself,
> so only one representative row is shown here to avoid duplication.

**Example — `FX-TARF-USDHKD-6M-B`**

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

`investment_note`: `USD/HKD TARF (buy) gives investors who need USD over time the chance to accumulate USD daily at a strike lower than spot; it knocks out once the target profit is reached, but 2x notional applies if spot falls below the strike.`

For the remaining five rows, read `type_specific` and `investment_note` directly
from the DuckDB (they differ only in provider, currency pair, strike, fixing
frequency, guaranteed period, and target redemption cap):

```sql
SELECT product_id, type_specific, investment_note
FROM products
WHERE product_id LIKE 'FX-TARF-%';
```

---

## 2. Client RM notes: `clients.qualitative_profile` (3 rows updated)

Appended FX-TARF-appropriate guidance to the existing `qualitative_profile`
value (existing text is preserved; only the trailing sentences are new).

### `PB-HK-000002-6` (Sarah Chen, risk_rating 5)

New value:

```
High-earning legal professional with high risk appetite. Comfortable with concentrated equity positions and alternative investments. Frequently travels to China for business — receptive to APAC equity themes. Recently expressed interest in ESG and sustainable investing trends. No immediate liquidity needs. Has recurring USD/HKD settlement needs and is open to an FX TARF that accumulates USD against HKD at a strike below spot, provided the 2x gearing risk is clearly explained.
```

### `PB-HK-000009-1` (Sophia Rossi, risk_rating 5)

New value:

```
High-income surgeon with aggressive risk appetite. Young enough for a long investment horizon. Interested in healthcare and biotech sector plays. Comfortable with high equity allocation and alternatives. No dependents — flexible on liquidity and time horizon. As a Europe-based high earner holding GBP, she is open to selling GBP at an enhanced strike via an FX TARF to build USD exposure while rates remain favourable.
```

### `PB-HK-000017-4` (Catherine Li, risk_rating 5)

New value:

```
High-income CFO with aggressive risk appetite. Active in portfolio decisions; enjoys discussing macro themes and sector rotation. Interested in tech, AI, and emerging-market growth stories. Comfortable with currency exposure. Has enquired about private equity fund access. As a CFO with regular USD-denominated obligations, she is open to FX structured products (accumulating USD against HKD at a discount, or selling GBP/AUD at an enhanced strike) to reduce her effective USD funding cost.
```

---

## 3. How to reproduce

The exact values above are the source of truth. An external system may:

- **Products** — `INSERT OR REPLACE INTO products` the 6 rows above (all 16
  columns in `DDL_COLUMNS` order: `product_id, isin, name, ticker,
  trading_currency, risk_rating, expected_return, region, country, sector,
  remarks, product_type, vehicle, type_specific, performance_history,
  investment_note`). `remarks` is a short human summary (e.g. for row 1:
  `Buy USD/HKD at 0.10% strike discount; 2x gearing below strike; target HKD 150,000.`).
- **Clients** — `UPDATE clients SET qualitative_profile = '<value>' WHERE client_id = '<id>'` for the three clients above.

> For the full canonical seed, see `src/test_data/product_catalog_seed.py`
> (`seed_fx_tarf()` and `_FX_TARF_VARIANTS`), and the live DuckDB itself
> (`SELECT * FROM products WHERE product_type = 'structured_product'`).
