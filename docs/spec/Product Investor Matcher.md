# Product Investor Matcher

# Introduction

The matcher matches the product to the potential investor to products.  It takes two inputs.

1.  List of products with the various product characteristics and historical performance
    
2.  List of client with their demograhic and existing holdings.
    

There are two outputs from this function.

1.  Ranked potential investors.  List of client and products sorting in the order of "likeness to buy".
    
2.  Client-Product fitness proposal.  This shows how the product able to fullfill the identified client needs including scenario analysis.
    

This is not a portfolio optimizer — it is a needs-first suitability engine, using liability-driven investing (LDI).

# Product catalog

We would like to introduce a 4-dimensional framework that moves beyond traditional "risk vs. return" charts to provide a comprehensive **Product Suitability Map** for private clients.  This allows us to engineer portfolios that match a client's specific life constraints—ensuring they have the **Return** to grow wealth, the **Volatility** profile they can emotionally stomach, the **Certainty** required for looming liabilities (like taxes or tuition), and the **Liquidity** necessary to pivot when new opportunities arise.

| **Dimension** | **Key Definition** |
| --- | --- |
| Expected Return | Annualized expected return.  This shall be provided by an analyst.  It could also be proxied by the compound annual growth rate of last 3y when analyst estimation is not availabe. |
| Risk Rating | This is a ranking according to the 1y downside deviation from the assets.  <br>*   Rating 1 is principal protected or investment grade bond.<br>    <br>*   While 5 is high volatility stock, and junk bond. |
| Certainty Rating | Certainty of the return.  It's computed by the z-score using the historical CAGR and the historical volatility. |
| Liquidity Rating | **The Exit Flexibility:** Speed and cost of converting the asset back into cash.<br>Exchange traded instrument / Liquid Bond: 5<br>Junk/HY Illiquid Bond/Mutual Fund: 4<br>Structured product/Annuity: 3<br>Real Estate: 2<br>Arts, Private Credit: 1 |

Below sections provide the methodology for the above rating.  For product without historical performance (or one of a kind like structured product), those rating shall be proxy by some means from the bank's analyst.

## Risk rating

Risk rating kind of proxy of principle protected.  It's dervied from the statistical measure "downside deviation" (semi-deviation) that is computed from historical prices.

| **Risk Rating** | **Classification** | **Annualized Downside Deviation** | **Statistical Meaning & Downside Behavior** | **Enriched Product Coverage** |
| --- | --- | --- | --- | --- |
| **1** | Negligible Downside | < 1% | Negative returns are rare and computationally negligible. Price path is virtually linear or contractually guaranteed. | \* Cash, Overnight Deposits.<br>\* Money Market Funds (MMFs).<br>\* Short-term T-Bills / Sovereign Debt held to maturity. |
| **2** | Low Downside Volatility | 1% - 4% | Small, infrequent negative periods. Downside is quickly offset by yields. Capital is highly resilient over short horizons. | \* High-grade, short-duration corporate bonds.<br>\* Investment-Grade Bond Funds / UCITS.<br>\* Capital-Protected Notes / AAA Structured Paper. |
| **3** | Moderate Downside Volatility | 4% - 10% | Standard asymmetrical downside. Typical of diversified market beta where negative quarters are common but bounded. | \* Balanced Allocation Funds (60/40, Multi-Asset).<br>\* Broad Global Equity ETFs (S&P 500, MSCI World).<br>\* Blue-chip dividend equity portfolios. |
| **4** | High Downside Volatility | 10% - 20% | Significant negative asymmetry. Deep, frequent downside monthly returns. Clusters of negative performance can last for quarters. | \* Emerging Market Equities / Sector ETFs (Tech, Biotech).<br>\* High-Yield ("Junk") Bond portfolios.<br>\* Long/Short Equity Hedge Funds.<br>\* Liquid Alternatives with aggressive trading strategies. |
| **5** | Extreme Downside Volatility | \> 20% | Tail-risk dominated. Downside returns are frequent, severe, and highly unconstrained. High probability of permanent capital impairment. | \* Cryptocurrencies and Digital Assets.<br>\* Concentrated single-stock options / Leveraged derivatives.<br>\* Early-stage venture capital assets. |

### Interpreation of downside deviation

For a 5% downside deviation, it means if there's a loss, the loss is within 5% with 52% confidence level, or 52% probabillity the loss is less than 5%.  On the other hand, this could framed as the loss is bounded to 5% for 76% (50+52/2) if win/loss is 50/50.

