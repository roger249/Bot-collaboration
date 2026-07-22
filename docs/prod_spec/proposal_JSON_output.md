Refactor the proposal output
============================

# Introduction

We would like to break the product suggestion and proposal writing into two stages.  This can improve the response time and hopefully improve the LLM attentions where routine things could be implemented via program code that are more deterministic and less subject to hallucination and other uncertainty curing production. 

- LLM output all key decisive parameters and natural language description.
  - Executive summary
  - choosen product and rationale
  - pros and cons to the portfolio
  - The 3 scenarios relevant to the portfolio and product
  - References used by LLM
- External module to do precise calculation such as 
  - Details of the suggested product
  - Expected portfolio return
  - Scenario analysis
  - Charting such as pie chart or detail cashflow
  - Risk disclaimer

# Sprint 1

Generate a JSON output in parallel with the current md output for the reinvestment proposal.

Format of the JSON as below

Modify the prompt to output this file in parallel with md

The JSON will be returned when invoked thru API.  The md is an optional return

# Sprint 2 

- Product suggestion can use more sophisticated algorithm including machine learning to come up investment strategies from different perspective.  This could output a JSON format as

