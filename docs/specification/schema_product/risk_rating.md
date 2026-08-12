# Product Catalog: Dataflow & Field Computation

> How `config/config_marketdata.yaml` drives the generation of
> `runs/market_data/<tickers_groupname>.csv` via
> `.venv/bin/python -m src.main run-market-data --config config/config_marketdata.yaml`

---

## 1. End-to-End Dataflow

```
config/config_marketdata.yaml
        │
        ▼
┌──────────────────────────────────┐
│  MarketDataConfig (Pydantic)     │  src/planbot/market_data_module.py:29
│  load_market_data_config()       │  Parses & validates YAML
└──────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────┐
│  get_market_data_from_config()   │  src/planbot/market_data_module.py:393
│  - resolves ticker groups        │
│  - passes through to             │
│    get_market_data()             │
└──────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────┐
│  get_market_data()               │  src/planbot/market_data_module.py:205
│                                  │
│  Per ticker:                     │
│  1. yfinance → price history     │
│  2. compute PeriodMetrics        │
│     (return, CAGR, drawdown,     │
│      downside_risk, volatility)  │
│  3. derive ratings               │
│  4. assemble CSV row             │
│                                  │
│  Output: CSV file                │
└──────────────────────────────────┘
        │
        ▼
runs/market_data/<tickers_groupname>.csv
```

CLI entry point: `src/main.py:168` — `run-market-data` subcommand.

---

## 2. CSV Column Layout

The generated CSV has this column order:

| # | Column(s) | Source |
|---|---|---|
| 1–5 | `ticker`, `asset_class`, `name`, `currency`, `last_closing_price` | Yahoo Finance `info` dict + latest history row |
| 6–N | `{period}_{metric}` | One column per metric × per period (e.g., `1y_return`, `3y_cagr`) |
| N+1 | `risk_rating` | §3 below |
| N+2 | `expected_return` | §4 below |
| N+3+ | `certainty_{period}_rating` | §5 below (omitted if `certainty_enabled: false`) |
| … | `liquidity_rating` | §6 below |
| last | `last_update_date` | Date of most recent price row |

The `{period}_{metric}` columns are driven by `metrics` × `periods` in the YAML:

```yaml
# config/config_marketdata.yaml (defaults shown)
metrics: [return, CAGR, max_drawdown, calmar_ratio, downside_risk, volatility]
periods: [6m, 1y, 3y, 5y, 10y]
# → 6 × 5 = 30 dynamic columns
```

Column names: `{period}_cagr`, `{period}_calmar_ratio`, `{period}_downside_risk`, `{period}_volatility`, `{period}_max_drawdown`. Plus `price_{period}_IHR_20` and `price_{period}_IHR_80` if requested.

Each cell is the computed metric value rounded to 2 decimal places, or blank if unavailable.

---

## 3. Risk Rating (`risk_rating`)

**Code:** `_estimate_risk_rating()` + `_enforce_sgov_return_ratio_rule()`

### 3.1 Primary: Downside Deviation via Config Table

The rating is derived from **annualised downside deviation** (semi-deviation) of weekly returns ($\sqrt{52}$ scaling), matched against the config table:

```yaml
risk_rating:
  - 1: 1%     # downside ≤ 1%   → rating 1 (Negligible Downside)
  - 2: 4%     # downside ≤ 4%   → rating 2 (Low Downside Volatility)
  - 3: 10%    # downside ≤ 10%  → rating 3 (Moderate Downside Volatility)
  - 4: 20%    # downside ≤ 20%  → rating 4 (High Downside Volatility)
  - 5:        # downside > 20%  → rating 5 (Extreme Downside Volatility)
```

The table is evaluated top-to-bottom: the **first** row whose threshold ≥ the computed downside deviation wins. The final entry with no threshold is the catch-all.

**Primary period:** 1y. If 1y downside_risk is unavailable, falls back to the longest available period.

### 3.2 Fallback: Max Drawdown

