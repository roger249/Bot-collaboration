# Overview of investment advisor

# Introduction

The major objective of this tool is to help Private Bankers (PB) close more deals by streamlining the entire sales cycle from lead generation to retention. This includes:

*   **Lead Generation**: Automatically identify prospects with hidden needs, upcoming liquidity events, or product-fit characteristics.  For example, automatic reveal client fits into certain characteristics, e.g., have children and age between 45-55 to target to annuity product for leftover to their children, and have invested/been investing in deposit, money market fund, bond fund.
    
*   **Time Efficiency**: Eliminate RM time spent consolidating client profiles from disparate systems; AI-generated talking points reduce meeting preparation time
    
*   **Proposal Quality**: Provide personalized investment proposals, portfolio health checks, and scenario analyses
    
*   **Closing Support**: 
    
    *   Generate term sheets and reconcile counterparty documents
        
    *   Suggest suitable asset for the individual.
        
    *   Personal investment suggetsion and portfolio review of the individual profile and current/future financial situation
        
    *   Produce what-if report with the asset bought, optionally combined with the PnL of the portfolio of the client if required.
        
*   **Retention & Upsell**: Monitor portfolio events (expirations, knock-out risks, barrier breaches) to trigger proactive outreach
    
*   **Management Visibility**: Track sales effectiveness metrics and conversion funnel performance
    

---

## Selling cycle and product features

| Selling cycle | Product features / artifact |
| --- | --- |
| Lead generation | *   Lead Generation - Crossell outreach cheatsheet<br>    <br>*   Lead Generation - Hidden need finder<br>    <br>*   Lead Generation - Product-investor matcher<br>    <br>*   Investment Advisor - Upcoming fund release finder.  <br>    <br>    *   Portfolio expiry report <br>        <br>    *   Potential KO/barrier breach report <br>        <br>    *   Liquidity Ladder<br>        <br>*   Lead Generation - Potential risk reassesment finder |
| Qualifying | *   RM Intel - Client pre-meeting cheatsheet<br>    <br>*   RM Intel - Cross sell outreach cheatsheet |
| Proposal | *   Investment Advsior - Chatbot to tailer made the needs<br>    <br>*   Investment Advsior - Personalized Investment Proposal<br>    <br>*   Investment Advsior - Portfolio health check and growth opportunity analysis<br>    <br>*   Investment Advsior - Scenario Analysis |
| Closing | *   Request for Quote (external)<br>    <br>*   Investment Advsior - Term sheet generation<br>    <br>*   Term sheet reconciliation with couterparty |
| Retention and upsell | *   Investment Advsior - Portfolio health check and growth opportunity analysis<br>    <br>*   Investment Advsior - Upcoming fund release finder <br>    <br>*   RM Intel - Asset outflow prediction<br>    <br>*   RM Intel - Relationship decay report |

## Out of scope items

The following times are out-of-scope as they are either covered in an existing module or they are low value for license sales.

*   Most back office operation such as accounting and trade reconcilation
    
*   RFQ
    

# Lead generation

## Three sources of leads

There’re three sources of lead

1.  Buyer driven.  An investor comes in who are looking for an investment opportunity.
    
2.  Product driven.  There’re some selective products that looks excellent in terms of risk return that require investor.  Typical investor are buying similar before and have cash in coming 3m.
    
3.  Hidden needs.  Investor with plenty of cash of equivalent sitting idle, having future expenses to meet.  For example, suggest Mortgage with private credit or high yield bond.  Education funding, etc.
    

This is summarized as below with the proposed product feature

| Leads | Classification | Product features |
| --- | --- | --- |
| Buyer driven | Investor actively looking for opportunity.  Possibly message RM for needs | *   Client pre-meeting cheatsheet<br>    <br>*   Portfolio health check and growth opportunity analysis<br>    <br>*   Chatbot to tailer made the needs |
| Product driven | Identify potential opportunity starting from a set of hot-selling product. | *   Product investor matcher<br>    <br>*   RM cross sell outreach cheatsheet |
| Hidden needs | Those have hidden needs such as <br>*   Cash sitting idle<br>    <br>*   Have capital to release in next 3m<br>    <br>*   Have children that needs education fund<br>    <br>*   To retire in 10 year<br>    <br>*   High paid individual need to hedge their career/business | *   Hidden needs finder<br>    <br>*   Wallet Inflow Forecast<br>    <br>*   Potential risk reassessment<br>    <br>*   RM cross sell outreach cheatsheet |

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

