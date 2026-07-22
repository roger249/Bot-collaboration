Refactor a proposal writer
==========================

# Introduction

We would like to break the product suggestion and proposal writing into two stages.

- LLM output all key decisive parameters and natural language description.
- External module to do precise calculation such as 
  - Portfolio return
  - Scenario analysis

This can improve the response time and hopefully improve the LLM attentions where routine things could be implemented via program code that are more deterministic and less subject to hallucination and other uncertainty curing production. 

- Product suggestion can use more sophisticated algorithm including machine learning to come up investment strategies from different perspective.  This could output a JSON format as

    Client, 
    (Recommendation Products, Reason), 
    (Suggested Products, Reason Pros and cons), 
    (Scenario, and asset movement))
    Executive Summary

- Proposal writer could be more taking the output client, list of suggested products, remark

- Scenario section PnL computation
- Pie chart of before/after
- Risk disclaimer- 