When downside_risk is not computable (too few data points), the function falls back to **max_drawdown** compared against the same config thresholds. If no drawdown data exists either, returns 3 (neutral).

### 3.3 Boundary Rule: SGOV Return Ratio Floor

**Code:** `_enforce_sgov_return_ratio_rule()`

For ETFs only: the risk rating cannot be lower than

$$\text{ceil}\!\left(\frac{|\text{1y\_return}|}{\text{SGOV\_1y\_return}}\right)$$

This prevents low risk ratings on ETFs with returns that far outstrip the risk-free rate. SGOV (iShares 0-3 Month Treasury Bond ETF) is fetched as the benchmark.

**Example:** If an ETF has 1y return = 11% and SGOV returned 1%, the floor is `ceil(11) = 5` → risk_rating ≥ 5.

---

## 4. Expected Return (`expected_return`)

**Code:** `_estimate_expected_return()`

Raw **3Y CAGR** percentage, formatted to 2 decimal places. Not a 1–5 score.

- Uses `PeriodMetrics.cagr` from the 3y window.
- Blank if 3y history is unavailable.
- This is the **proxy** for analyst-estimated expected return per the spec.

---

## 5. Certainty Rating (`certainty_{period}_rating`)

**Code:** `_estimate_certainty_rating()`

### 5.1 Configuration

```yaml
certainty_enabled: false          # true  → include certainty columns
                                  # false → omit all certainty columns
certainty_target_return: 0        # fixed target r%
certainty_period:                 # which horizons get certainty columns
  - 1y
  - 3y
  - 8y
```

The certainty_period list determines how many columns appear. Periods are configured independently of the data `periods` list.

### 5.2 Method: `zscore`

**Formula:**

$$z = \sqrt{T} \cdot \frac{r - \mu}{\sigma}$$

| Symbol | Value |
|---|---|
| $T$ | Horizon in years (`_period_to_months(horizon) / 12`) |
| $r$ | `certainty_target_return` — fixed target % (default: 0 = break-even) |
| $\mu$ | Horizon-matched historical CAGR |
| $\sigma$ | Horizon-matched annualised volatility ($\sqrt{52}$ scaled) |

**Horizon matching** (`_get_cagr_and_volatility_for_horizon()`):
- Exact period match preferred (e.g., "3y" → use 3y CAGR & volatility).
- Falls back to the **closest** available period by month distance.

**Z-score → rating**: the z-score is compared against the config table (top-to-bottom first-match):

```yaml
certainty_rating:
  - 5: -2     # z ≤ -2.0  → rating 5  (High Certainty)
  - 4: -1     # z ≤ -1.0  → rating 4  (Probable)
  - 3: 0.5    # z ≤  0.5  → rating 3  (Neutral)
  - 2: 1.5    # z ≤  1.5  → rating 2  (Speculative)
  - 1:        # z >  1.5  → rating 1  (Hope-Based)
```

**Behaviour with $r = 0$:**
- Positive-$\mu$ products → negative $z$ → high certainty (more so at longer horizons)
- Negative-$\mu$ products → positive $z$ → low certainty
- The $\sqrt{T}$ factor amplifies: certainty **grows with horizon** for winning products and decays for losers.

### 5.3 Certainty Boundary Caps

**Code:** `_apply_certainty_cap()`

Irrespective of method, certainty is capped at **3** for:
- Bonds (asset class contains "bond" or "government" but not "short" or "moneymarket")
- Any product with risk_rating > 2

---

## 6. Liquidity Rating (`liquidity_rating`)

**Code:** `_estimate_liquidity_rating()`

### 6.1 Asset-Type Mapping

```yaml
liquidity_rating:
  etf: 5              # Exchange-traded
  equity: 5
  mutualfund: 4       # Standard managed
  bond: 4
  structured: 3       # Lock-up
  annuity: 3
  realestate: 2       # Transaction-dependent
  privateequity: 1    # Opaque
```