A lead score will be given for each client in the list

**Annuity Match:** High-fit for age 45-55 cohort with children.

## Hidden needs finder

A lead score (1-5) will be given for each client in the list

## Wallet Inflow Forecast

The feature is to screen out any client who will have upcoming funding inflow so that RM may introduce a portfolio rebalance meeting to find any cross sell opportunity

### Portfolio expiry report 

The screener will filter out client that will have funds released for investment in near future (default 3m that could be adjusted on screen)

*   SP/Note/Bond matured
    
*   Option, in particular sell call will be exercised.
    
*   Potential Knock out 
    
*   Potential barrier breached.
    

### Potential KO/barrier breach report 

*   Back test with recent three months?
    
*   Model calibrated to BS using 3m risk free rate
    

### Liquidity Ladder

*   Liquidity Ladder
    

# RM intel

There are a two types of reports that will be often used.

1.  RM cheat sheet - Prepare the RM/IC to talk to the client.
    
2.  Client advisory - Explain to client the product and why it fits to his portfolio.
    

## Client pre-meeting cheatsheet (for RM)

Talking points to client target to RM.  The report shall covers the following content

1.  Personal deomgraphic (marital status, age, etc.)
    
2.  Potential product and the talking points.  For the seeker, we may want to include product of higher risk and need to initiate new risk assessment process to close the deal.
    
3.  Client current holdings
    
4.  Expected cash to release in coming 6m
    
5.  Summary of previous call/meeting minute and recent bought
    
6.  Key questions to further qualify the prospect
    
7.  Lead score - the probability of closing for this client
    

## Cross sell outreach cheatsheet (for RM)

Talking points to client for RM to call for a meeting.  The report shall covers the following content

1.  Hidden investment needs - education fee, retirement, mortgage downpayment, idle cash, etc.
    
2.  Personal deomgraphic (marital status, age, etc.)
    
3.  Potential product and the talking points.  For the seeker, we may want to include product of higher risk and need to initiate new risk assessment process to close the deal.  
    
4.  Key questions to further qualify the prospect
    

## Asset outflow prediction

*    Clients showing signs of consolidating assets away from your PB (e.g., gradual reduction in AUM, transfer requests, increased cash drag without reinvestment).
    
    ## Relationship decay report
    
*   Declining meeting frequency, unreturned RM calls, or lack of engagement with client advisory materials.
    
*   Which high-value clients have had no meaningful contact in >60 days.
    

# Investment Advisor

## Personalized investment proposal (for Client)

1.  Summary of product benefit and why
    
    1.  Stable cashflow, capture AI gain, hedging the current career position (tech people choose non tech investment)
        
2.  Product characteristics such as maturity, coupon rate, risk
    
3.  Scenario analysis that includes return, cashflow.  
    
    1.  Product alone
        
    2.  Portfolio level (optional)
        

## Portfolio health check & growth opportunity (for Client)

1.  Current portfolio characteristics - pros and cons 
    
2.  PnL
    
3.  Concentration analysis, currency, asset classes, region, industry
    
4.  Suggest to change or rebalance of the current portfolio and why
    
5.  Addition product characteristics, if any, such as maturity, coupon rate, risk
    
6.  Scenario analysis that includes return, cashflow.  
    
    1.  Product alone
        
    2.  Portfolio level
        

## Scenario analysis

Based on model with model with correct distribution.  Could use BS for at the very beginning with certain simplified assumptions.

*   Best scenario
    
*   Expected scenario
    
*   Worst scenario
    
*   KO probability
    

Later to move to SVCJ for Stock/bitcoin?

## Termsheet

This generates a deteail termsheet to confirm trade execution.  This is different from the product under personalized invesmtent proposal which only outlines the brief term of the product.  Term sheet will have exact date and other term detail (call condition), and also risk disclosure.

