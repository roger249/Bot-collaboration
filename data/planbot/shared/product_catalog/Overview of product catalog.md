# Overview

The product information is listed in the following files.
- demo-market-quotes.csv: The list of products, their historical performance and risk ratings

Each product are ranked in four factors as a summary of their characteristic to facilitate suggestion to investors.

- Risk ranking (1-5)
    This is a mandatory matching criteria which a suggestion of this product only made if product risk <= client risk ranking.  All ranked in the range of 1-5

- Return

- Certainty (1, 3, 8y)- 1 is not certain if the asset could have the expected return in the time horizon.  1 is stock for an 1y investment.  5 is very likely such as treasury bond.  For long horizon, stock may be more certain than an individual bond.

- Certainty (10y)- 1 is not certain if the asset could have the expected return in 

- Liquidity 1 means it's highly unlikely we need the fund before the planned date. While 5 means the need may come earlier and needs liquidate the position to get the funding.

