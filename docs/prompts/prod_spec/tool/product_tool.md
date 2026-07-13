It returns the product_id grouped by risk_rating, with each group listed in descending order of expected_return 

{
  "name": "search_aligned_products",
  "description": "Queries the product catalog for investment assets matching an investor's available cash, risk boundaries, and specific financial intent.",
  "parameters": {
    "type": "object",
    "properties": {
      "product_type": {
        "type": "string",
        "enum": 
        "description": ""
      },
      "region": {
        "type": "string",
        "enum": 
        "description": ""
      },
      "investment_amount": {
        "type": "number",
        "description": "The absolute ticket size the client is looking to deploy (in the client's currency). Used to filter out products with high minimum investment thresholds."
      },
      "max_risk_rating": {
        "type": "integer",
        "minimum": 1,
        "maximum": 5,
        "description": "The investor's maximum acceptable risk rating score. Products exceeding this tier are strictly omitted."
      },
      "target_currency": {
        "type": "string",
        "description": "The target ISO currency code for the investment (e.g., 'HKD', 'USD')."
      },
      "strategic_intent": {
        "type": "object",
        "description": "The client's primary objective mapped directly across the core 4-Factor portfolio matrix.",
        "properties": {
          "min_return": {
            "type": "string",
            "enum": ["Income", "Capital_Growth"],
            "description": "Whether the client seeks regular cash flow distributions or long-term asset appreciation."
          },
          "liquidity_need": {
            "type": "string",
            "enum": ["Immediate_Exit", "Lockup_Acceptable"],
            "description": "Immediate_Exit restricts results to daily trading instruments (Stocks, ETFs). Lockup_Acceptable permits structural maturity terms."
          }
        }
      }
    },
    "required": ["investment_amount", "max_risk_rating"]
  }
}