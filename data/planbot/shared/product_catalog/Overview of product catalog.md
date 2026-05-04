# Overview

Product data is sourced from demo-market-quotes.csv, which contains the master list of available instruments, historical performance metrics, and risk classifications. To facilitate high-precision matching, each product is scored across four dimensions:

1. Risk Rating (Mandatory Constraint)
Scale: 1 (Lowest) to 5 (Highest).

Protocol: This acts as a hard filter. A product is only eligible for a portfolio suggestion if its Risk Rating is less than or equal to the client’s assessed risk tolerance. No exceptions are permitted, ensuring regulatory and strategic harmony.

2. Expected Return
Scale: 1 (Capital Preservation) to 5 (Aggressive Growth).

Definition: Represents the projected annualized yield or capital appreciation. A rating of 1 implies a focus on nominal stability, while 5 indicates a high-conviction growth target, typically associated with higher volatility.

3. Certainty (Time-Horizon Probability)
Scale: 1 to 5, assessed across three horizons: 1y, 3y, and 8y.

Definition: Measures the probability of achieving the "Expected Return" over the specific holding period.

Fixed Income Example: A 10-year Treasury bond may score 5/5 for Certainty-8y (low default risk) but 3/5 for Certainty-1y due to mark-to-market sensitivity to interest rate fluctuations.

Equity Example: An index ETF may score 2/5 for Certainty-1y (high short-term variance) but 4/5 for Certainty-8y as historical time-diversification reduces the range of outcomes.

4. Liquidity
Scale: 1 (Illiquid/Locked) to 5 (Daily Liquidity).

Definition: Reflects the ease of exiting a position at the current market price without significant penalty or delay.

Score 5: Exchange-traded equities and daily-dealing Mutual Funds.

Score 2-3: Products with structural barriers, such as annuities or structured producdt, where early unwinding incurs significant surrender charges or exit fees.