## Certainty rating

For the sake of simplicity, we assume asset return is distributed normally, and use z score to backout the probability of the asset return higher than a given percentage.  

r is the desired return

mu is the expected return, which is estimated from historical record of bank's discretionary view.

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/Lk3lbmbvbZeEXOm9/img/c9d1c518-7911-4fa5-b9f2-3c9c481fa8b2.png)

*   If your target return is exactly the mean, you have a **50%** chance.
    

*   If your target is 1 standard deviation _below_ the mean, you have an **~84%** chance of hitting it.
    

*   If your target is 1 standard deviation _above_ the mean, you only have a **~16%** chance.
    

| **Rating** | **Certainty Rating** | **Description** | **Z-Score Range** | **Probability** | **Logic for a Downpayment** |
| --- | --- | --- | --- | --- | --- |
| 5 | High Certainty | Rock Solid | Z <= -2.0 | \> 97.5% | The target return is well below the 2 sigma floor. Even a major market crash shouldn't stop you. |
| 4 | Probable | Likely | \-2.0 < Z <= -1.0 | 84% - 97.5% | Target is between the mean and the 2 sigma floor. Very safe, but vulnerable to a "Once-in-a-decade" event. |
| 3 | Neutral | Toss-up | \-1.0 < Z <= 0.5 | 30% - 84% | Your target return is near the expected mean. You are essentially betting on "average" market behavior. |
| 2 | Speculative | Aggressive | 0.5 < Z <= 1.5 | 7% - 30% | You need the market to perform _better_ than average to hit your goal. High risk of a shortfall. |
| 1 | Hope-Based | Moonshot | Z > 1.5 | < 7% | You are relying on a "bull run" tail event. Not suitable for a mandatory liability like a mortgage. |

## Liquidity rating

| **Liquidity Rating** | **Classification** | **Execution Horizon** | **Cost / Friction Penalty** | **Refined Asset Coverage** |
| --- | --- | --- | --- | --- |
| **5** | Instant / Frictionless | Same Day to T+2 | **None to Negligible**<br>_(Tight spreads, minor brokerage)_ | **Exchange-Traded Instruments & Liquid Bonds:** Cash, T-Bills, highly liquid large-cap Equities/ETFs, and Sovereign/G10 Government Bonds. |
| **4** | Standard Managed / Delayed | 1 to 2 Weeks | **Low to Moderate**<br>_(NAV pricing, potential exit loads)_ | **Standard Mutual Funds & High-Yield/Corporate Bonds:** Standard long-only mutual funds (daily liquidity but processing delay), and High-Yield/Corporate bonds that require an OTC (Over-The-Counter) dealer desk to find a buyer. |
| **3** | Lock-up / Structural Gate | 1 Month to 1 Year+ | **High**<br>_(Early withdrawal penalties)_ | **Structured Products & Annuities:** Capital-protected notes, fixed-term structured coupons, and annuities. You _can_ get out, but doing so before maturity violates the contract terms and incurs severe break fees or loss of interest. |
| **2** | Transaction-Dependent | 3 to 6 Months+ | **Very High**<br>_(Commissions, legal fees, taxes)_ | **Physical Real Estate:** Highly illiquid. You are completely dependent on finding a specific buyer, securing bank valuations, and waiting out legal conveyancing timelines.<br>**High-Yield/Distressed OTC Credit**: Junk bonds (HY), distressed debt, and illiquid emerging market corporate bonds.<br>**Traditional Hedge Funds**: Open-ended but with quarterly/semi-annual dealing, often requiring 60-90 days notice + lock-up periods. |
| **1** | **Opaque / Discretionary** | **Years / Undefined** | **Extreme**<br>_(Deep secondary discounts)_ | **Private Credit & Passion Assets (Arts, Wine, Watches):** No public market exists. Private credit funds often have multi-year lock-ups or "gates" that restrict withdrawals during market stress. Art requires auction houses and private broker networks.<br>**Classic Private Markets**: Closed-end Private Equity (PE) and Venture Capital (VC) drawdown funds (7-10 year typical lock-up). |

## Sample product catalog

Following table shows some examples of how each asset class in general rated in each dimension.  In reality, each undelrying in an asset class may have different rating.  For example, a fund of money market is very different from a fund targetted to crytocurrency.

