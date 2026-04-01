# Overview of Investment Advisor

# Introduction

The major objective of this tool is to help Private Bankers (PB) close more deals by streamlining the entire sales cycle from lead generation to retention. This includes:

* **Lead Generation**: Automatically identify prospects with hidden needs, upcoming liquidity events, or product-fit characteristics
* **Time Efficiency**: Eliminate RM time spent consolidating client profiles from disparate systems; AI-generated talking points reduce meeting preparation time
* **Proposal Quality**: Provide personalized investment proposals, portfolio health checks, and scenario analyses
* **Closing Support**: Generate term sheets and reconcile counterparty documents
* **Retention & Upsell**: Monitor portfolio events (expirations, knock-out risks, barrier breaches) to trigger proactive outreach

## Selling Cycle and Product Features

| Stage | Product Features | Key Artifacts |
| --- | --- | --- |
| Lead Generation | Lead identification and prioritization | • Product-Investor Matcher Report<br>• Hidden Needs Finder Report<br>• Upcoming Fund Release Finder Report<br>• Potential Risk Reassessment Report |
| Qualifying | Client profile consolidation and meeting preparation | • Client 360 Cheatsheet<br>• RM Cross-Sell Outreach Cheatsheet |
| Proposal | Tailored investment recommendations | • Personalized Investment Proposal<br>• Portfolio Health Check & Growth Opportunity Analysis<br>• Scenario Analysis Report<br>• AI Chatbot for Interactive Needs Discovery |
| Closing | Documentation generation and reconciliation | • Term Sheet Generation<br>• Term Sheet Reconciliation Report |
| Retention & Upsell | Proactive monitoring and re-engagement | • Portfolio Expiry Report<br>• Potential KO/Barrier Breach Report<br>• Portfolio Health Check & Growth Opportunity Analysis (periodic) |

## Out of Scope Items

The following items are out-of-scope:
* Back-office operations (accounting, trade reconciliation)
* RFQ execution (external system integration)
* Real-time trading execution
* Compliance and regulatory reporting (assumed handled by existing systems)

---

# Lead Generation Workflow

## Three Sources of Leads

| Lead Type | Classification | Product Features | Key Artifacts |
| --- | --- | --- | --- |
| **Buyer Driven** | Investor actively seeking opportunities; may contact RM directly | • Client 360 Cheatsheet<br>• Portfolio Health Check<br>• AI Chatbot | • Client 360 Cheatsheet<br>• Personalized Investment Proposal |
| **Product Driven** | Start with high-performing products and identify suitable investors | • Product-Investor Matcher<br>• RM Cross-Sell Outreach Cheatsheet | • Product-Investor Matcher Report<br>• RM Cross-Sell Outreach Cheatsheet |
| **Hidden Needs** | Investors with unaddressed needs:<br>• Idle cash<br>• Upcoming liquidity events<br>• Life events (education, retirement)<br>• Career/business hedging needs | • Hidden Needs Finder<br>• Upcoming Fund Release Finder<br>• Potential Risk Reassessment<br>• RM Cross-Sell Outreach Cheatsheet | • Hidden Needs Finder Report<br>• Upcoming Fund Release Finder Report<br>• Potential Risk Reassessment Report<br>• RM Cross-Sell Outreach Cheatsheet |

---

# Lead Generation Artifacts

## Product-Investor Matcher Report

**Purpose**: Identify investors who are best suited for a specific high-performing or strategic product based on their risk profile, investment history, and liquidity.

**Benefit**: Enables RMs to proactively reach out to qualified prospects with a compelling product story, increasing conversion rates.

**Typical User Action**: 
* Call or email selected investors to introduce the product
* Schedule meetings with top-matched prospects

**Data Included**:
* Investor name, contact information, and demographic summary
* Current portfolio composition and risk profile
* Investment history (similar products purchased)
* Available liquidity (current and upcoming in next 3 months)
* Match score (0-100) with explanation
* Suggested talking points for outreach

