# Product Catalog — DuckDB Seed Utility

> **Location:** `src/test_data/`  
> **Output:** `data/planbot/db/planbot.duckdb`
> **Last updated:** 2026-07-10

---

## Overview

Seeds a DuckDB product catalog from three data sources:

| Source | Products |
|---|---|
| `data/planbot/shared/product_catalog/selected_etf.csv` | 95 tickers with market data (funds, stocks, currencies, crypto) |
| Yahoo Finance (`yfinance`) | Provider, NAV, AUM, strategy summary, market cap, exchange, ISIN enrichment |
| `data/planbot/shared/product_catalog/otc_products.md` | 27 OTC products (15 funds + 12 individual bonds) |

## Database Schema

Single-file DuckDB at `data/planbot/db/planbot.duckdb`. **Single-table design with two JSON columns:**

```sql
CREATE TABLE products (
    product_id          TEXT PRIMARY KEY,
    isin                TEXT,
    name                TEXT NOT NULL,
    ticker              TEXT,
    trading_currency    TEXT,
    risk_rating         INTEGER NOT NULL CHECK (risk_rating BETWEEN 1 AND 5),
    expected_return     DOUBLE,
    region              TEXT,
    country             TEXT,
    sector              TEXT,
    remarks             TEXT,
    product_type        TEXT NOT NULL,
    vehicle             TEXT,
    type_specific       TEXT,           -- JSON: type-specific fields
    performance_history TEXT            -- JSON: per-period return/risk metrics
);
```

Schema source of truth: `docs/prompts/prod_spec/product_catalog/product_catalog.md`

## Contents

| product_type | Count | Source | Examples |
|---|---|---|---|
| `stock` | 39 | CSV | NVDA, AAPL, TSLA, 0700.HK, TSM, 9988.HK… |
| `equity_fund` | 35 | CSV (23) + OTC (12) | XLK, VOO, QQQ, PROD001, PROD013–019, PROD021–025… |
| `bond_fund` | 30 | CSV | HYG, BND, AGG, SGOV, TLT, LQD, EMB… |
| `bond` | 12 | OTC | PROD003, PROD007, PROD011, PROD044–PROD052 |
| `money_market_fund` | 3 | CSV | VMRXX, FZDXX, SPAXX |
| `balanced_fund` | 3 | OTC | PROD008, PROD020, PROD024 |
| **Total** | **122** | | |

## JSON Column Shapes

### `type_specific` by product_type

| product_type | Key fields |
|---|---|
| `money_market_fund` | `nav`, `yield_type`, `credit_quality`, `maturity_profile`, `dividend_treatment` |
| `bond_fund` | `provider`, `nav`, `expense_ratio`, `strategy_summary`, `aum`, `ytm`, `domicile`, `effective_duration`, … |
| `equity_fund` | `provider`, `nav`, `strategy_summary`, `ter`, `domicile`, `aum`, `dividend_treatment`, `dividend_frequency` |
| `stock` | `company_name`, `exchange`, `lot_size`, `market_cap`, `dividend_paying`, `dividend_yield` |
| `balanced_fund` | `provider`, `strategy_summary`, `equity_exposure`, `fixed_income_exposure`, `cash_exposure`, `risk_profile`, `investment_style` |
| `bond` | `issuer_name`, `issuer_sector`, `coupon_type`, `coupon_rate`, `credit_rating`, `maturity`, `convertible`, `green_bond` |

### `performance_history`

```json
{
  "6m":  {"return": 28.97, "cagr": 66.32, "max_drawdown": -11.20, "calmar_ratio": 5.92, "downside_risk": 10.93, "volatility": 23.84},
  "1y":  {"return": 55.42, …},
  "3y":  {…},
  "5y":  {…},
  "10y": {…}
}
```

Populated for CSV-derived products only (95 of 122). OTC products have `{}`.

## Quick Start

### Re-seed from scratch

```bash
rm data/planbot/db/planbot.duckdb
.venv/bin/python -m src.test_data.product_catalog_seed
```

### Query

```python
from src.test_data.product_catalog import get_conn, get_product, search_aligned_products_json

conn = get_conn(read_only=True)

# Single product with parsed JSON columns
prod = get_product(conn, "ETF-HYG")
print(prod["type_specific"]["provider"])           # "iShares"
print(prod["type_specific"]["aum"])                 # 17626118144.0
print(prod["performance_history"]["3y"]["cagr"])    # 8.42

# Filtered, grouped result for LLM consumption
json_str = search_aligned_products_json(
    conn, product_type="bond_fund", max_risk_rating=3, target_currency="USD"
)

# Summary counts
from src.test_data.product_catalog import get_summary
print(get_summary(conn))  # {'stock': 39, 'equity_fund': 35, …}
```

