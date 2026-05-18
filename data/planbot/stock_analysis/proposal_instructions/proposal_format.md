Stock Analysis: <Ticker>
========================

# Executive Summary
```yaml
instructions: |
Summarize in 3-4 sentences:
- Show in point form the basic information including company ticker, last closing price, TTM P/E and data date.
- Please crosscheck the last closing price & TTM PE from finance.yahoo.com against www.nasdaq.com to avoid any tool error.  No output from this check if the relative error < 2%.  
- Describe why market sentiment justify the current price ratio
- What's catalyst for the recommendation for this stock relative to its current valuation
```

# Company background
```yaml
instructions: |
Summarize in 3-4 sentences:
- Describe the major product/services the company earns its money.
- Provide one table with business lines as grouped rows and fiscal years as columns.
    - Columns: the latest 5 completed fiscal years, ordered oldest -> latest, plus a "5Y CAGR" column for revenue.
    - For each business line, include exactly 2 rows in this order:
        1) Revenue (state unit in header, e.g., USD bn)
        2) Profit Margin (%)
    - Add one "Total" group at the bottom:
        - Total Revenue row = sum of all listed business-line revenues by year
        - Total Profit Margin (%) row = weighted average margin by revenue for each year
    - If segment definitions changed over time, keep the latest segment names and add footnotes describing mapping assumptions.
    - Number shall be right aligned in the table
- Brief describe the changes in the earnings in each row.
```


# Historical Financial Performance and Pricing Ratio
```yaml
instructions: |
- Tabulate the following price ratio in rows for the last 8 years (columns) in a table format.  Low/High is the lowest and highest of the corresponding year.

    - Revenue
    - EPS
    - Operating Profit Margin
    - Price of the year (Low/High)
    - P/E (Low/High)
    - P/S (Low/High)
    - P/B (Low/High)
    - P/CF (Low/High)

- The cell shall have the value of the measures.  Any unit, if any, shall be in the row headings.
- Number shall be right aligned in the table
- Please provide the URL(s) where all these figures are retrieved.
- Add two columns at the right of the table showing the lowest and highest values of the row.
- Please verify P/E shall be in the range of Price/EPS.  Similar Validation for P/S to Price/(EPS/Profit Margin)
```

# Recent Major event impact the price
```yaml
instructions: |
- In additional to the past event, please also describe any looming concerns from the market for this company - lawsuit, policy changes, market focus, etc.
```

# Scenario Analysis
```yaml
instructions: |
Please show the expected the company earning or market sentiment changes in 2 years time for the three scenarios as below.  

- Normal, or the most probable
- Pemissitic
- Optimistic

In each scenario, please include the minimal the following information
- Scenario assumption
    - Please also make assumption of the evolution of the current looming concerns, if any.
    - If its interest rate related, please state the interest coverage ratio or similar to access its risk.
- Target price, and its timeframe.
- The rationale from target price, earning estimation, P/E, etc.
- All figures please contrast in % of its current value.
```

# Peers
```yaml
instructions: |
Provide no more than 3 companies with similar business segment to consider.  Skip this section if no similar companies found.
```

# References
```yaml
instructions: |
Please put up major references or website used to come up the material in this proposal
```
