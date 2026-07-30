# Client & Holdings Schema

Reversed from the live DuckDB: [`data/planbot/db/planbot.duckdb`](../../data/planbot/db/planbot.duckdb)

Two tables — the `profiles` table previously existed but was empty and has been dropped.

- `clients` — denormalized client master + demographics (23 rows)
- `holdings` — normalized positions per client, FK to products catalog (180 rows)

---

# Client schema

```yaml

# =============================================================================
# CLIENTS — Master record + demographics, denormalised for zero-JOIN lookups
# =============================================================================

clients:
  - client_id                # Primary key. Format: PB-HK-NNNNNNN-N
  - name                     # Full display name
  - aum                      # Total portfolio value (base currency)
  - cash_pct                 # Percentage of AUM held as cash (0–100)
  - region                   # Primary geographic region
                             #   Known: Europe, North America, APAC, LatAm
  - birthdate                # ISO 8601 (YYYY-MM-DD), or "N/A" for corporate entities
  - occupation               # e.g. Retired, CFO, Corporate Entity
  - risk_rating              # 1‑5 risk tier. 1 = conservative, 5 = aggressive
  - marital_status           # Single, Married, Divorced
  - children_info            # e.g. "2 children", "0 children"
  - liquidity_need           # e.g. "Medium (12 months buffer)"
                             #   Planned migration → needs section
  - income_stability         # e.g. "Stable pension", "Self-employed"
  - investment_objective     # e.g. "Regular income"
                             #   Planned migration → needs section
  - qualitative_profile      # This is a free text entered by RM and targeted for LLM/RM to understand more on the client and suggest product
```

**Sample:**

```yaml
client_id:              PB-HK-000003-4
name:                   James Harrison
aum:                    12,500,000
cash_pct:               5.2
region:                 North America
birthdate:              1959-01-01
occupation:             Retired
risk_rating:            2
marital_status:         Married
children_info:          2 children
liquidity_need:         Medium (12 months buffer)
income_stability:       Stable pension
investment_objective:   Regular income
```

---

# Holdings Schema

```yaml

# =============================================================================
# HOLDINGS — Normalised positions per client
# Source CSV stored up to 10 nested holdings in wide format.
# ETL in src/planbot/investor_readiness_score.py normalises into this table.
# =============================================================================

holdings:
  - client_id                # FK → clients.client_id
  - holding_idx              # 0‑based position in client's portfolio
  - holding_id               # Internal position identifier (e.g., ph-1-shv-o-0)
  - product_id               # FK → products.product_id
  - instrument_name          # Display name of the security
  - symbol                   # Ticker symbol (e.g., SHV.O, 0700.HK)
  - asset_class              # Broad asset class
                             #   Known: Cash, Alternatives, Fixed Income, Equities
  - region                   # Geographic exposure of this holding
  - currency                 # Settlement currency (e.g., USD, HKD)
  - quantity                 # Units held
  - book_cost                # Acquisition cost
  - market_value             # Current market value
  - unrealized_pl            # Unrealized profit/loss
  - unrealized_pl_pct        # Unrealized P&L as percentage
  - yield_pct                # Current yield percentage
  - risk_bucket              # Risk classification (e.g., Low, Medium)
  - esg_score                # ESG rating (nullable — not populated for all holdings)
  - liquidity                # Settlement liquidity (e.g., T+2)
```

**Primary key**: `(client_id, holding_idx)`

**Sample:**

```yaml
client_id:        PB-HK-000003-4
holding_idx:      0
holding_id:       ph-1-shv-o-0
product_id:       ETF-SHV
instrument_name:  iShares Short Treasury Bond ETF
symbol:           SHV.O
asset_class:      Cash
region:           North America
currency:         USD
quantity:         5,891.95
book_cost:        645,481.63
market_value:     650,000.00
unrealized_pl:    4,518.37
unrealized_pl_pct: 0.7
yield_pct:        4.0
risk_bucket:      Low
esg_score:        null
liquidity:        T+2
```

---

# Key Relationships

```
clients.client_id ───< holdings.client_id
                          │
                          └── holdings.product_id ───> products.product_id
```

- `clients` and `holdings` JOIN on `client_id`.
- `holdings` JOINs to the product catalog (`products` table) on `product_id` for product-type, risk, expected-return enrichment.
- Both `clients` and `holdings` are loaded by `src/planbot/investor_readiness_score.py` during first-run ETL.