**Key Filters/Criteria**:
* Product characteristics (asset class, risk level, minimum investment, maturity)
* Investor risk tolerance and investment objectives
* Historical purchase behavior (similar products)
* Available cash or upcoming liquidity events (next 3 months)
* Regulatory constraints (accredited investor status, jurisdiction)

---

## Hidden Needs Finder Report

**Purpose**: Identify investors with unaddressed financial needs based on life stage, demographics, and portfolio composition.

**Benefit**: Uncovers cross-sell and upsell opportunities that investors may not have explicitly requested, expanding the addressable product set.

**Typical User Action**:
* Initiate outreach to discuss life goals (education funding, retirement planning, estate planning)
* Propose products that address identified needs (annuities, structured notes, bonds)

**Data Included**:
* Investor name and demographic profile (age, marital status, children, occupation)
* Identified hidden needs with supporting evidence:
  * Idle cash exceeding threshold (e.g., >20% of portfolio in cash/money market)
  * Children aged 10-18 (education funding need)
  * Age 50-60 (retirement planning need)
  * High concentration in employer stock (hedging need)
  * Upcoming major expenses (home purchase, business investment)
* Current portfolio composition
* Suggested product categories to address needs
* Talking points for initial conversation

**Key Filters/Criteria**:
* Demographic triggers (age ranges, family status, occupation)
* Portfolio composition thresholds (idle cash %, concentration risk)
* Life event indicators (from CRM notes, transaction history)
* Investment behavior patterns (conservative investors with high net worth)

---

## Upcoming Fund Release Finder Report

**Purpose**: Identify investors who will have funds available for reinvestment in the near term due to maturity, exercise, or knock-out events.

**Benefit**: Enables proactive outreach before funds are released, capturing reinvestment opportunities before competitors.

**Typical User Action**:
* Schedule pre-maturity meetings to discuss reinvestment options
* Prepare personalized investment proposals for anticipated liquidity

**Data Included**:
* Investor name and contact information
* List of upcoming liquidity events:
  * Structured products, notes, bonds maturing (with maturity date and amount)
  * Options likely to be exercised (sell calls with high probability)
  * Knock-out products with high KO probability (with estimated date and amount)
  * Barrier breach events (with estimated date and amount)
* Total expected liquidity by month (next 3-6 months)
* Current portfolio composition
* Suggested reinvestment products based on risk profile

**Key Filters/Criteria**:
* Time horizon (default: next 3 months; adjustable to 6 or 12 months)
* Minimum liquidity amount threshold
* Product types: maturing bonds/notes, options near expiry, structured products with KO risk
* KO probability threshold (e.g., >30% probability in next 3 months)
* Barrier breach probability threshold

**Knock-Out Probability Calculation**:
* Model: Black-Scholes calibrated using 3-month risk-free rate
* Inputs: Current underlying price, barrier level, volatility (historical 3-month), time to maturity
* Backtesting: Validate model accuracy using recent 3-month historical data

---

## Potential Risk Reassessment Report

**Purpose**: Identify investors whose stated risk tolerance may not align with their actual behavior, portfolio composition, or financial capacity.

**Benefit**: Opens opportunities to expand the product universe by helping investors reassess and potentially increase their risk tolerance.

**Typical User Action**:
* Schedule risk reassessment meeting
* Propose higher-return products if reassessment confirms higher risk tolerance

**Data Included**:
* Investor name and current risk profile
* Mismatch indicators with supporting evidence:

| Mismatch Type | AI Signal | Hidden Reality | Suggested Action |
| --- | --- | --- | --- |
| **Panic Seller** | Trading frequency spikes during market dips | Low volatility tolerance | Reassess to lower risk; propose capital-protected products |
| **Concentrator** | Single stock >20% of NAV + overconfident language in notes | Low certainty tolerance | Reassess to lower risk; propose diversification |
| **Yield Chaser** | High-yield assets that correlate with S&P 500 | False certainty (hidden equity risk) | Educate on true risk; propose genuinely diversified income products |
| **Lifestyle Laggard** | Spending rate > portfolio growth rate | Insufficient return for goals | Reassess to higher risk; propose growth-oriented products |
| **Conservative Paradox** | High net worth + high income but >50% in cash/fixed deposits | Risk capacity exceeds risk tolerance | Reassess to higher risk; propose balanced or growth portfolios |

