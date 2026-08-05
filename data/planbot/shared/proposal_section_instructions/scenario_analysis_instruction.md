# Scenario Analysis of the Suggested Trade
```yaml
instructions: |
  Analyze the impact of the recommended trade under three scenarios.

  For every scenario, provide:
  1. A 1–2 sentence narrative describing the market conditions.
  2. An explicit probability estimate (as a percentage, sum of all three = 100%).
  3. A return-assumption table showing projected returns per asset class.
  4. A P&L comparison table: suggested portfolio vs. current portfolio.

  Important: the "." and the "|" are examples illustrating the format.
  Replace all numbers and product IDs with actual data from the input.
```

## Normal Market Condition
```yaml
instructions: |
  Describe a baseline scenario where markets perform in line with long-term
  historical averages.

  Assign a probability of 50% to this scenario.

  Return assumptions:
  - Global equities: 8–10% (5-year historical average).
  - Fixed income / bonds: 3–5% (5-year historical average).
  - Money market / cash: 2–3%.
  - State which specific historical period was used (e.g., "S&P 500 average
    annual return 2019–2024").

  Output a table with these columns:
  | Asset | Assumed Return % | Suggested Holding (USD) | Suggested P&L (USD) | Current Holding (USD) | Current P&L (USD) |
  |---|---|---|---|---|---|
  | ... | ... | ... | ... | ... | ... |
  | **Total** | — | **sum** | **sum** | **sum** | **sum** |

  Below the table, state:
  - Annual return of suggested portfolio vs. current: X% vs. Y%
  - Incremental benefit: +USD Z (+W% improvement)
```

## Upside Market Condition
```yaml
instructions: |
  Describe a bullish scenario where markets significantly outperform.

  Assign a probability of 25% to this scenario.

  Return assumptions:
  - Global equities: 15–20%.
  - Fixed income / bonds: 5–7%.
  - Money market / cash: 2–3%.
  - Justify the assumptions with a specific historical bull-market period
    (e.g., "2020–2021 post-COVID recovery rally") or current sentiment.

  Use the SAME table format as Normal Market Condition above.

  Below the table, state:
  - Annual return of suggested portfolio vs. current: X% vs. Y%
  - Incremental benefit: +USD Z (+W% improvement)
```

## Downside Market Condition
```yaml
instructions: |
  Describe a bearish scenario where markets significantly underperform.

  Assign a probability of 25% to this scenario.

  Return assumptions:
  - Global equities: −15% to −25%.
  - Fixed income / bonds: 0–3% (flight-to-quality bid).
  - Money market / cash: 1–2%.
  - Justify the assumptions with a specific historical stress period
    (e.g., "2022 rate-hike selloff", "2020 COVID-19 crash").

  Use the SAME table format as Normal Market Condition above.

  Below the table, state:
  - Annual return of suggested portfolio vs. current: X% vs. Y%
  - Incremental benefit (may be negative in this scenario): +USD Z

  Important: keep the "−" as minus sign as LMM could interpret as bullet.
```

## Scenario Summary
```yaml
instructions: |
  Output a final summary table:

  | Scenario | Probability | Suggested Return | Current Return | Incremental Benefit |
  |---|---|---|---|---|
  | Normal | 50% | X% | Y% | +USD Z |
  | Upside | 25% | X% | Y% | +USD Z |
  | Downside | 25% | X% | Y% | −USD Z |

  Then state the probability-weighted expected incremental benefit in one sentence.
```