**NLP generates term sheet**

*   Include term and all above discussion
    

## Investment chatbot

Basically this js a prompt-to-investment advisor that could be operated by the investor alone or with the guidance of a financial advisor 

There are two modes of operation

*   Get a final report of the recommendation based on AI based on a aged profile 
    
*   Have a workflow to ask a few questions or preferences in market, geographical underlying
    

# Screen

┌─────────────────────────────────────────────────────────────────────────────┐

│ \[LOGO\]  PB Investment Advisor | Main Dashboard                             │

│                                                                             │

│ \[RM: David Wong | Relationship Manager\]  \[🔍 Search Client/Lead\]  \[🔔 7 Alerts\]  \[⚙️ Settings\] \[Logout\] │

├─────────────────────────────────────────────────────────────────────────────┤

│ \[ Dashboard \] \[ Leads \] \[ Clients \] \[ Proposals \] \[ Reports \] \[ Tools \]     │ ← Main Nav

├─────────────────────────────────────────────────────────────────────────────┤

│                                                                             │

│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐    │

│  │ Active Leads       │  │ Conversion Funnel  │  │ Upcoming Events    │    │

│  │ 12 Total           │  │ Lead→Qual: 72%     │  │ Expiries: 5        │    │

│  │ High Priority: 4   │  │ Qual→Prop: 58%     │  │ KO Risk: 2        │    │

│  └────────────────────┘  └────────────────────┘  └────────────────────┘    │

│                                                                             │

│  ┌───────────────────────────────────────────────────────────────────────┐  │

│  │ Quick Actions                                                         │  │

│  │ \[+ New Proposal\]  \[Generate Cheatsheet\]  \[Term Sheet\]  \[AI Chatbot\]    │  │

│  └───────────────────────────────────────────────────────────────────────┘  │

│                                                                             │

│  ┌───────────────────────────────────────────────────────────────────────┐  │

│  │ My Priority Clients & Leads                                          │  │

│  │ ┌───────────────────────────────────────────────────────────────────┐ │  │

│  │ │ ID   Name          Net Worth   Lead Score   Next Action           │ │  │

│  │ ├───────────────────────────────────────────────────────────────────┤ │  │

│  │ │ C001 John Smith    $4.8M       92%         Portfolio Expiry (14d) │ │  │

│  │ │ C002 Sarah Lee     $6.2M       87%         Hidden Need: Education │ │  │

│  │ │ C003 Michael Chen  $3.5M       78%         Risk Reassessment      │ │  │

│  │ └───────────────────────────────────────────────────────────────────┘ │  │

│  └───────────────────────────────────────────────────────────────────────┘  │

│                                                                             │

│  ┌───────────────────────────────────────────────────────────────────────┐  │

│  │ AI Insights (Auto-Generated)                                         │  │

│  │ • 3 clients with idle cash > $500k → cross-sell opportunity           │  │

│  │ • 2 clients showing panic selling behavior → review risk profile     │  │

│  │ • 8 high-net-worth clients no contact > 60d → retention alert         │  │

│  └───────────────────────────────────────────────────────────────────────┘  │

│                                                                             │

├─────────────────────────────────────────────────────────────────────────────┤

│ \[Compliance Audit Trail\] \[Help\] \[Data Last Refreshed: 2026-04-06 10:25\]     │

└─────────────────────────────────────────────────────────────────────────────┘

# Data needed for LLM integration

The data below preferably feed by tool via MCP, or RAG if they're provided as document (e.g., a research report)

## Data Entities

Below is the major data entities required for the LLM integration.  Most of them could be made optional but fewer data may result in weaker product suggestion.

