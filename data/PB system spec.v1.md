# Overview of investment advisor

# Introduction

The major objective of this tool to let PB close more deals.  This includes the following areas.

*   Get more leads with the lead generator module
    
*   Automatic reveal client fits into certain characteristics, e.g., have children and age between 45-55 to target to annuity product for leftover to their children, and have invested/been investing in deposit, money market fund, bond fund.
    
*   Eliminate RM time to consolidate client profile from different systems.  AI generated talking points reduce RM time to prepare meeting and pre-meeting calls.
    
*   Provide various reports to faciliate closing and portfolio
    
*   Suggest suitable asset for the individual.
    
*   Personal investment suggetsion and portfolio review of the individual profile and current/future financial situation
    
*   Produce what-if report with the asset bought, optionally combined with the PnL of the portfolio of the client if required.
    

## Selling cycle and product features

Portfolio Health Check & Growth Opportunity Analysis

| Stage | Product features |
| --- | --- |
| Lead generation | *   RM crossell outreach cheatsheet<br>    <br>*   Product-investor matcher<br>    <br>*   Hidden need finder<br>    <br>*   Clients with increase of available fund near term finder (matured bond, etc.)<br>    <br>*   Potential risk reassesment finder |
| Qualifying | *   RM client 360 cheatsheet |
| Proposal | *   Chatbot to tailer made the needs<br>    <br>*   Personalized Investment Proposal<br>    <br>*   Portfolio health check and growth opportunity analysis |
| Closing | *   Term sheet generation |
| Retention and upsell | *   Portfolio health check and growth opportunity analysis<br>    <br>*   Portfolio expiry report <br>    <br>*   Potential KO/barrier breach report |

# Lead generation

## Three sources of leads

There’re three sources of lead

1.  Buyer driven.  An investor comes in who are looking for an investment opportunity.
    
2.  Product driven.  There’re some selective products that looks excellent in terms of risk return that require investor.  Typical investor are buying similar before and have cash in coming 3m.
    
3.  Hidden needs.  Investor with plenty of cash of equivalent sitting idle, having future expenses to meet.  For example, suggest Mortgage with private credit or high yield bond.  Education funding, etc.
    

This is summarized as below with the proposed product feature

| Leads | Classification | Product features |
| --- | --- | --- |
| Buyer driven | Investor actively looking for opportunity.  Possibly message RM for needs | *   Client 360 cheatsheet<br>    <br>*   Portfolio health check and growth opportunity analysis<br>    <br>*   Chatbot to tailer made the needs |
| Product driven | Identify potential opportunity starting from a set of hot-selling product. | *   Product investor matcher<br>    <br>*   RM cross sell outreach cheatsheet |
| Hidden needs | Those have hidden needs such as <br>*   Cash sitting idle<br>    <br>*   Have capital to release in next 3m<br>    <br>*   Have children that needs education fund<br>    <br>*   To retire in 10 year<br>    <br>*   High paid individual need to hedge their career/business | *   Hidden needs finder<br>    <br>*   Upcoming fund release finder<br>    <br>*   Potential risk reassessment<br>    <br>*   RM cross sell outreach cheatsheet |

Two types of screener to reveal client with hidden needs.

1.  Client that have improper risk assessed.  If reassement agreed, this opens hidden needs and open the whole new world of product to choose.
    
2.  Client with hidden needs not addressed.
    

## Potential risk reassesment

The report allows RM to identfy client that could should take different risk level.  For example, client holds stock or high net worth but invest large portion in CD/fixed deposit.  Some example as below.

| **Mismatch Type** | **AI Signal** | **Hidden Reality** |
| --- | --- | --- |
| **Panic Seller** | Trading frequency spikes during dips. | Low Volatility tolerance. |
| **Concentrator** | Single stock > 20% of NAV + Overconfident language. | Low Certainty. |
| **Yield Chaser** | High yield but assets move in sync with S&P 500. | False Certainty. |
| **Lifestyle Laggard** | Spending > Portfolio growth rate. | Insufficient Return. |

The screener will take demographic information and client profile to find hidden investment goal.

## Product invester matcher

## Hidden needs finder

## Upcoming fund release finder

