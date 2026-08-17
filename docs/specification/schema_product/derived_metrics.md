# Derived Metrics & Ratings

> Metrics and 1–5 ratings computed **from** the plain performance metrics
> (see [`product_performance.md`](product_performance.md)) or from config
> tables.  These are single-value-per-ticker columns (`risk_rating`,
> `expected_return`, `certainty_*_rating`, `liquidity_rating`) plus the
> per-period `calmar_ratio`.

---

## 1. Overview

| Derived value | Computed from | Column(s) |
|---|---|---|
| Calmar ratio | CAGR / max drawdown | `{period}_calmar_ratio` (per period) |
| Risk rating | downside risk / max drawdown → threshold table + SGOV floor | `risk_rating` |
| Expected return | 5y CAGR (proxy) | `expected_return` |
| Certainty rating | z-score of CAGR & volatility → threshold table + caps | `certainty_{period}_rating` |
| Liquidity rating | Yahoo quote type / asset class → mapping table | `liquidity_rating` |

## 2. Shared Rating-Table Semantics

All threshold tables share one evaluation rule and one parser:

```
for each row in table (top to bottom):
    if threshold is None:       # catch-all
        return this_rating
    if value ≤ threshold:
        return this_rating
```

`_parse_rating_table()` converts the YAML `[{1: "1%"}, …]` form into
`[(rating, float_or_None)]` tuples, stripping `%` signs from string thresholds.
A missing final threshold means "everything above the previous row".

## 3. Calmar Ratio

**Code:** `_calmar_ratio()`

$$\text{calmar\_ratio} = \frac{\text{cagr}}{|\text{max\_drawdown}|}$$

- Computed per period, alongside the plain metrics.
- Blank if either CAGR or max drawdown is unavailable, or if max drawdown is 0.

## 4. Risk Rating (`risk_rating`)

**Code:** `_estimate_risk_rating()` + `_enforce_sgov_return_ratio_rule()`

Scale: **1** (lowest risk) to **5** (highest risk).

### 4.1 Primary — downside deviation

The rating is derived from **annualised downside deviation** (semi-deviation) of
the sampled returns, matched top-to-bottom against the config table:

```yaml
risk_rating:
  - 1: 1%     # downside ≤ 1%   → 1 (negligible downside)
  - 2: 4%     # downside ≤ 4%   → 2 (low)
  - 3: 10%    # downside ≤ 10%  → 3 (moderate)
  - 4: 20%    # downside ≤ 20%  → 4 (high)
  - 5:        # downside > 20%  → 5 (extreme)
```

Primary period is **1y**.  If 1y downside risk is unavailable, it falls back to
the longest available period.

### 4.2 Fallback — max drawdown

When downside risk cannot be computed (too few points), the function falls back
to **max drawdown** against the same thresholds.  If no drawdown data exists
either, it returns **3** (neutral).

### 4.3 Floor — SGOV return-ratio rule

**Code:** `_enforce_sgov_return_ratio_rule()`

For **ETFs only**, the risk rating cannot be lower than

$$\text{ceil}\!\left(\frac{|\text{1y\_return}|}{\text{SGOV\_1y\_return}}\right)$$

clamped to `[1, 5]`.  This prevents a low risk rating on an ETF whose return far
exceeds the risk-free rate.  SGOV (iShares 0–3 Month Treasury Bond ETF) is
fetched as the benchmark.

**Example:** 1y return = 11%, SGOV 1y return = 1% → floor `ceil(11) = 5` →
`risk_rating ≥ 5`.

## 5. Expected Return (`expected_return`)

**Code:** `_estimate_expected_return()`

Raw **5y CAGR** percentage (formatted to 2 decimals).  This is the proxy for the
analyst-estimated expected return.  Blank if 5y history is unavailable.

> ⚠️ The 5y horizon is fixed in the current code (`period_results.get("5y")`);
> it is not configurable.

## 6. Certainty Rating (`certainty_{period}_rating`)

**Code:** `_estimate_certainty_rating()` + `_apply_certainty_cap()`