| Entity | Remarks (purpose + up to 6 fields) |
| --- | --- |
| **Client Profile** | Core client identity for personalization and targeting. _Fields:_ Client\_ID, Age, Marital Status, Children, Occupation, Net Worth |
| **Client Risk Profile (current + History)** | Tracks risk tolerance over time for reassessment triggers. _Fields:_ Client\_ID, Assessment Date, Risk Tolerance Score, Risk Capacity Score, Behavioral Flags |
| **Tax Status** | Enables tax-efficient product selection. _Fields:_Client\_ID, Tax Jurisdiction, FATCA Status, Tax Bracket |
| **Demographics** | Life-stage attributes for hidden needs (education, retirement). _Fields:_ Client\_ID, Age, Marital Status, Children Count, Retirement Age, Homeownership |
| **Position Holding** | Client's current holdings, pre-aggregated by instrument. _Fields:_ Client\_ID, Instrument\_ID, Quantity, Current Value, PnL, Maturity Date |
| **Transaction History** | Cash/trade flow for behavior detection (panic selling). _Fields:_ Client\_ID, Date, Type (Buy/Sell/Deposit), Amount, Instrument\_ID |
| **Product Catalog** | Master product list with risk/return ratings. _Fields:_Instrument\_ID, Asset Class, Volatility, Maturity, Risk Rating, Barrier/KO Level |
| **Lead** | Tracks sales opportunities from generation to close. _Fields:_ Lead\_ID, Client\_ID, RM\_ID, Type, Status, Lead Score |
| **Interaction** | Records RM-client touchpoints for cheatsheets. _Fields:_Client\_ID, RM\_ID, Date, Sentiment, Summary, Artifact\_Ref |
| **Conversation History** | Chatbot session state for multi-step workflows. _Fields:_Session\_ID, Client\_ID, Step, User Message, AI Response, Derived Preferences |
| Market Data | *   Prices<br>    <br>*   Yield curves<br>    <br>*   FX rates<br>    <br>*   Volatility<br>    <br>*   Benchmarks |

## Demographic 

in particular the taxation consideration

## Client profile 

*   Legal name
    
*   Entity structure
    
*   Tax residency
    
*   Risk profile
    
*   Investment mandate
    
*   KYC documents
    
*   FATCA/CRS status?
    

## Transaction Data

*   Trade date
    
*   Value date
    
*   Counterparty
    
*   Broker
    
*   Fee
    
*   Commission
    
*   FX rate
    

---

## Position Holding

*   Asset class
    
*   ISIN
    
*   Quantity
    
*   Market value
    
*   Cost basis
    
*   Currency
    
*   Settlement status
    
*   PnL from import (realized and unrealzied)?
    

---

## Product Catalog

This should include the rating of the product in the four dimensions.

*   Expected return
    
*   Volatility
    
*   Certainty of return at maturity
    
*   Liqudity
    

## Interaction Data

*   Meeting notes
    
*   Tasks
    
*   Approvals
    
*   Compliance events
    

# User Roles and Permissions

| Role | Description | Access Level |
| --- | --- | --- |
| **Relationship Manager (RM)** | Primary user; manages client relationships and sales. | View assigned clients, generate proposals, trigger outreach. |
| **Investment Counselor (IC)** | Technical specialist; assists RM with complex portfolios. | View all clients, modify model assumptions, validate proposals. |
| **Compliance Officer** | Oversight role; ensures suitability and regulatory alignment. | View audit trails, suitability reports, and flagged mismatches. |
| **Senior Management** | Business head; monitors performance and conversion. | View aggregated analytics and RM productivity reports. |

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
    
*   Tool/RAG
    

## Shall we persist below?

## 📥 D. Credit Data

*   Facility limit
    
*   Outstanding
    
*   Collateral value
    
*   Haircut
    
*   LTV
    

# Additional idea for AI assistant

1.  Term sheet reconciliation including OCR
    
2.  Market data cleansing
    
3.  Tax optimization
    
4.  Model validation
    
5.  Marketing campaign - estate planning, children education, retirement, etc.
    

# Reference

## Terminology

| Term | Definition | Example |
| --- | --- | --- |
| **Product / Instrument Type** | The _template_ or _class_ of financial instrument | Interest Rate Swap, Equity Option, Bond, Structured Note |
| **Product / Instrument**(sometimes "Security Master") | The _specific issuance_ with fixed terms | USD 5% 1/2/2035 Fix-Float Swap (a specific tradeable line) |
| **Position / Holding** | A client's _ownership_ of a specific instrument, including quantity, purchase date, cost basis | Client A: 10mm notional of that swap, bought 2024-01-15 |