The screener will filter out client that will have funds released for investment in near future (default 3m that could be adjusted on screen)

*   SP/Note/Bond matured
    
*   Option, in particular sell call will be exercised.
    
*   Potential Knock out 
    
*   Potential barrier breached.
    

### Knock out probability

*   Back test with recent three months?
    
*   Model calibrated to BS using 3m risk free rate
    

# RM cheatsheet

There are a two types of reports that will be often used.

1.  RM cheat sheet - Prepare the RM/IC to talk to the client.
    
2.  Client advisory - Explain to client the product and why it fits to his portfolio.
    

## Client 360 cheatsheet (for RM)

Talking points to client target to RM.  The report shall covers the following content

1.  Personal deomgraphic (marital status, age, etc.)
    
2.  Potential product and the talking points.  For the seeker, we may want to include product of higher risk and need to initiate new risk assessment process to close the deal.
    
3.  Client current holdings
    
4.  Expected cash to release in coming 6m
    
5.  Summary of previous call/meeting minute and recent bought
    
6.  Key questions to further qualify the prospect
    

## RM cross sell outreach cheatsheet (for RM)

Talking points to client for RM to call for a meeting.  The report shall covers the following content

1.  Hidden investment needs - education fee, retirement, mortgage downpayment, idle cash, etc.
    
2.  Personal deomgraphic (marital status, age, etc.)
    
3.  Potential product and the talking points.  For the seeker, we may want to include product of higher risk and need to initiate new risk assessment process to close the deal.  
    
4.  Key questions to further qualify the prospect
    

# Client proposal

## Personalized investment proposal (for Client)

1.  Summary of product benefit and why
    
    1.  Stable cashflow, capture AI gain, hedging the current career position (tech people choose non tech investment)
        
2.  Product characteristics such as maturity, coupon rate, risk
    
3.  Scenario analysis that includes return, cashflow.  
    
    1.  Product alone
        
    2.  Portfolio level (optional)
        

## Portfolio health check & growth opportunity (for Client)

1.  Current portfolio characteristics - pros and cons 
    
2.  Suggest to change or rebalance of the current portfolio and why
    
3.  Addition product characteristics, if any, such as maturity, coupon rate, risk
    
4.  Scenario analysis that includes return, cashflow.  
    
    1.  Product alone
        
    2.  Portfolio level
        

## Scenario analysis

Based on model with model with correct distribution.  Could use BS for at the very beginning with certain simplified assumptions.

*   Best scenario
    
*   Expected scenario
    
*   Worst scenario
    
*   KO probability
    

Later to move to SVCJ for Stock/bitcoin?

## Termsheet?

This generates the termsheet for closure

**NLP generates term sheet**

*   Include term and all above discussion
    

# Chatbot

Basically this js a prompt-to-investment advisor that could be operated by the investor alone or with the guidance of a financial advisor 

There are two modes of operation

*   Get a final report of the recommendation based on AI based on a aged profile 
    
*   Have a workflow to ask a few questions or preferences in market, geographical underlying
    

# Data needed for MCP integration

The data below preferably feed by MCP

## Demographic 

in particular the taxation consideration

## Client profile 

*   Current holdings
    
*   Human capital - should hedge the industry the client is working in
    
*   Stability of source of funding
    
*   Future consumption or liability matching - duration and industry
    
*   Note from previous meetings minute
    

## Product portfolio

This should include the rating of the product in the four dimensions.

*   Expected return
    
*   Volatility
    
*   Certainty of return at maturity
    
*   Liqudity
    

**Motivation - to add the product**

*   Less volatility with lower return
    
*   Income generation
    
*   Protect market adjustment from high valuation of the market 
    
*   Forward looking of a particular industry
    

*   The product universe with preference from the seller
    

# Outstanding

Interest rate?

Commodity?

*   Structured Product integration deployment
    
*   Pricing model
    

## To test

*   AI response
    
*   Constrained prompt
    
*   Demo data?
    
*   Capability in performing stress test (or generate stress test scenario from historical data)
    

# Additional idea for AI assistant

1.  Term sheet reconciliation including OCR
    
2.  Market data cleansing
    
3.  Model validation
    
4.  Marketing theme - estate planning, children education, retirement, etc.