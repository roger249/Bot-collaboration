# Product Performance Metrics

> Historical performance statistics for each product, computed directly from
> Yahoo Finance price history and written to `runs/market_data/<tickers_groupname>.csv`
> via `.venv/bin/python -m src.main run-market-data --config config/config_marketdata.yaml`.

---

## 1. Overview

The market-data module computes the **plain performance metrics** of financial
products — the raw statistical observations derived directly from a price
series.  These are the inputs to the **derived metrics** documented in
[`derived_metrics.md`](derived_metrics.md) (calmar ratio, risk rating, expected
return, certainty, and liquidity).

Plain metrics are computed **per period** (`6m`, `1y`, `3y`, `5y`, `10y`), so
each ticker produces one value per metric × period.  Values are rounded to 2
decimal places, or left blank when unavailable.

## 2. Dataflow

```
config/config_marketdata.yaml
        │
        ▼
┌──────────────────────────────────┐
│  MarketDataConfig (Pydantic)     │  src/planbot/market_data_module.py
│  load_market_data_config()       │  parses & validates YAML
└──────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────┐
│  get_market_data_from_config()   │  resolves ticker groups,
│                                  │  passes through to get_market_data()
└──────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────┐
│  get_market_data()               │
│                                  │
│  Per ticker:                     │
│  1. yfinance → price history     │
│  2. compute PeriodMetrics        │  ← plain metrics (this document)
│  3. derive ratings               │  ← see derived_metrics.md
│  4. assemble CSV row             │
└──────────────────────────────────┘
        │
        ▼
runs/market_data/<tickers_groupname>.csv
```

CLI entry point: `src/main.py` → `run-market-data` subcommand.

## 3. Configuration

The plain metrics are driven by three keys in `config/config_marketdata.yaml`:

```yaml
frequency: 1w
periods: [6m, 1y, 3y, 5y, 10y]
metrics:
  - return
  - CAGR
  - max_drawdown
  - calmar_ratio
  - downside_risk
  - volatility
```

| Key | Meaning | Allowed values |
|---|---|---|
| `frequency` | Price-sample interval | `1d`, `1w`, `1m`, `1q` (default `1w`) |
| `periods` | Look-back windows | free-form (`6m`, `1y`, `3y`, `5y`, `10y`) |
| `metrics` | Which metrics to compute | `return`, `cagr`, `max_drawdown`, `downside_risk`, `volatility`, `calmar_ratio`, `price_ihr_20`, `price_ihr_80` |

The code supports **eight** metric keys, but the current config enables **six**
(`return`, `cagr`, `max_drawdown`, `calmar_ratio`, `downside_risk`,
`volatility`).  The `price_ihr_20` / `price_ihr_80` intra-horizon risk columns
are available but not currently enabled.

Two further keys affect row content:

| Key | Meaning |
|---|---|
| `name_preference` | `long` (default) or `short` — which Yahoo name to emit |
| `asset_class_proxy` | Substitute ticker per asset class when history is missing/blank (e.g. `MONEYMARKET: SGOV`) |

> **Approximation note:** metrics other than the raw `return` are exact only
> when `frequency: 1d`.  At weekly/monthly/quarterly sampling, annualisation and
> CAGR use a fixed 52-points-per-year approximation.

## 4. Data Fetching

- Library: `yfinance`
- `frequency` maps to a yfinance interval: `1d→1d`, `1w→1wk`, `1m→1mo`, `1q→3mo`
- Each `period` maps to the yfinance `period` argument
- Timeout: 20 seconds per fetch
- The most recent price row supplies `last_closing_price` and `last_update_date`

### Asset-class proxy

```yaml
asset_class_proxy:
  MONEYMARKET: SGOV
```

When a ticker's history is empty (or all returns/drawdowns are zero/blank), the
module substitutes price history from the proxy ticker for the **same period**,
keeping the original ticker's identity in the row.  This covers instruments
(e.g. money-market funds) that Yahoo reports as flat.

## 5. Plain Metrics

Let $P_t$ be the closing price and $r_i = P_i / P_{i-1} - 1$ the simple
(single-period) returns over the sampled series.

| Metric | Formula | Column |
|---|---|---|
| Period return | $(P_{\text{last}} / P_{\text{first}} - 1) \times 100$ | `{period}_return` |
| CAGR | $\left((P_{\text{last}} / P_{\text{first}})^{1/y} - 1\right) \times 100$ | `{period}_cagr` |
| Max drawdown | $\min\!\left((P_t / \text{peak}_t - 1) \times 100\right)$ | `{period}_max_drawdown` |
| Downside risk | $\sqrt{\frac{1}{n}\sum \min(0, r_i)^2} \times \sqrt{52} \times 100$ | `{period}_downside_risk` |
| Volatility | $\sqrt{\frac{1}{n}\sum (r_i - \bar r)^2} \times \sqrt{52} \times 100$ | `{period}_volatility` |
| Intra-horizon risk | 20th / 80th percentile of $P_t$ | `price_{period}_IHR_20` / `price_{period}_IHR_80` |

Notes:

- Returns are **total returns** (Yahoo close prices already reflect dividends).
- `y` (years) is approximated as `(n_points - 1) / 52` — exact only for `1d`.
- Downside risk and volatility use **population** variance (divide by $n$, not
  $n-1$) and annualise with $\sqrt{52}$.
- `price_ihr_20` / `price_ihr_80` are **price levels** (not returns) — the 20th
  and 80th percentile closing prices over the period, used as an intra-horizon
  risk measure.

## 6. CSV Column Layout

```text
ticker, asset_class, name, currency, last_closing_price,
{period}_{metric} …,           # one column per metric × period (config order)
risk_rating, expected_return,  # derived — see derived_metrics.md
[certainty_{period}_rating …], # derived, omitted when certainty disabled
liquidity_rating,              # derived
last_update_date
```

With the current config (`6 metrics × 5 periods`), the dynamic block is 30
columns, ordered metric-major (all periods of `return`, then `cagr`, …).

Column-name mapping (`_metric_column_name`):

| metric | column |
|---|---|
| `return` | `{period}_return` |
| `cagr` | `{period}_cagr` |
| `max_drawdown` | `{period}_max_drawdown` |
| `downside_risk` | `{period}_downside_risk` |
| `volatility` | `{period}_volatility` |
| `calmar_ratio` | `{period}_calmar_ratio` |
| `price_ihr_20` | `price_{period}_IHR_20` |
| `price_ihr_80` | `price_{period}_IHR_80` |

## 7. Output Path

`output_filename` is `runs/market_data/<tickers_groupname>.csv`.  The
`<tickers_groupname>` placeholder is replaced with the executed group name (the
first group when several are merged).  A bare filename falls back to the
`output_dir` argument (default `data/planbot/shared/product_catalog`).

## 8. Implementation Reference

| Component | Location |
|---|---|
| Config model (`MarketDataConfig`) | `src/planbot/market_data_module.py` |
| Config parsing | `src/planbot/market_data_module.py` → `load_market_data_config()` |
| Main CSV generation | `src/planbot/market_data_module.py` → `get_market_data()` |
| Config → CSV bridge | `src/planbot/market_data_module.py` → `get_market_data_from_config()` |
| Per-period metric computation | `src/planbot/market_data_module.py` → `_calculate_period_metrics()` |
| Column-name builder | `src/planbot/market_data_module.py` → `_build_fieldnames()` / `_metric_column_name()` |
| CLI entry | `src/main.py` → `run-market-data` |
| Config YAML | `config/config_marketdata.yaml` |
| Tests | `tests/test_market_data_module.py` |
