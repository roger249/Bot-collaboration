Investor Readiness Score Card
=============================

Objective: Screen the entire client pool to isolate the top clients who need to execute a transaction due to structural portfolio anomalies.

These clients could then be used for input to product matching or a portfolio review for any up-sell opportunities.

The total score is computed by four dimensions.

- Cash drag - portfolio has too much cash.
- Concentration risk - portfolio has high concentration
- Investment experience - One who is exposes to investment of MF/ETF are more willing to accept rebalancing of the portfolio
- Life stage - one who is in mid-life to retirement would have a number of changing needs

The score are computed as below

score = w_cash * s_cash + w_concentration * s_concentration + w_active * s_active + w_lifestage * s_lifestage

All weight are put in a yaml file as illustrated in sections below.

s_* are the score from each aspect, scales from 0-10

w_* are weight used scale the weight for each dimension, default to 1, suggest to be in the range of 0.5 - 2

These parameter could be trained by machine learning if sufficient samples are given by the bank.

## Cash Drag 

Cash equivalent includes cash, deposits + Money Market Funds

  k_cash = Cash or cash equivalent / Portfolio Value

```yaml
  
  score_cash_drag:
    weight: 1
    # The score s_cash is interpolated from the table below, e.g., k_cash is 0.3 it'll be interpolated from 0.2 (3) and 0.5 (9), i.e, (3+9)/(0.5-0.2) * (0.3-0.2).  Flat extrapolation if beyond the smallest and largest pivot points
    - score:
        0.0: 0
        0.2: 3
        0.5: 9
        1.0: 10
```


## Concentration Risk (Single-stock vulnerabilities)
    k_concentration = max(
      s_single_holding_exposure(largest_holding / portfolio_value),
      s_sector_exposure / portfolio_value,
      s_region_exposure / portfolio_value,
      s_asset_class_exposure / portfolio_value,
    )
```yaml
  score_concentration_risk:
    weight: 1
    - s_single_holding:
        0.2: 0
        1.0: 10
    - s_sector_exposure:
        0.3: 0
        1.0: 10
    - s_region_exposure:
        0.4: 0
        1.0: 10
    - s_asset_class_exposure:
        0.6: 0
        1.0: 10
```


## Investment experience

```yaml
  score_active_manage:
    weight: 1
    - score_number_of_trading_ttm:
        0: 0
        2: 7
        5: 7
        12: 4      # Investor may not want to rebalance too frequent so score is lower.
        20: 1
    - has_fund: 3   # if client has Stock/ETF/MF/SP in the portfolio
```

## Life stage

```yaml
  score_life_stage
    weight: 1
    - score_age:
        25: 0
        35: 5      # Mid-career accumulation setup
        45: 10     # Peak wealth alignment, preservation, and retirement structural, children education, etc.
        65: 10
        80: 5
```