Some asset will have more certain outcome for a longer period.  For example, we may not know if the return of a stock fund will outrun a bond, but over a course of 10y, it's very likely the stock fund will have higher return.

| Asset Class | Expected Return | Downside risk | Certainty-1y | Certainty-5y | Liquidity | The Advisory Shift |
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

| Investment Objective | Typical Horizon (y) | Suggested basic amount | Liquidity (1-5) | The Strategic Logic |
| --- | --- | --- | --- | --- |
| University Fund / Mortgage down payment | 10–15 | 10K | 3 | Horizon-Locked: High certainty is achievable through balanced funds over 10 years. |
| Business Owner | 1–2 | 30K | 5 | Operating Buffer: Certainty must be near 100% (Contractual) due to the short horizon. |
| Retirement (Accumulation) | \>7 | 1M | 1 | Growth Dominance: Can trade liquidity for returns; time creates the certainty. |
| Retirement (Distribution) | Ongoing | 4K/month | 3 | Cash Flow: Needs a high certainty of yield/coupons to fund monthly life. |
| Estate/Legacy | 30+ | 100K | 1 | Multi-Gen: Max volatility is ignored to harvest the highest long-term returns. |
| Emergency Fund | 0.5-1 | 30K | 5 | Immediate Need: No time for mean reversion; requires absolute price stability. |
| Tax Liability Reserve/Loan | <1 | 10K | 2 | Fixed-date obligation; matching duration is critical, not return. |

"Bridge to social security" is ignored for the moment as we need to account for the difference of each country.

# Product matching logic

## Needs investment

Regarding to the financial needs, our aim at the specified timeframe is 

*   Basic - maximize the certainty of the return (or minimize the downside of not achieving it).  Basic is the minimium amount to achieve the needs, education, mortgage downpayment, retirement
    
*   Upside - Once above is guarantee to provide buffer, upside provides a better life style - education aboard, bigger house, more luxury travel during retirement
    

An approach is to divide the investment into two investment - basic and upside.

### Basic

Once we have the required minimium basic amount, we can compute the required return from time horizon.  Then we can choose investment produce > required return and certainty > 4.

If this couldn't be fullfilled, will try to lower certiainty when selecting investment to come up the potential investement.  In this case, the report shall have a remark of the uncertainty.

### Upside

This one we shall choose highest expected return according to the risk appetite of the client 

For needs, liquidity 1 means it's highly unlikely we need the fund before the planned date.  While 5 means the need may come earlier and needs liquidate the position to get the funding.

# Portfolio Review

There are few different origin for a portfolio review

*   General review by LLM
    
*   General policy optimization 
    
*   Needs based
    

## General portfolio optimization

Portfolio rebalance does have the following consideration

*   Optimize on product selection.  Obviously, a product is more superior if it has higher certainty rating or lower risk rating for the same expected return.  This could be a major driver to recommend new product when doing a portfolio review.
    
*   Concentration risk
    
    *   Reduce concentration on asset class, industry, geographical location if possible
        
    *   Reduce the asset correlation
        

*   If funding needs to switch out a product, any new product introduced into the portfolio shall have similar risk rating as the switched-out.  Only except to this is the client confirmed a new need so we can change portfolio characteristics in a more drastic way to fullfill the needs return.
    

## Need based

RM could select one or multiple needs from a list, and let the system to find products to match it.

This will reuse the product investor match by providing the specific needs table as in section 3, which all parameters could be customized.

# Implementation consideration

The following table shows the suggested engine for the matching logic.  When the engine is deterministics, it generate the prompt with the exact product, or investment horizon to the LLM to come up the report.  So the report is always generated by LLM but the details will be dictated by the deterministics logic.

| Area | Engine | Output |
| --- | --- | --- |
| Product rating | Deterministics | Product catalog with proper rating |
| Needs identfication | LLM | No more than 3 needs from the needs table |
| Needs product matching | Deterministics | From the |
| Funding | LLM |  |
| Proposal - scenario analysis | Deterministics | Scenarios?<br>Portfolio calculation? |
| Proposal - alternative suggestion | LLM |  |
| Proposal composition | LLM | Final proposal |

# Sample report

Here is a sample output report

# LLM Input

During the prototype phase, 

*   Product catalog (as CSV)
    
*   Needs table
    
*   Matching rules (weights, interpolation logic)
    
*   Client profile
    
*   Current holdings
    
*   Specific prompt from RM/client.  This is needed for input additional consideration that revealed during the RM meeting with client.