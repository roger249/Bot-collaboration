Here is an initial specification for your client-matching tool. This spec defines the tool's interface (what the LLM sees) and outlines how your backend script should execute the actual query.

---

### Part 1: The LLM Schema Specification

This is the formal JSON schema that you pass directly to the LLM within your API request (compatible with OpenAI, Anthropic, Gemini, or LangChain).

```json
{
  "type": "function",
  "function": {
    "name": "fetch_target_investors",
    "description": "Queries the client CRM/database to retrieve a pre-filtered list of clients based on criteria mapping to a specific financial product type. Use this to drastically narrow down the 1,000-client list before applying deeper qualitative matching.",
    "parameters": {
      "type": "object",
      "properties": {
        "product_type": {
          "type": "string",
          "enum": ["mutual_fund", "annuity", "structured_product", "fixed_income"],
          "description": "The type of financial instrument being matched."
        },
        "min_net_worth": {
          "type": "number",
          "description": "The minimum liquid net worth or investable assets required for the product. Set to 0 if no minimum exists."
        },
        "acceptable_risk_profiles": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": ["Conservative", "Moderate", "Aggressive"]
          },
          "description": "List of client risk tolerances that fit this instrument."
        },
        "investment_horizon_years_min": {
          "type": "integer",
          "description": "The minimum time horizon (in years) required for this product (e.g., 5+ years for structured products, 10+ for annuities)."
        },
        "max_results": {
          "type": "integer",
          "default": 50,
          "description": "The maximum number of candidate clients to return in a single batch to fit into the LLM context window."
        }
      },
      "required": ["product_type", "acceptable_risk_profiles"]
    }
  }
}

```

---

### Part 2: Backend Mock Logic (Python)

When the LLM triggers the function above, your backend system intercepts the JSON payload, queries your database, and returns the data back to the LLM.

Here is a blueprint of how to structure that logic:

```python
import json
from typing import List, Dict, Any

def fetch_target_investors(
    product_type: str, 
    acceptable_risk_profiles: List[str], 
    min_net_worth: float = 0, 
    investment_horizon_years_min: int = 0,
    max_results: int = 50
) -> str:
    """
    This function connects to your internal database/DataFrame containing 
    the 1,000 clients and runs a deterministic filter.
    """
    
    # 1. Fetch your raw database/DataFrame here
    # raw_clients = db.query("SELECT * FROM clients")
    raw_clients = [] # Placeholder for your 1000 clients list
    
    filtered_leads = []
    
    for client in raw_clients:
        # Example Hard Filters:
        if client['risk_tolerance'] not in acceptable_risk_profiles:
            continue
        if client['net_worth'] < min_net_worth:
            continue
        if client['investment_horizon'] < investment_horizon_years_min:
            continue
            
        # Structure the payload efficiently for the LLM context window
        filtered_leads.append({
            "client_id": client["id"],
            "age": client["age"],
            "risk_profile": client["risk_tolerance"],
            "net_worth": client["net_worth"],
            "current_holdings": client["top_holdings"], 
            "recent_notes": client["latest_interaction_summary"] # Qualitative text for LLM to read
        })
        
        if len(filtered_leads) >= max_results:
            break
            
    # Return as a stringified JSON object back to the LLM
    return json.dumps({"status": "success", "candidates_found": len(filtered_leads), "data": filtered_leads})

```

---

### Areas to Enhance As You Take This Over

1. **Add Vector Embeddings:** If your client data includes long, conversational text fields (e.g., meeting notes like *"Client mentioned being stressed about market volatility and wants guaranteed income"*), add a `semantic_query` string parameter to the tool. You can use it to perform a vector search alongside your hard filters.
2. **Handle Large Lists via Pagination:** If the tool matches 300 out of 1,000 clients, you don't want to pass all 300 to the LLM at once. Enhance the schema to include an `offset` or `page` parameter so the system can process the matches in waves.
3. **Include "Product Exclusions":** Financial instruments often have constraints. You could add an `exclusion_tags` array parameter to the schema (e.g., `["US_Citizens_Only", "No_Liquidity_Needs"]`) to ensure the backend skips clients who explicitly don't fit the product's legal constraints.