Matches **case-insensitively** against:
1. `info["quoteType"]` (e.g., "ETF")
2. `info["assetClass"]`
3. Substring match within either field

If no YAML mapping matches, defaults to **3** (neutral).

---

## 7. Ticker Selection & Merging

```yaml
execute_ticker_groupname:          # string or list
  - selected_etf
  - demo-market-1Jun26

ticker_groups:
  selected_etf: [XLK, XLF, …]
  demo-market-1Jun26: [NEAR, JPST, …]
```

- Single string: uses that group only.
- List: **merges** all groups (order preserved, duplicates removed), writes output using the **first** group name for the filename.
- CLI overrides: `--tickers SPY QQQ` or `--ticker-groupname test`.

---

## 8. Data Fetching & Metric Computation

### 8.1 Yahoo Finance Fetch

- Library: `yfinance`
- Frequency: configured as `1w` → yfinance interval `1wk`
- Periods: configured list (e.g., `1y`, `3y`, …) → yfinance `period` parameter
- Timeout: 20 seconds per fetch

### 8.2 Asset Class Proxy

```yaml
asset_class_proxy:
  MONEYMARKET: SGOV
```

When a ticker's history returns all-zero or blank metrics, the module substitutes price history from the proxy ticker for the **same period**, preserving the original ticker's identity in the row.

### 8.3 Computed Metrics (per period)

| Metric | Formula | Column |
|---|---|---|
| `period_return` | $(P_{\text{last}} / P_{\text{first}} - 1) \times 100$ | `{period}_return` |
| `cagr` | $((P_{\text{last}} / P_{\text{first}})^{1 / \text{years}} - 1) \times 100$ | `{period}_cagr` |
| `max_drawdown` | $\min( (P_t / \text{peak}_t - 1) \times 100 )$ | `{period}_max_drawdown` |
| `calmar_ratio` | $\text{cagr} / |\text{max\_drawdown}|$ | `{period}_calmar_ratio` |
| `downside_risk` | $\sqrt{\frac{1}{n}\sum \min(0, r_i)^2} \times \sqrt{52} \times 100$ | `{period}_downside_risk` |
| `volatility` | $\sqrt{\frac{1}{n}\sum (r_i - \bar{r})^2} \times \sqrt{52} \times 100$ | `{period}_volatility` |

where $r_i$ are weekly log returns and 52 is the annualisation factor (weekly frequency).

---

## 9. Rating Config Table Semantics

All rating tables (`risk_rating`, `certainty_rating`) share the same evaluation logic:

```
for each row in table (top to bottom):
    if threshold is None:       # catch-all
        return this_rating
    if value ≤ threshold:
        return this_rating
```

The `_parse_rating_table()` helper converts the YAML `[{1: "1%"}, …]` format into `[(rating, float_or_None)]` tuples, stripping `%` signs from string thresholds.

---

## 10. Implementation Reference

| Component | File | Line |
|---|---|---|
| Config model | `src/planbot/market_data_module.py` | 29 |
| YAML parsing | `src/planbot/market_data_module.py` | 183 |
| Main CSV generation | `src/planbot/market_data_module.py` | 205 |
| Config → CSV bridge | `src/planbot/market_data_module.py` | 393 |
| Risk rating | `src/planbot/market_data_module.py` | 830 |
| SGOV floor rule | `src/planbot/market_data_module.py` | 920 |
| Expected return | `src/planbot/market_data_module.py` | 881 |
| Certainty (zscore) | `src/planbot/market_data_module.py` | 896 |
| Certainty caps | `src/planbot/market_data_module.py` | 944 |
| Liquidity rating | `src/planbot/market_data_module.py` | 983 |
| Rating table parser | `src/planbot/market_data_module.py` | 167 |
| Fieldnames builder | `src/planbot/market_data_module.py` | 458 |
| CLI entry | `src/main.py` | 168 |
| Config YAML | `config/config_marketdata.yaml` | — |
| Tests | `tests/test_market_data_module.py` | — |
