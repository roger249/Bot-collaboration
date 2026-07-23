# Scenario analysis of the suggested portfolio
```yaml
instructions: |
- Come up three scenarios - Normal, Upside, Downside, based on some grounds such as historical or current market sentiment.  
- Assumption of the expected return for each asset shall have justification from historical as default, deviation from historical shall be justified.  
- Scenario shall include the assumption of the movement of each asset classes in the portfolio.
- Specify the probability of the scenario if data available.
- Any historical reference should have the exact from/to year and duration specified.
- For each scenario, have a summary table including PnL and projected cashflow for the suggested vs the current portfolio.
- The PnL shall be break down to the product level.
- After narrative scenario section, output a machine-readable proposal JSON block for external valuation between markers:
	- ---** PROPOSAL_JSON **---
	- ---** END_PROPOSAL_JSON **---
- The JSON block shall contain assumptions only; do not include portfolio-level computed totals.
- Use canonical product identifiers from the input data for instrument-level assumptions.
- Below is a illustration of the scenarios, feel free to use others that making better sense.
```

## Structured scenario JSON contract

The scenario JSON block should follow the contract defined in:
docs/prod_spec/proposal_JSON_output.md

Minimum required fields:
- schema_version
- proposal_type
- client_id
- catalog_context
- valuation_context
- scenario_set.scenarios[] with normal/upside/downside
- scenario_set.scenarios[].asset_class_returns[] and/or instrument_returns[]

Validation rules:
- Probability is optional; if any scenario includes it, all three must and sum to 1.0.
- All return_pct values are percentages, not decimals.
- Use unique scenario_id values.
- Include source/source_period where historical references are used.
- Instrument IDs must match product_id in the same-version catalog.

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
