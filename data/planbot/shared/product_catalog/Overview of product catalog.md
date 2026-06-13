# Overview

Product data is sourced from 
- demo-market-1Jun26.csv, which contains the master list of available instruments, historical performance metrics, and risk classifications. 
- Sector ETF that that gives the product with bank's preference
    - selected_etf.csv
- Structured products
    - CMT_note.md

To facilitate high-precision matching, each product is scored across four dimensions:

1. Risk Rating (Mandatory Constraint)
Scale: 1 (Lowest) to 5 (Highest).

Protocol: This acts as a hard filter. A product is only eligible for a portfolio suggestion if its Risk Rating is less than or equal to the client’s assessed risk tolerance. No exceptions are permitted, ensuring regulatory and strategic harmony.

2. Expected Return

Definition: Represents annualized total return (annualized yield (not the actual price return) or capital appreciation)

4. Liquidity
Scale: 1 (Illiquid/Locked) to 5 (Daily Liquidity).

Definition: Reflects the ease of exiting a position at the current market price without significant penalty or delay.

Score 5: Exchange-traded equities and daily-dealing Mutual Funds.

Score 2-3: Products with structural barriers, such as annuities or structured product, where early unwinding incurs significant surrender charges or exit fees.