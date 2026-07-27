# Endpoint Index (LLM Coding Context)

Purpose: concise endpoint map for coding tasks. OpenAPI remains the source of truth.

Primary sources:
- `docs/prod_spec/tool/openapi.json`
- `docs/prod_spec/tool/client_tool.md`
- `docs/prod_spec/tool/product_tool.md`

## Endpoint Table

| Domain | Operation ID | Method | Path | When to use | Required inputs | Key outputs used by matcher | Common errors |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Client | `search_clients_api_v1_clients_search_post` | POST | `/api/v1/clients/search` | Filter candidate clients by criteria | criteria payload (for example risk rating, age, holdings filters) | `client_id`, profile fields, holdings summary | `422` validation |
| Client | `get_holdings_maturing_api_v1_clients_holdings_maturing_get` | GET | `/api/v1/clients/holdings/maturing` | Find clients with maturing fixed-income holdings | optional `product_types`, `within_days`, `as_of_date` | `{client_id, product_id, notional, days_to_mature}` | `422` validation |
| Client | `get_investor_readiness_api_v1_clients_readiness_get` | GET | `/api/v1/clients/readiness` | Retrieve readiness-ranked clients | optional `top_n` | readiness rank and component scores | `422` validation |
| Client | `get_client_api_v1_clients__client_id__get` | GET | `/api/v1/clients/{client_id}` | Retrieve full profile for one client | path `client_id` | full client profile + holdings | `404` not found, `422` validation |
| Product | `get_product_api_v1_products__product_id__get` | GET | `/api/v1/products/{product_id}` | Retrieve one product detail | path `product_id` | product attributes used in rationale/scoring context | `404` not found, `422` validation |
| Product | `search_similar_products_api_v1_products_search_similar_post` | POST | `/api/v1/products/search-similar` | Find similar products and diversification alternatives | query payload + optional ranking knobs | ranked product list + similarity score | `422` validation |
| Product | `get_reinvestment_candidates_api_v1_products_reinvestment_candidates_post` | POST | `/api/v1/products/reinvestment-candidates` | Get reinvestment candidates from a seed product | seed product + options | ranked reinvestment candidates | `422` validation |
| Product | `get_product_fitness_score_api_v1_products_fitness_score_post` | POST | `/api/v1/products/fitness-score` | Score client x product candidates | `client_ids`, `product_ids`, options | `(client_id, product_id, score, component_scores)` | `422` validation |

## Usage Notes for Coding Assistants

- Prefer operation IDs and schema in `openapi.json` over prose when there is any mismatch.
- Use this file for endpoint selection, then read `openapi.json` for exact request/response shape.
- Runtime implementation is under `src/integrations` and must stay aligned with this contract.
- Empty result for search/list endpoints is a valid success path (HTTP `200`) with empty list/section.