* Current portfolio composition
* Demographic and financial capacity indicators (net worth, income, age)
* Suggested talking points for reassessment conversation

**Key Filters/Criteria**:
* Portfolio composition thresholds (e.g., cash >50%, single stock >20%)
* Trading behavior patterns (frequency, timing relative to market events)
* Spending vs. portfolio growth rate
* Net worth and income levels vs. risk profile
* NLP analysis of meeting notes for overconfidence or anxiety indicators

---

# Qualifying Workflow Artifacts

## Client 360 Cheatsheet (for RM)

**Purpose**: Provide RMs with a comprehensive, consolidated view of the client to prepare for meetings or calls efficiently.

**Benefit**: Eliminates time spent gathering information from multiple systems; ensures RMs are well-prepared with relevant talking points and questions.

**Typical User Action**:
* Review before client meeting or call
* Use talking points to guide conversation
* Ask key qualifying questions to uncover needs

**Data Included**:
* **Personal Demographics**: Age, marital status, number of children, occupation, location
* **Current Holdings**: Portfolio composition with asset allocation breakdown
* **Expected Cash Release**: Upcoming liquidity events in next 6 months (maturity, exercise, KO)
* **Recent Activity**: Summary of last 3 meetings/calls (from CRM notes) and recent purchases
* **Potential Products**: 3-5 recommended products with brief talking points for each:
  * Why it fits the client's profile
  * Key benefits (income, growth, diversification, hedging)
  * Risk considerations
* **Risk Reassessment Flag**: If applicable, note mismatch and suggested approach
* **Key Qualifying Questions**: 5-7 questions to further understand client needs and preferences

**Key Filters/Criteria**:
* Client ID or name
* Data freshness: Pull latest data from all integrated systems (CRM, portfolio management, transaction history)

---

## RM Cross-Sell Outreach Cheatsheet (for RM)

**Purpose**: Equip RMs with targeted talking points for proactive outreach calls to clients identified through lead generation reports.

**Benefit**: Increases success rate of cold/warm outreach by providing personalized, relevant conversation starters.

**Typical User Action**:
* Call or email client to request a meeting
* Use talking points to explain the reason for outreach
* Ask key questions to confirm interest and qualify further

**Data Included**:
* **Hidden Investment Needs**: Specific needs identified (education funding, retirement planning, idle cash, mortgage down payment, career hedging)
* **Personal Demographics**: Age, marital status, children, occupation
* **Potential Products**: 2-3 recommended products with talking points:
  * How the product addresses the identified need
  * Key benefits and risk considerations
  * Why now is a good time (e.g., upcoming liquidity, market conditions)
* **Risk Reassessment Note**: If higher-risk products are suggested, note the need to initiate risk reassessment
* **Key Qualifying Questions**: 3-5 questions to confirm the need and gauge interest

**Key Filters/Criteria**:
* Lead source (Hidden Needs Finder, Upcoming Fund Release Finder, Product-Investor Matcher, Risk Reassessment)
* Client ID or name
* Specific need or product focus

---

# Proposal Workflow Artifacts

## Personalized Investment Proposal (for Client)

**Purpose**: Provide clients with a clear, compelling case for a specific investment product tailored to their profile and goals.

**Benefit**: Increases client confidence and understanding, accelerating the decision-making process.

**Typical User Action** (by RM):
* Present proposal during client meeting
* Walk through scenario analysis to address client questions
* Request client decision or next steps

**Typical User Action** (by Client):
* Review proposal independently or with RM
* Discuss with family or advisors
* Make investment decision

**Data Included**:
* **Executive Summary**: 
  * Product name and key characteristics (asset class, maturity, coupon/yield, risk level)
  * Why this product is recommended (stable cash flow, growth potential, hedging, diversification)
  * Expected outcome (return, income, risk mitigation)
