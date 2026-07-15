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

1. Investor readiness score
It filters out clients that may have tendency to rebalance their portfolio.

2. Product Fitness Score
For each clients from first one, given a list of products, compute the score of each product for each client based on his/her demographic and holding information. 

3. With these two score LLM will make final decision based on 
  - product fitness score of the selected clients
  - the description of the product against the client background


# Ideas
- We can leave product fitness score card incomplete and let LLM to choose from the product list by filling in other factors.
- The alternative product suggestion shall be done by LLM with the product catalog tool to put in some creativity


Compose the final proposal with 
- scenario analysis
- risk disclaimer

## Cash drag filter

## Concentration risk filter


## Proposal writing agent
Refactor a investment proposal taking a specific client, and product

- A tool should be built to single out the client info.
- A subset of product shall be given for alternative investment (use a tool?)
