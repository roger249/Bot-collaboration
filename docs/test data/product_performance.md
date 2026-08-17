# Market data

# Objective

A module will be built to output the historical performance of financial products for product-investor matching.

The module will update data/planbot/shared/product_catalog/selected_etf.csv using settings in config/config_marketdata.yaml.

This module is independent of others and packaged in its own Python module. It will be used in other Python programs as well.

# Design

- Frequency of closing retrieval is configurable in config_marketdata.yaml, defaulting to 1w.
- When frequency is not 1d, output metrics are approximations.
- Output metrics include the following for each specified period:
    - cumulative_gain
    - annualized_gain
    - max_drawdown
    - high - highest price during the period
    - low, lowest price during the period
- Returns are total returns, so dividends are included.
- Config is handled by pydantic with validation.
- Logging uses loguru.
- Unit tests use pytest.

def get_market_data(tickers, output_filename="selected_etf.csv", frequency="1w", metrics=None, periods=None)

tickers are Yahoo tickers
frequency: 1d, 1w, 1m, 1q; default 1w
periods: default [6m, 1y, 3y, 5y, 10y]

## Output fields

Output format is CSV. The bullet list below is documentation formatting only.

CSV output requirements (implementation-critical):
- Single CSV table only (no markdown separators, section headers, or comments).
- First row is header; each subsequent row is one ticker.
- UTF-8 encoding, comma delimiter, RFC4180-compatible quoting.
- Do not add trailing delimiter at end of each row.

Dynamic period-based fields are expanded from periods at runtime (for example, [6m, 1y, 3y, 5y, 10y]).
- return columns: <period>_return
- drawdown columns: <period>_max_drawdown
- IHR columns: price_<period>_IHR_20 and price_<period>_IHR_80

- ticker
- asset_class
- name
- currency
- last_update_date
- last_closing_price
- <period>_return
- <period>_max_drawdown
- price_<period>_IHR_20
- price_<period>_IHR_80
- risk_rating
- expected_return_score
- certainty_1y_score
- certainty_3y_score
- certainty_8y_score
- liquidity_score

## Score and risk rating

To facilitate high-precision matching, each product is scored across four dimensions:

1. Risk Rating (Mandatory Constraint)
Scale: 1 (Lowest) to 5 (Highest).

2. Expected Return
Scale: 1 (Capital Preservation) to 5 (Aggressive Growth).

Definition: Represents the rating of projected annualized yield (not the actual price return) or capital appreciation. A rating of 1 implies a focus on nominal stability, while 5 indicates a high-conviction growth target, typically associated with higher volatility.

3. Certainty (Time-Horizon Probability)
Scale: 1 to 5, assessed across three horizons: 1y, 3y, and 8y.

Definition: Measures the probability of achieving the "Expected Return" over the specific holding period.

Fixed Income Example: A 10-year Treasury bond may score 5/5 for Certainty-8y (low default risk) but 3/5 for Certainty-1y due to mark-to-market sensitivity to interest rate fluctuations.

Equity Example: An index ETF may score 2/5 for Certainty-1y (high short-term variance) but 4/5 for Certainty-8y as historical time-diversification reduces the range of outcomes.

4. Liquidity
Scale: 1 (Illiquid/Locked) to 5 (Daily Liquidity).

Definition: Reflects the ease of exiting a position at the current market price without significant penalty or delay.

Score 5: Exchange-traded equities and daily-dealing Mutual Funds.

Score 2-3: Products with structural barriers, such as annuities or structured product, where early unwinding incurs significant surrender charges or exit fees.


# Sample output
A sample of a similar output can be found below.  Please note their column heading is different.  Please use above as the correct output reference.  Treat below as a similar sample only.

data/planbot/shared/product_catalog/demo-market-quotes.csv

# Acceptance criteria

- Able to generate the CSV without error with all the fields above.

## Test tickers
Please use below tickers for the test

XLK 
XLF 
XLV 
XLY 
XLP 
XLE 
XLI 
XLB 
XLRE 
XLU 
XLC
VOO
HYG
FLOT
BSV
SHYG
USO
GLDM




