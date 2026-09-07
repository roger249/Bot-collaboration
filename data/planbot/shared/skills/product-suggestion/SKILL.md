---
name: product-suggestion
description: Rules for suggesting an investment product to a client
---

- For each client, assign a buying score from 1-5 indicating how likely the client is to buy the recommended investment product.  5 is the most likely to buy, while 1 is the least likely to buy.
- Only one product recommendation is allowed for each client.
- For any suggested product, please specify the funding source.
- No more than 2 products shall be switched out for funding.
- Whenever you mention, state, or quote a Product Fitness Score (the "Fitness Score" column, 0–10, higher = better fit), you MUST explain it in plain language — never state a bare number. State the overall score first, then name the component scores that drove it and explain why each is high or low for THIS client, ending with an explicit fit/not-fit conclusion.
  - A component is "material" (must be explained) when it clearly drives fit (≈7.0 or higher) or drives non-fit (≈3.0 or lower), plus the single highest and single lowest component if those are not already covered. Skip mid-range/neutral components.
  - Name each component exactly by its table column: Risk Match, Diversification, Experience, Better Product, Like, Comfort, Holding Similarity, RM Note Similarity.
  - If RM note is used, please state the original RM note or an excerpt relevant to the score as a supporting reference.
  - Ground every material component in the client's actual data, not just the number — e.g. "Like = 8.5 because the client's stated interest in technology funds matches this product's focus"; for a low score say what is missing or mismatched (e.g. "RM Note Similarity = 2.0 because the RM's notes favour capital preservation, but this product is high-volatility growth").
  - If a similarity column is neutral (5.0) because semantic similarity was unavailable, say so and do not treat it as a real signal.
  - End with one sentence stating whether the product fits this client and why (cite the strongest and weakest component).
- Treat the Product Fitness Score as the primary (baseline) factor for selecting the recommended product.  Feel free to support the recommendation with factor outside fitness score. State explicitly and grounded in the given data — do not name a factor without its supporting evidence:
  - Market outlook — cite the market_outlook reference.
  - Liquidity — cite the product's liquidity relative to the funding source, consistent with the >5% cash/cash-equivalent liquidity rule.
  - Expected return — cite the product's 5y CAGR (not 1y/3y unless justified per the CAGR-sustainability rule).
- For any switch out, good to justify the reason in terms of outlook and expected benefit from the market_outlook reference.
- Consider below to ensure the suggested product is suitable for the client, among other factors:
  - "RM Note" in the client profile
  - "Investment note" in the product catalog
  - Market outlook
- The risk class or asset class of the suggested product should be similar to the funding source.
- Do not increase holding for any product other than the suggested product.
- The suggested product shall have more than 0.5% return than existing or better liquidity.  Otherwise a strong justification of switching shall be provided.
- Consider having more than 5% of the portfolio in cash or cash equivalent for liquidity purpose.
- Use 5y CAGR for the future expected return.  For a product with much higher 1y, 3y CAGR than 5y CAGR, provide justification on the sustainability of the return.
