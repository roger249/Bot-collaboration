# Lead generation

1. New Cash/Reinvestment.  Clients is filtered from product that will be matured and release funding.  Then engine shall match with similar products.
  
2. Product Investor Matcher.  RM choose a list of products (popular, bank's promotion, custom), and ask the system to filter out clients that may be interested in this products

3. Portfolio optimization
  - General
    - Better product selection
    - Concentration risk
    - Cash drag
  - Efficient frontier?
  - Goal based investing

# Product Investor matcher

It uses two-stage scorecard approach.


2. Product Fitness Score

Answers "What exactly should we pitch them?" It runs a deeper multi-asset evaluation to rank their affinity for specific Mutual Funds, Bonds, or Structured Products.


# Ideas
- We can leave product fitness score card incomplete and let LLM to choose from the product list by filling in other factors.
- The alternative product suggestion shall be done by LLM with the product catalog tool to put in some creativity




The process breaks down into few steps.

1.  Identify clients that fit to a given product list
2.  Identify product that fit to a given client list
3.  Review portfolio and provide rebalance suggestion


Compose the final proposal with 
- scenario analysis
- risk disclaimer

## Cash drag filter

## Proposal writing agent
Refactor a investment proposal taking a specific client, and product

- A tool should be built to single out the client info.
- A subset of product shall be given for alternative investment (use a tool?)

## Concentration risk filter