* **Product Characteristics**:
  * Underlying asset(s)
  * Maturity date
  * Coupon rate or yield
  * Risk factors (market risk, credit risk, liquidity risk, knock-out/barrier risk)
  * Minimum investment
* **Scenario Analysis** (Product Alone):
  * Best case: Return, cash flow, final value
  * Expected case: Return, cash flow, final value
  * Worst case: Return, cash flow, final value
  * Knock-out probability (if applicable)
* **Scenario Analysis** (Portfolio Level - Optional):
  * Current portfolio vs. portfolio with new product
  * Impact on overall return, volatility, and diversification
  * Cash flow projection over time
* **Why This Product Fits You**:
  * Alignment with stated goals (income, growth, capital preservation)
  * Hedging considerations (e.g., tech professional investing in non-tech assets)
  * Diversification benefits
  * Tax considerations (if applicable)
* **Next Steps**: Instructions for proceeding (sign term sheet, transfer funds, etc.)

**Key Filters/Criteria**:
* Client ID
* Product ID
* Include portfolio-level analysis: Yes/No
* Scenario assumptions (market conditions, volatility, interest rates)

---

## Portfolio Health Check & Growth Opportunity Analysis (for Client)

**Purpose**: Provide clients with an objective assessment of their current portfolio and actionable recommendations for improvement.

**Benefit**: Builds trust by demonstrating RM expertise; uncovers rebalancing and upsell opportunities.

**Typical User Action** (by RM):
* Present during periodic review meetings (quarterly, annually)
* Use recommendations to propose new products or rebalancing

**Typical User Action** (by Client):
* Review portfolio assessment
* Discuss recommendations with RM
* Approve rebalancing or new investments

**Data Included**:
* **Current Portfolio Characteristics**:
  * Asset allocation breakdown (equities, fixed income, alternatives, cash)
  * Geographic and sector diversification
  * Risk metrics (volatility, Sharpe ratio, maximum drawdown)
  * Liquidity profile
  * Concentration risks (single stock, single sector, single geography)
* **Strengths**: What the portfolio does well (e.g., stable income, low volatility, good diversification)
* **Weaknesses**: Areas of concern (e.g., excessive cash, concentration risk, insufficient growth, duration mismatch with liabilities)
* **Recommendations**:
  * Rebalancing suggestions (reduce/increase exposure to specific asset classes)
  * New products to add (with rationale)
  * Products to exit or reduce (with rationale)
* **Proposed Product Characteristics** (if adding new products):
  * Product name, asset class, maturity, coupon/yield, risk level
  * How it addresses portfolio weaknesses
* **Scenario Analysis** (Portfolio Level):
  * Current portfolio performance projection
  * Recommended portfolio performance projection
  * Comparison of return, volatility, and cash flow
  * Best, expected, and worst-case scenarios for recommended portfolio
* **Action Plan**: Prioritized steps to implement recommendations

