# Changes

The risk rating are generated in the file runs/market_data/selected_etf.csv when running run-market-data (from command line argument)

We will revise how the risk rating for products (runs/market_data/selected_etf.csv) is generated.  

The logic shows in the section "product catalog" in the file docs/spec/Product Investor Matcher.md.  

These will affect the four columns 

- risk_rating
- rename expected_return_score to expected_return
- certainty_<period>_score -> certainty_<period>_rating
- liquidity_score -> liquidity_rating

- Maintain all floor or cap rule for certainty as it is

All mapping are done via the config/config_marketdata.yaml and example has made for risk_rating and certainty_rating

# Acceptance
- the columns are renamed as above
- certainty/risk rating are assigned according to the table defined in the yaml
