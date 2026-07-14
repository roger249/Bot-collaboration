Product Catalog Integration
===========================

The information about the financial product is retrieved via API from the main module product catalog layer.  To develop a working prototype without depending on the readiness of the main module.  This spec is to provide a mock up (simulation) of the product catalog API.  The main tasks includes

1. Tidy up and have initial schema designed for the product catalog
2. Populate it with test data
3. Move all product catalog into DuckDB
4. Provide Python method to query the duckDB
5. Move Python method into Fast API
6. With this product and the client API, we will migrate the various investment proposal to use API to query the necessary data to fit to LLM.

Steps 1-3 shall have finished from the spec docs/prompts/product_catalog.md

This document focus on step 4.

# API

Below are the API exposed to search the product catalog, it returns a list of the products in JSON format

1. search by product_id
2. search by following attributes
  This shall be proximity search that return top n products with 
    - risk_rating
    - expected_return
    - product_type
    - asset_class
    - region
    - industry
    - time_to_maturity # accepted in d, w, m, y
    - coupon  # This shall be the dividend of a MF/ETF and the coupon for bond
    - trade_date # default to system date if not specified.  This is used to compute the time_to_maturity

3. Search products for reinvestment purpose.  This will leverage the search in 2 but the input is a product_id that used to provide the product attributes to search similar product

For the same asset class, at most three products shall be in the same industry or same region to maintain diversification

4. search by product_fitness_score

It returns the product_id grouped by risk_rating, with each group listed in descending order of expected_return 

# Product fitness score

It accepts two lists - list of client_id (m) and product_id (n), then compute the score for each client_id x product_id, then order the score by descending order and return the top nth result

(client_id, product_id, score)

The score is find how fit a product for a particular investor.  It computes the following dimension 

Without assuming switching out a particular product.  A score is computed in the following dimensions.

1. risk_rating matches client
  - product.risk_rating <= client.risk_rating
2. concentration.  Will provide diversification to the current portfolio
3. has_similar_investment_experience
  - holding of same product type
  - holding of the underlying of the product type
4. better product than existing
  - better return than existing with same risk_rating
  - Same risk rating but better expected return

The score will pass to the LLM along with the selected clients and products to make the final recommendation.  The additional information including

- market outlook
- product description from the bank