**Key Filters/Criteria**:
* Client ID
* Portfolio snapshot date
* Benchmark for comparison (e.g., balanced index, client's stated goals)
* Scenario assumptions (market conditions, time horizon)

---

## Scenario Analysis Report

**Purpose**: Provide detailed quantitative analysis of investment outcomes under different market conditions.

**Benefit**: Helps clients and RMs understand potential risks and rewards, supporting informed decision-making.

**Typical User Action**:
* Review during proposal presentation
* Use to address client concerns about downside risk
* Compare multiple products or portfolio configurations

**Data Included**:
* **Product or Portfolio Summary**: Name, composition, key characteristics
* **Scenario Definitions**:
  * Best case: Assumptions (e.g., underlying asset +20%, no knock-out)
  * Expected case: Assumptions (e.g., underlying asset +5%, historical volatility)
  * Worst case: Assumptions (e.g., underlying asset -20%, barrier breach)
* **Outcomes for Each Scenario**:
  * Total return (%)
  * Final portfolio value
  * Cash flow schedule (coupons, dividends, principal repayment)
  * Knock-out probability (if applicable)
  * Time to knock-out (if applicable)
* **Portfolio-Level Impact** (if applicable):
  * Current portfolio vs. portfolio with new product
  * Change in expected return, volatility, Sharpe ratio
  * Diversification benefit

**Key Filters/Criteria**:
* Product ID or portfolio ID
* Scenario assumptions (market return, volatility, interest rates, credit spreads)
* Time horizon
* Include portfolio-level analysis: Yes/No

**Modeling Approach**:
* **Initial Implementation**: Black-Scholes model with simplified assumptions (constant volatility, log-normal returns)
* **Future Enhancement**: SVCJ (Stochastic Volatility with Correlated Jumps) model for equities and Bitcoin
* **Calibration**: Use 3-month risk-free rate and historical volatility
* **Backtesting**: Validate model accuracy using recent 3-month historical data

---

## AI Chatbot for Interactive Needs Discovery

**Purpose**: Enable investors to explore investment options interactively, either independently or with RM guidance, through a conversational interface.

**Benefit**: Provides 24/7 access to personalized investment advice; reduces RM time for initial needs discovery; improves client engagement.

**Typical User Action** (by Client):
* Access chatbot via web or mobile app
* Answer questions about goals, risk tolerance, preferences
* Review AI-generated recommendations
* Request RM follow-up for detailed proposal

**Typical User Action** (by RM):
* Use chatbot during client meeting to interactively explore options
* Review chatbot conversation history to understand client preferences
* Generate formal proposal based on chatbot recommendations

**Functionality**:
* **Mode 1: Quick Recommendation**
  * Client provides basic inputs (investment amount, time horizon, risk tolerance)
  * AI generates immediate product recommendations with brief rationale
* **Mode 2: Guided Discovery**
  * AI asks a series of questions to understand:
    * Investment goals (income, growth, capital preservation, hedging)
    * Risk tolerance and past investment experience
    * Preferences (asset class, geography, sector, ESG considerations)
    * Liquidity needs and time horizon
    * Tax considerations
  * AI generates detailed recommendations with scenario analysis
* **Mode 3: RM-Assisted**
  * RM and client use chatbot together during meeting
  * RM can override or refine AI suggestions in real-time
  * Conversation history saved to CRM

**Data Included** (in chatbot output):
* Recommended products (ranked by fit score)
* Brief rationale for each recommendation
* Key product characteristics (maturity, yield, risk)
* Next steps (request formal proposal, schedule RM meeting)

**Key Filters/Criteria**:
* Client profile (if logged in) or anonymous inputs
* Product universe (filtered by regulatory constraints, minimum investment, availability)
* AI model: Fine-tuned LLM with investment advisory knowledge and firm's product catalog

---

# Closing Workflow Artifacts

## Term Sheet Generation

**Purpose**: Automatically generate legally compliant term sheets for approved investment products, reducing manual effort and errors.

**Benefit**: Accelerates closing process; ensures consistency and accuracy; reduces legal review time.

**Typical User Action** (by RM):
* Select product and client
* Review and approve AI-generated term sheet
* Send to client for signature

**Typical User Action** (by Client):
* Review term sheet
* Sign electronically or return signed copy

**Data Included**:
* **Product Details**: Name, ISIN, underlying asset(s), issuer, maturity date
* **Economic Terms**: Notional amount, coupon rate, payment frequency, knock-out/barrier levels, participation rate
* **Risk Factors**: Market risk, credit risk, liquidity risk, early termination conditions
* **Legal Terms**: Governing law, jurisdiction, dispute resolution
* **Client Details**: Name, account number, contact information
* **Signatures**: Client and authorized bank representative

**Key Filters/Criteria**:
* Product ID
* Client ID
* Investment amount
* Customization options (if any)
* Template selection (based on product type and jurisdiction)

**NLP Approach**:
* Use pre-approved templates with variable fields
* AI populates fields based on product and client data
* AI flags any non-standard terms for legal review

---

## Term Sheet Reconciliation Report

**Purpose**: Automatically compare term sheets from counterparties (e.g., issuers, brokers) with internal term sheets to identify discrepancies.

**Benefit**: Reduces manual review time; minimizes settlement errors; ensures terms match client expectations.

**Typical User Action** (by RM or Operations):
* Upload counterparty term sheet (PDF or image)
* Review AI-generated reconciliation report
* Resolve discrepancies with counterparty before final execution

**Data Included**:
* **Matched Fields**: List of terms that match between internal and counterparty term sheets
* **Discrepancies**: List of terms that differ, with side-by-side comparison:
  * Field name (e.g., coupon rate, maturity date, knock-out level)
  * Internal value
  * Counterparty value
  * Materiality flag (High, Medium, Low)
* **Missing Fields**: Terms present in one term sheet but not the other
* **Recommendation**: Approve, request clarification, or reject

**Key Filters/Criteria**:
* Internal term sheet ID
* Counterparty term sheet (uploaded file)
* Materiality thresholds (e.g., >0.1% difference in coupon rate is High)

**Technology Approach**:
* OCR to extract text from counterparty term sheet
* NLP to parse and structure extracted data
* Rule-based and AI comparison engine to identify discrepancies

---

# Retention & Upsell Workflow Artifacts

## Portfolio Expiry Report

**Purpose**: Proactively notify RMs of upcoming product maturities to facilitate timely reinvestment discussions.

**Benefit**: Prevents client cash from sitting idle; captures reinvestment opportunities before competitors; demonstrates proactive service.

**Typical User Action** (by RM):
* Review report weekly or monthly
* Schedule pre-maturity meetings with affected clients
* Prepare reinvestment proposals

**Data Included**:
* **Client Name and Contact Information**
* **Expiring Products**:
  * Product name and ID
  * Maturity date
  * Maturity amount (principal + final coupon)
* **Total Expiring Amount by Client** (next 1, 3, 6 months)
* **Client Risk Profile and Investment Objectives**
* **Suggested Reinvestment Products** (based on client profile)
* **Priority Flag**: High (large amount, high-value client), Medium, Low

**Key Filters/Criteria**:
* Time horizon (next 1, 3, 6, or 12 months)
* Minimum maturity amount threshold
* Client segment (e.g., high net worth, mass affluent)
* RM or team assignment

---

## Potential KO/Barrier Breach Report

**Purpose**: Alert RMs to structured products at risk of knock-out or barrier breach, enabling proactive client communication.

**Benefit**: Demonstrates proactive risk management; allows RMs to prepare clients for potential outcomes; identifies reinvestment opportunities.

**Typical User Action** (by RM):
* Review report daily or weekly
* Contact clients with high-risk products to discuss potential outcomes
* Prepare contingency reinvestment proposals

**Data Included**:
* **Client Name and Contact Information**
* **At-Risk Products**:
  * Product name and ID
  * Underlying asset and current price
  * Knock-out or barrier level
  * Distance to knock-out/barrier (% and absolute)
  * Probability of knock-out/barrier breach (next 1 week, 1 month, 3 months)
  * Estimated knock-out date (if probability >50%)
  * Potential payout if knocked out or barrier breached
* **Priority Flag**: High (probability >50% in next month), Medium (probability 30-50%), Low (probability <30%)
* **Suggested Actions**: 
  * Contact client to discuss risk
  * Prepare reinvestment proposal
  * Consider hedging strategies (if available)

**Key Filters/Criteria**:
* Probability threshold (e.g., >30% in next 3 months)
* Time horizon (next 1 week, 1 month, 3 months)
* Product type (autocallables, barrier reverse convertibles, etc.)
* Client segment or RM assignment

**Modeling Approach**:
* Black-Scholes model (initial implementation)
* Calibrated using 3-month historical volatility and risk-free rate
* Backtesting using recent 3-month data to validate accuracy
* Future enhancement: SVCJ model for improved accuracy

---

# Data Requirements for MCP Integration

The following data sources are required for the system to function. Data should be provided via MCP (Model Context Protocol) integration where possible.

## Demographic Data

**Purpose**: Enable personalized recommendations and identify life-stage needs.

**Data Fields**:
* Client ID (unique identifier)
* Age
* Marital status
* Number of children and ages
* Occupation and industry
* Annual income
* Net worth
* Location (country, state/province, city)
* Tax residency and jurisdiction
* Language preference

**Update Frequency**: Quarterly or upon client request

---

## Client Profile Data

**Purpose**: Understand client investment objectives, risk tolerance, and constraints.

**Data Fields**:
* **Current Holdings**:
  * Product ID, name, asset class, quantity, market value, purchase date, maturity date
  * Asset allocation breakdown (equities, fixed income, alternatives, cash)
* **Risk Profile**:
  * Risk tolerance (conservative, moderate, aggressive)
  * Risk capacity (based on net worth, income, time horizon)
  * Investment objectives (income, growth, capital preservation, hedging)
* **Human Capital**:
  * Industry and occupation (for hedging considerations)
  * Income stability (salaried, commissioned, business owner)
  * Career stage (early, mid, late, retired)
* **Future Consumption and Liabilities**:
  * Expected major expenses (education, home purchase, retirement)
  * Liability duration and amount
  * Industry exposure of liabilities (e.g., tuition linked to education sector)
* **Meeting Notes**:
  * Summary of previous meetings and calls (from CRM)
  * Client preferences and concerns
  * Action items and follow-ups

**Update Frequency**: Real-time for holdings; quarterly for profile data; continuous for meeting notes

---

## Product Portfolio Data

**Purpose**: Enable product recommendations and scenario analysis.

**Data Fields**:
* **Product Identification**:
  * Product ID, ISIN, name
  * Asset class (equity, fixed income, structured product, alternative)
  * Underlying asset(s)
  * Issuer and credit rating
* **Economic Terms**:
  * Maturity date
  * Coupon rate or yield
  * Payment frequency
  * Knock-out/barrier levels (if applicable)
  * Participation rate (if applicable)
  * Minimum investment
* **Risk Characteristics** (rated on 0-10 scale or Low/Medium/High):
  * Expected return
  * Volatility
  * Certainty of return at maturity
  * Liquidity
* **Strategic Attributes**:
  * Seller preference (high, medium, low)
  * Inventory availability
  * Margin or commission
* **Marketing Themes**:
  * Income generation
  * Capital preservation
  * Growth potential
  * Hedging (sector, geography, market risk)
  * ESG alignment
* **Regulatory Constraints**:
  * Accredited investor required (Yes/No)
  * Jurisdictions where available

**Update Frequency**: Daily for pricing and availability; weekly for strategic attributes

---

## Market Data

**Purpose**: Support pricing, scenario analysis, and risk calculations.

**Data Fields**:
* Underlying asset prices (equities, indices, commodities, FX, crypto)
* Interest rates (risk-free rates by maturity, credit spreads by rating)
* Volatility (implied and historical)
* Correlations (between asset classes and underlyings)

**Update Frequency**: Real-time or end-of-day

---

## Transaction History

**Purpose**: Understand client behavior and preferences.

**Data Fields**:
* Transaction ID, date, type (buy, sell, maturity)
* Product ID and name
* Quantity and amount
* Client ID

**Update Frequency**: Real-time

---

## CRM Data

**Purpose**: Capture client interactions and preferences.

**Data Fields**:
* Meeting and call notes
* Client preferences (asset class, geography, sector, ESG)
* Relationship strength (A, B, C client)
* RM assignment

**Update Frequency**: Continuous (after each interaction)

---

# Key Assumptions

1. **Data Availability**: All required data sources (demographic, holdings, products, market data, CRM) are accessible via MCP or API integration.
2. **Data Quality**: Client demographic and profile data are accurate and up-to-date; RMs are responsible for updating CRM notes after each interaction.
3. **Regulatory Compliance**: All product recommendations comply with client's risk profile and regulatory constraints (accredited investor status, jurisdiction); compliance checks are performed by existing systems.
4. **Model Accuracy**: Black-Scholes model provides reasonable accuracy for initial implementation; SVCJ model will be implemented in future phase for improved accuracy.
5. **Client Consent**: Clients have consented to AI-driven analysis and recommendations; human RM review and approval required before final proposals are presented.
6. **Technology Stack**: System will use fine-tuned LLMs for NLP tasks (cheatsheet generation, chatbot, term sheet generation); OCR for term sheet reconciliation; quantitative models (BS, SVCJ) for scenario analysis.
7. **Performance**: Reports and cheatsheets can be generated within 30 seconds; chatbot responses within 5 seconds; term sheet generation within 60 seconds.
8. **User Access**: RMs access system via web application; clients access chatbot and proposals via secure client portal.
9. **Integration**: System integrates with existing CRM, portfolio management, and product catalog systems; does not replace these systems.
10. **Pricing and Execution**: System provides recommendations and documentation but does not execute trades; RFQ and trade execution handled by existing systems.

---

# Outstanding Issues

1. **Interest Rate and Commodity Products**: Specification currently focuses on equity and structured products; need to define requirements for interest rate products (bonds, swaps) and commodity products.
2. **Structured Product Integration Deployment**: Need to finalize integration approach with existing structured product pricing and lifecycle management systems.
3. **Pricing Model Selection**: Need to finalize choice between Black-Scholes (simpler, faster) and SVCJ (more accurate, complex) for initial deployment; define timeline for model upgrade.
4. **AI Model Performance**: Need to test AI response quality for cheatsheets, chatbot, and term sheet generation using demo data; establish quality benchmarks.
5. **Constrained Prompt Engineering**: Need to develop and test constrained prompts to ensure AI outputs are compliant, accurate, and consistent with firm's tone and policies.
6. **Demo Data Availability**: Need to create realistic demo data (clients, portfolios, products, market data) for testing and training purposes.
7. **Stress Testing Capability**: Need to define requirements for stress testing scenarios (e.g., 2008 financial crisis, COVID-19 crash); determine if AI should generate scenarios from historical data or use predefined scenarios.
8. **Market Data Cleansing**: Need to define requirements for automated market data cleansing (outlier detection, missing data imputation) if this is in scope.
9. **Model Validation**: Need to define requirements for automated model validation (backtesting, sensitivity analysis) if this is in scope.
10. **Performance and Scalability**: Need to define performance requirements (number of concurrent users, report generation time) and scalability targets (number of clients, products, RMs).
11. **Security and Privacy**: Need to define data security, encryption, and privacy requirements (GDPR, CCPA compliance); role-based access control.
12. **Audit Trail**: Need to define requirements for audit trail (who generated what report when, what data was used, what recommendations were made).
13. **Feedback Loop**: Need to define how RM and client feedback on recommendations will be captured and used to improve AI models.
14. **Multi-Language Support**: Need to define if system should support multiple languages for client-facing outputs (proposals, chatbot).
15. **Mobile Access**: Need to define if mobile app is required for RMs and/or clients, or if responsive web application is sufficient.

---

# Additional Ideas for Future Phases

1. **Term Sheet Reconciliation with OCR**: Automatically extract and compare terms from counterparty term sheets (PDF, image) with internal term sheets.
2. **Market Data Cleansing**: AI-driven detection and correction of market data errors (outliers, missing data, stale prices).
3. **Model Validation**: Automated backtesting and validation of pricing and risk models; generate validation reports for compliance.
4. **Marketing Theme Campaigns**: AI-generated marketing campaigns targeting specific client segments (estate planning, children education, retirement) with personalized content.
5. **Voice-Enabled Chatbot**: Allow clients to interact with chatbot via voice (phone, smart speaker) for accessibility and convenience.
6. **Predictive Client Churn**: Identify clients at risk of moving assets to competitors based on engagement patterns, portfolio performance, and market conditions.
7. **Automated Portfolio Rebalancing**: AI-driven rebalancing recommendations with one-click execution (subject to client approval).
8. **ESG Scoring and Recommendations**: Integrate ESG scores for products and clients; recommend ESG-aligned portfolios.
9. **Tax Optimization**: AI-driven tax-loss harvesting and tax-efficient product recommendations based on client's tax situation.
10. **Behavioral Finance Insights**: Analyze client behavior (panic selling, overconfidence) and provide coaching tips to RMs to improve client outcomes.

---