Scale **1** (hope-based) to **5** (high certainty).  Measures the probability of
achieving the target return over a horizon.

### 6.1 Configuration

```yaml
certainty_enabled: false          # false → omit all certainty columns
certainty_target_return: 0        # fixed target r%
certainty_period: [1y, 3y, 8y]    # horizons that get columns
```

`certainty_period` is configured independently of the data `periods` list.

### 6.2 Method — z-score

$$z = \sqrt{T} \cdot \frac{r - \mu}{\sigma}$$

| Symbol | Value |
|---|---|
| $T$ | horizon in years |
| $r$ | `certainty_target_return` (fixed target %, default 0 = break-even) |
| $\mu$ | horizon-matched historical CAGR |
| $\sigma$ | horizon-matched annualised volatility |

Horizon matching (`_get_cagr_and_volatility_for_horizon()`): exact period match
preferred (e.g. `3y` → 3y CAGR & volatility); otherwise the **closest** period
by month distance.

Z-score → rating (top-to-bottom first match):

```yaml
certainty_rating:
  - 5: -2     # z ≤ -2.0  → 5 (high certainty)
  - 4: -1     # z ≤ -1.0  → 4 (probable)
  - 3: 0.5    # z ≤  0.5  → 3 (neutral)
  - 2: 1.5    # z ≤  1.5  → 2 (speculative)
  - 1:        # z >  1.5  → 1 (hope-based)
```

With $r = 0$: positive-$\mu$ products get negative $z$ (high certainty, growing
with horizon via $\sqrt{T}$); negative-$\mu$ products get positive $z$ (low
certainty).  Missing $\mu$ or $\sigma$ → neutral **3**.

### 6.3 Boundary caps

**Code:** `_apply_certainty_cap()`

Certainty is capped at **3** for:

- bonds (asset class contains "bond"/"government" but not "short"/"moneymarket")
- any product with `risk_rating > 2`

### 6.4 Known inconsistency

> ⚠️ `config/config_marketdata.yaml` still holds the legacy **percentile**
> thresholds (`[{1: 30%}, {2: 50%}, {3: 70%}, {4: 85%}, {5: 95%}]`) which do
> not match the z-score scale above, and `certainty_enabled: false`.  The code
> default (`[{5: -2}, {4: -1}, {3: 0.5}, {2: 1.5}, {1: None}]`) is the intended
> table; the YAML should be updated before enabling certainty.

## 7. Liquidity Rating (`liquidity_rating`)

**Code:** `_estimate_liquidity_rating()`

Scale **1** (illiquid/locked) to **5** (daily liquidity).

```yaml
liquidity_rating:
  etf: 5
  equity: 5
  currency: 5
  future: 5
  index: 5
  mutualfund: 4
  bond: 4
  structured: 3
  annuity: 3
  realestate: 2
  privateequity: 1
```

Matching (case-insensitive):

1. Exact match on Yahoo `quoteType`, then `assetClass`.
2. Substring match against the mapping keys.
3. No match → default **3** (neutral).

## 8. Implementation Reference

| Component | Location |
|---|---|
| Calmar ratio | `src/planbot/market_data_module.py` → `_calmar_ratio()` |
| Risk rating | `src/planbot/market_data_module.py` → `_estimate_risk_rating()` |
| SGOV floor rule | `src/planbot/market_data_module.py` → `_enforce_sgov_return_ratio_rule()` |
| Expected return | `src/planbot/market_data_module.py` → `_estimate_expected_return()` |
| Certainty (z-score) | `src/planbot/market_data_module.py` → `_estimate_certainty_rating()` |
| Certainty caps | `src/planbot/market_data_module.py` → `_apply_certainty_cap()` |
| Liquidity rating | `src/planbot/market_data_module.py` → `_estimate_liquidity_rating()` |
| Rating-table parser | `src/planbot/market_data_module.py` → `_parse_rating_table()` |
| Config YAML | `config/config_marketdata.yaml` |
| Tests | `tests/test_market_data_module.py` |