### Raw SQL with JSON extraction

```sql
-- Top 5 bond funds by 3y CAGR
SELECT name, json_extract(performance_history, '$.3y.cagr')::DOUBLE AS cagr_3y
FROM products WHERE product_type = 'bond_fund'
ORDER BY cagr_3y DESC LIMIT 5;

-- Average AUM by product type
SELECT product_type,
       AVG(json_extract(type_specific, '$.aum')::DOUBLE) AS avg_aum,
       COUNT(*)
FROM products
WHERE json_extract(type_specific, '$.aum') IS NOT NULL
GROUP BY product_type;
```

## Classification Logic

### CSV products (`selected_etf.csv`)

| CSV condition | → `product_type` |
|---|---|
| `asset_class = MONEYMARKET` (VMRXX, FZDXX, SPAXX) | `money_market_fund` |
| Name/asset_class contains bond keywords | `bond_fund` |
| `asset_class = EQUITY` | `stock` |
| Other ETF (sector, blend, growth, commodities…) | `equity_fund` |
| `CURRENCY`, `CRYPTOCURRENCY`, `INDEX` | Skipped |

### OTC products (`otc_products.md`)

| OTC Section | Classification |
|---|---|
| **Fund** — sector/name contains "balanced", "multi-asset", or "conservative income" | `balanced_fund` |
| **Fund** — all other rows | `equity_fund` |
| **Bond** — all rows | `bond` |

## Yahoo Finance Enrichment

- Cache: `runs/test_data/.yahoo_cache.json` (95 tickers)
- Fetches: `fundFamily`, `navPrice`, `totalAssets`, `longBusinessSummary`, `marketCap`, `dividendYield`, `isin`, `exchange`, `country`
- Rate limit: 0.3s sleep between requests
- Re-fetch: delete cache and re-run seeder

## Known Gaps

| Item | Status |
|---|---|
| `expense_ratio` / `ter` for ETFs | Yahoo `annualReportExpenseRatio` often `None` |
| `strategy_summary` for HK tickers | Yahoo `longBusinessSummary` sometimes missing — synthetic fallback |
| `bond_fund` pricing (duration, OAS, YTW) | All `None` — needs Bloomberg/terminal data |
| `balanced_fund` allocation weights | Synthetic heuristic based on name |
| `stock` dividend_yield for HK stocks | Often `None` from Yahoo |

## Products Not Yet Seeded

These exist in source data but are intentionally deferred. Adding any requires:
1. A `_synth_xxx()` function returning a dict
2. A classification rule
3. An insert block in `seed()` — no DDL changes needed.

| product_type | Source | Count | Product IDs |
|---|---|---|---|
| `structured_product` | `otc_products.md` Structured table | 22 | PROD002, PROD004, PROD9988FCN, PROD009, PROD026–043 |
| `insurance` | `otc_products.md` Insurance table | 7 | PROD005, PROD012, PROD053–057 |
| `hedge_fund` | `otc_products.md` Alternative table | 2 | PROD058, PROD061 |
| `private_equity` | `otc_products.md` Alternative table | 4 | PROD006, PROD010, PROD059, PROD060 |
| `fx` | `selected_etf.csv` CURRENCY rows | 6 | EURUSD=X, USDJPY=X, GBPUSD=X, USDCNY=X, USDHKD=X, USDCNH=X |
| `crypto` | `selected_etf.csv` CRYPTOCURRENCY rows | 6 | LTC-USD, XRP-USD, BNB-USD, USDT-USD, ETH-USD, BTC-USD |
| `index` | `selected_etf.csv` INDEX rows | 1 | DX-Y.NYB |

## Files

```
src/test_data/
├── product_catalog.py          # Schema, get_conn(), search_aligned_products(), helpers
├── product_catalog_seed.py     # One-shot seeder
└── product_catalog.md          # This file

runs/test_data/
├── planbot.duckdb              # Unified DuckDB database (clients + holdings + products)
└── .yahoo_cache.json           # Yahoo Finance info cache (95 entries)
```

## Dependencies

```bash
uv pip install duckdb
```

`yfinance` already in project dependencies.

## Adding a New Product Type

1. Add `_synth_newtype(row_or_otc, …) -> dict` returning the type-specific fields
2. Add classification in `classify_row()` (for CSV) or `_classify_otc_xxx()` (for OTC)
3. Add insert block in `seed()` using the shared `_otc_to_general()` or inline
4. No DDL or schema changes required

## Related Docs

- Product schema: `docs/prompts/prod_spec/product_catalog/product_catalog.md`
- Tool spec: `docs/prompts/prod_spec/product_catalog/product_tool.md`
- Risk rating: `docs/spec/risk_rating.md`
- Source data overview: `data/planbot/shared/product_catalog/Overview of product catalog.md`
