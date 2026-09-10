To Do
=====

# Below are to do for a POC grade proposal generator

- Get investor readiness score include days to maturing
- TARF put in expected return assuming cap return reached
- Refine the proposal-client matching UI
- FX view
- Fix the bug in incremental concentration
- Portfolio review

## Minor improvement

- Move proposal generation to a server side API with JSON output
- Including holding PnL in proposal consideration?
- Let user refine the client, product after product matching and before product proposal generation

 
## All to-do below are too initial.  Need more investigation to confirm they are worth to do.
- Further divide risk rating to compare drawdown, vol during crisis period instead of general comparison
- Organized way to repopulate into DuckDB?
- For the expected return, shall average the last five years to avoid any peak in 3y period?
- Invoking PFS with multiple clients.  Pagination for every 30?
- search_by_investor_readiness_score to accept client filtering criteria

# Below are to do for a Smart Alert

Below are some Epics to do in the future

# Self update of market outlook and provide description (from suitability standpoint) for products based on news/data

# Goal Based Investing

# Efficient integration to product/client

# Move Scorecard to self-learning
- Two-Tower Deep Learning
  - Encode client profile and product in latent embedding
  - Training the model to cluster them together to predict client-product match

- The engine behind is Learn to Rank 
  - Linear RankNet to train scorecard?
    - 1000 labeled training data

# Efficient frontier?

# Scenario analysis like Historical VaR?

# Add psychology framework to the investment guide
- May not have sufficient information due to long questionnaire that no investor would like to take.


# Specialize agents

- Product matching
    - Needs identification
    - Product matching
- Scenario analyst
- Proposal writer

# proposal content
- Client with big loss leave them alone
- Portfolio Profit
- Warning in proposal description on concentration, or risk rating
- RM note vs. current holding
- SP recommendation
    - Recommend underlying FCN?
    - SP suggestion such as FCN taken from past transaction

# Suitability test
- PI
- Cash
- Tenor vs. Questionaire
- Risk rating
- Concentration
- Experience bought



# Done
- Slide where AI is delivered
- Multiple products switched out
- Add description on IRS & PFS to LLM
- Provide better diagnosis output for the proposal API
