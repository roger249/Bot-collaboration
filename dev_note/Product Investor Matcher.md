# Product Investor Matcher

# Introduction

The matcher matches the product to the potential investor for a list of products.

There are two outputs from this function.

1.  Ranked potential investors.  List of client and products sorting in the order of "likeness to buy".
    
2.  Client suitability proposal.  This show how the product able to fullfill the identified client needs including scenario analysis.
    

First, we identify any needs of a list of investors.  Then we try to get the product(s) that best fit to the needs.

We would like to introduce a 4-dimensional framework that moves beyond traditional "risk vs. return" charts to provide a comprehensive **Product Suitability Map** for private clients.  This allows us to engineer portfolios that match a client's specific life constraints—ensuring they have the **Return** to grow wealth, the **Volatility** profile they can emotionally stomach, the **Certainty** required for looming liabilities (like taxes or tuition), and the **Liquidity** necessary to pivot when new opportunities arise.

| **Dimension** | **Key Definition** | **The Client’s Core Question** | **The Strategic Objective** |
| --- | --- | --- | --- |
| **Return** | **The Growth Engine:** Total gain from capital appreciation and income. | "How much wealth will this build for my future self?" | **Wealth Accumulation:** Outpacing inflation and lifestyle costs. |
| **Volatility** | **The Emotional Journey:** Short-term price fluctuations and "market noise." | "How much 'wiggle' will I see on my screen this month?" | **Psychological Suitability:**Ensuring the client doesn't panic-sell during dips. |
| **Certainty** | **The Destination Probability:** Likelihood of hitting the target return if held for the full horizon. | "How sure am I that the money will be there when I need it?" | **Time-Horizon Matching:** Trading short-term worry for long-term probability. |
| **Liquidity** | **The Exit Flexibility:** Speed and cost of converting the asset back into cash. | "Can I get my money out tomorrow if I have an emergency?" | **Operational Agility:** Maintaining the ability to pivot or fund liabilities. |

# Product catalog

Each product will be give a rating (1-5) along this four dimension, where 1 is the smallest (or least), and 5 the largest (or most).  

The rating shall be suggested by AI and (optionally) approved by a human before putting in product catalog.

Following table shows some examples of how each asset class in general rated in each dimension.  In reality, each undelrying in an asset class may have different rating.  For example, a fund of money market is very different from a fund targetted to crytocurrency.

Some asset will have more certain outcome for a longer period.  For example, we may not know if the return of a stock fund will outrun a bond, but over a course of 10y, it's very likely the stock fund will have higher return.

| Asset Class | Return | Volatility | Certainty-1y | Certainty-5y | Liquidity | The Advisory Shift |
| --- | --- | --- | --- | --- | --- | --- |
| Money Market Fund | 1 | 1 | 5 | 3 | 5 | Certainty drops as inflation and reinvestment risk grow. |
| Govt. Bonds or high investment grade corporate bond | 2 | 2 | 5 | 5 | 5 | The "Sweet Spot" for medium-term liability matching. |
| Corporate Bonds, including high yield | 3 | 2 | 5 | 4 | 4 | Investment grade: balanced choice for income seekers; moderate certainty decay from 1y to 5y due to credit risk.<br>High yield: "Higher return potential but lower certainty; behaves more like equities in downturns." |
| Public Equities | 5 | 5 | 1 | 4 | 5 | Volatility is high early, but time manufactures certainty. |
| Mutual Funds | 4 | 3 | 2 | 4 | 5 | Diversification accelerates the certainty curve. |
| Gold | 3 | 4 | 2 | 3 | 5 | No maturity or yield means certainty stays low/flat. |
| Structured Notes | 3 | 1 | 3 | 5 | 2 | Engineered to provide high certainty at a fixed date. |
| Anniuty | 3 | 1 | 3 | 4 | 1 |  |

# Needs

For needs, liquidity 1 means it's highly unlikely we need the fund before the planned date.  While 5 means the need may come earlier and needs liquidate the position to get the funding.

