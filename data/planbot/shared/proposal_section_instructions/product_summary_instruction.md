```yaml
instructions: |
When a product is recommended, either the main suggestion or alternative suggestion, the product summary shall be put up as the section below.
```

### Product Summary
```yaml
instructions: |
  Present the product's key terms as a table with two columns: **Attribute** and **Value**.
  Include ALL of the following rows (use "N/A" if a field is unavailable):

  | Attribute | Value |
  |---|---|
  | Product ID | {product_id} |
  | Product Name | {product_name} |
  | Product Type | {product_type} |
  | Asset Class | {asset_class} |
  | Region | {region} |
  | Sector | {sector} |
  | Risk Rating | {risk_rating} |
  | Expected Return (5Y CAGR) | {expected_return}% |
  | Expense Ratio | {expense_ratio} |
  | Time to Maturity | {time_to_maturity} |
  | Coupon | {coupon} |
  | Investment Note | {investment_note} |
```

### Performance Metrics Comparison
```yaml
instructions: |
  Compare the historical performance of the suggested product against the
  funding-source product (the one being sold).  Present as a table:

  | Metric | {suggested_product_id} | {funding_source_id} |
  |---|---|---|
  | 1Y Return | X% | Y% |
  | 3Y CAGR | X% | Y% |
  | 5Y CAGR | X% | Y% |
  | Max Drawdown | X% | Y% |
  | Calmar Ratio | X | Y |

  If historical data is unavailable for either product, state "Data unavailable"
  for the missing cells and note the limitation in one sentence below the table.
```

### Risk Characteristics
```yaml
instructions: |
  Describe the risk profile of the suggested product in 2–3 sentences covering:
  1. Risk rating and what it implies for the client's portfolio volatility.
  2. Key risk factors specific to this product (e.g., sector concentration,
     interest-rate sensitivity, currency exposure, credit risk).
  3. How the product's risk compares to the funding-source product being sold.

  Do not use a table for this section.  Prose only.
```

