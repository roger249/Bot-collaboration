# Objective

Luxinger doesn't provide any API for US stock price ratio data.  We'd like to build a utility to scrape the following metrics for PE-TTM, PB, and PS-TTM from the 

- Current Value
- Current Value Position
- 80% Point Value
- 50% Point Value
- 20% Point Value
- Max Value
- Average Value
- Min Value

Sample URL of the data as below

- HK stock
https://www.lixinger.com/analytics/company/detail/hk/00836/836/fundamental/valuation/primary?granularity=y10&y-axis-right-metrics-name=lxr_fc_rights

- US stock
https://www.lixinger.com/analytics/company/detail/nyse/BABA/157755200/fundamental/valuation/primary

This is currently a utility.  It'll be used to scrape information and provided to LLM as reference without package as tool.

## Input is a stock symbol

## Return

- All scrape put in python dict
- All metrics return in one call


# User interaction

- Go https://www.lixinger.com/
- Click the button "開始使用". (docs/spec/luxinger_scraper/1. start.jpg)
- Logon with username roger249, password from env LIXINGER_PASSWORD (2. login)
- Put in ticker name (e.g., BABA) in the top right box, (3. data)
- Adjust all duration to 10y on the top right of each. (3. data)
- Scrape the required data from the left of the page

# Recording procedure

playwright codegen --target python --browser webkit https://www.lixinger.com/analytics/company/detail/hk/00700/700/fundamental/valuation/primary