| Investment Objective | Typical Horizon (y) | Return (1-5) | Volatility (1-5) | Certainty (1-5) | Liquidity (1-5) | The Strategic Logic |
| --- | --- | --- | --- | --- | --- | --- |
| University Fund / Mortgage down payment | 10–15 | 3 | 2 | 5 | 2 | Horizon-Locked: High certainty is achievable through balanced funds over 10 years. |
| Business Owner | 1–2 | 1 | 1 | 5 | 5 | Operating Buffer: Certainty must be near 100% (Contractual) due to the short horizon. |
| Retirement (Accumulation) | \>7 | 5 | 5 | 5 | 1 | Growth Dominance: Can trade liquidity for returns; time creates the certainty. |
| Retirement (Distribution) | Ongoing | 3 | 2 | 4 | 3 | Cash Flow: Needs a high certainty of yield/coupons to fund monthly life. |
| Estate/Legacy | 30+ | 5 | 5 | 5 | 1 | Multi-Gen: Max volatility is ignored to harvest the highest long-term returns. |
| Emergency Fund | 0.5-1 | 1 | 1 | 5 | 5 | Immediate Need: No time for mean reversion; requires absolute price stability. |
| Tax Liability Reserve/Loan | <1 | 1 | 1 | 5 | 2 | Fixed-date obligation; matching duration is critical, not return. |

"Bridge to social security" is ignored for the moment as we need to account for the difference of each country.

# Product-need matching

The matching will be done by Weighted k‑NN (NumPy/scikit-learn).

We need to put some weight on certain factors.   To avoid over-engineer the parameter, we may just overweight certainty and liquidity as this is the major decision for many needs that has a hard horizon (retirement, univerisity fund).

## Interpolation logic for matching

Given an investment objective with horizon **H years** (between 1 and 5), you can calculate a **Certainty score** for each asset class as:

```plaintext
Certainty(H) = Certainty-1y + (Certainty-5y - Certainty-1y) × (H - 1) / 4
```

### Example:

For **Public Equities** (C1=1, C5=4):

*   At H=1 year → Certainty = 1.0
    
*   At H=3 years → Certainty = 1 + (4-1) × (2/4) = 1 + 3 × 0.5 = **2.5**
    
*   At H=5 years → Certainty = 4.0
    

Anything below 1y we take 1y-certainty.  Similar we take 5y for any needs beyond 5y.  This is a flat extrapolation.

# Ranked potential investor

1.  List of client with proposed product
    

# Client suitability proposal

```plaintext
# Summary
```yaml
instructions: 
  - Executive summary (2-3 sentences)
  - Client's primary goal and constraints
  - Top recommended product and why
  - Key trade-offs accepted (e.g., lower liquidity for higher certainty)
```

# Needs
```yaml
instructions: Tabulate the needs
```

# Suggested Products
```yaml
instructions: |
  For each product (max 3):
  
  1. Product name & asset class
  2. Fit score (e.g., 92/100) or rank
  3. Key metrics (Return, Volatility, Certainty-5y, Liquidity)
  4. Why it matches the need (2-3 sentences)
  5. Specific role in portfolio:
     a. Stable cashflow contribution (% of portfolio)
     b. AI/growth capture mechanism
     c. Career hedge explanation (e.g., "non-tech sector exposure")
  6. Trade-offs / what client gives up
  7. Allocation suggestion (% of total portfolio)
  ```

# Scenario analysis

```yaml
instructions: 
- scenario includes normal, bad, good

- Each scenario includes return projection, cashflow, and account balance by year
- For product that continue investment, include IRR as well for the maturity.
```

# Alternative products to consider

# Risk disclosure

# Reference
```yaml
- Product brochure
- URL,etc.
```
```

We may need to refactor to take out scenario analysis module

# Sample report

Here is a sample output report

# LLM Input

During the prototype phase, 

*   Product table (as JSON or markdown)
    
*   Needs table
    
*   Matching rules (weights, interpolation logic)
    
*   Client profile
    
*   Current holdings
    
*   Specific prompt from RM/client.  This is needed for input additional consideration that revealed during the RM meeting with client