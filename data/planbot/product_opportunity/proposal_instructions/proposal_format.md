# Investment Advisory Proposal for:
{client_name} ({client_id})
Prepared by: Louis Ng
Date: {date}

```yaml
instructions: |
  Replace {client_name} and {client_id} with values from the client profile.
  The title is a level-1 heading (#).
```
---

## Executive Summary
```yaml
instructions: |
  Write exactly 3–4 sentences covering ALL three of the following, in order:
  1. **Recommended action** — State the product to buy, the amount (in USD), the
     percentage of AUM it represents, and the funding source (what is sold).
  2. **Why** — One sentence explaining the primary investment rationale linking
     the product's characteristics to the client's stated financial needs.
  3. **Expected outcome** — One sentence describing the projected benefit (e.g.,
     improved diversification, higher income, reduced concentration risk,
     better risk-adjusted return).

  Do not include any bullet points, lists, or YAML in the Executive Summary output.
  Output only the 3–4 prose sentences.
```

---

## Recommended Product: {product_name} ({product_id})
```yaml
instructions: |
  Replace {product_name} and {product_id} with values from the product catalog.
  This is a level-2 heading (##).
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

### Detailed Justification (For Bank Internal)
```yaml
instructions: |
  Write in points form about the following:

  1. Evaluated products and why this one are suggested, and not the others.
  1. **Client-need alignment** (if relevant) — Which specific financial needs from the client
     profile does this product address?  Reference the stated needs explicitly
     (e.g., "long-term capital growth," "income generation," "capital preservation").
  2. **Fitness-score interpretation** — Reference the fitness score and its
     component breakdown (risk match, concentration, experience, better product).
     Explain what each component means in the context of *this specific client*.
  3. **Funding rationale** — Why is the selected funding source the right asset to
     sell?  Address opportunity cost, concentration impact, and tax/liquidity
     implications where data supports it.
  4. **Market context** — How does the current market outlook support or caution
     against this recommendation at this time?  Good to refer to the market_outlook material for relevant excerpt.

  Do not repeat the product specifications table.  Assume the reader has already
  seen it.
```

---

## Suggested Portfolio Allocation
```yaml
instructions: |
  Follow the format and instructions in
  `proposal_section_instructions/suggested_portfolio_instruction.md`.

  Output this section as a level-2 heading (##).
```

---

## Scenario Analysis
```yaml
instructions: |
  Follow the format and instructions in
  `proposal_section_instructions/scenario_analysis_instruction.md`.

  Output this section as a level-2 heading (##).
```

---

## Risk Disclosure
```yaml
instructions: |
  Follow the format and instructions in
  `proposal_section_instructions/risk_disclosure_instruction.md`.

  Output this section as a level-2 heading (##).
```

---

## References
```yaml
instructions: |
  Follow the format and instructions in
  `proposal_section_instructions/reference_instruction.md`.

  Output this section as a level-2 heading (##).
```
