Portfolio Health Review for <client name>
=========================================

# Summary

```yaml
instructions: |
Summarize in 3-4 sentences:
- Current portfolio health (one key strength, one key weakness)
- Recommended action (e.g., "reduce bonds by 5%, increase equities by 10%")
- Expected outcome (e.g., "improve long-term growth while managing downside risk")
```

# Potential Client Needs

```yaml
instructions: |
- Identify hidden needs in point form such as below.  If there're more than 3 needs identified, show only the top three, and use the top three for product suggestions.
    - children university education, etc.
    - mortgage refinancing, etc.
- For each hidden needs, attach a potential investment horizon to it.
- A list of needs could be found in shared/financial_needs/common_needs.md
```

Name: Alex Chan

|Potential Needs|Investment Horizon|Remark|
|---------------|----------------|---|
|Retirement|Long-term|Client estimated to retire in 10y|
|Children University Education|Medium-term|client has children will go into university in 10y|
|Reduce exposure to tech| N/A | Avoid concentration risk as client's career is in tech|

# Suggested Portfolio
```yaml
instructions: | 
- Tabulate the current portfolio and the suggested  as show below.
- Keep suggesting a maximum of 3 new products, if any.
- We shall suggest the exact asset and % so its executable so that it could be executed.  For example, increase AAPL to 30%.
- Total allocation adds up to 0% for the change column.
- Total allocation adds up to 100% for the current and suggested column.
- No need for come up another listing of the suggested asset except the table below.
- Show two pie charts indicating the portfolio allocation before this table using mermaid diagram syntax.
```

|Asset.     |Current| Suggested | Change | Remark|
|-----------|------:|----------:|-------:|----|
| Bond Fund |   20% | 15% | -5% | Need to put in high growth asset for retirement planning |
|Equity Fund|   30% | 40% | +10%| Increase equity for better growth potential |


```yaml
instructions: |
- Please analyze the pros and cons of the suggested holding with justification from the scenario analysis
- Any concentration risk?  If yes, please specify precise the asset that have concentration - currency, US exposure, etc.
```
## Pros and cons of suggested portfolio

- The current portfolio has a high allocation to bond funds, which provides stability but may not offer sufficient growth for long-term goals like retirement.
- The suggested portfolio reduces bond fund allocation and increases exposure to equities, which can enhance growth potential

# Scenario Analysis
```yaml
instructions: |
Please refer to the proposal_section_instructions/scenario_analysis_instruction to come up this section
```

# Risk Disclosure
```yaml
instructions: |
Please refer to the proposal_section_instructions/risk_disclosure_instruction to come up this section
```

# References
```yaml
instructions: |
Please refer to the proposal_section_instructions/reference_instruction to come up this section
```