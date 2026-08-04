# Scenario analysis of the suggested portfolio
```yaml
instructions: |
- Analyze three scenarios: Normal, Upside, Downside.
- Ground scenarios in historical data or current market sentiment.  State exact historical period (from–to year, duration) when used.
- Specify asset-class return assumptions.  Default to historical average; justify any deviation.
- Provide a probability estimate for each scenario where data supports it.
- Include a summary table per scenario: product-level PnL and projected cashflow for the suggested portfolio vs. the current portfolio.
- Use only canonical product identifiers from the input data.
```


## Normal Market Condition
- Projected global equity returns: 10%.  This was an average return for the last 5 y
- Projected money market returns: 2%.  This was an average return for the last 5 y

| Product | % Return | Suggested Holding | Return | Current Holding | Return |
| ------- | -------: | ----------------: | -----: | --------------: | -----: |
| APPL    |       10 |                60 |      6 |              10 |    1.0 |
| AGG     |        5 |                40 |      2 |              90 |    4.5 |
| Total   |        8 |               100 |      8 |             100 |    5.5 |

- Annual return of the suggested portfolio vs current : 8% vs 5.5%
- Incremental benefit: +HKD 98,000 annually (+23% improvement)

## Good Market Condition

## Bad Market Condition - Equity collapse similar to COVID-19
- Projected global equity returns: -20%.  This was an average return during the COVID-19 market crash
