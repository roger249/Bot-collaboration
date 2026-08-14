# Endpoint Index (LLM Coding Context)

Purpose: concise endpoint map for coding tasks. OpenAPI remains the source of truth.

Primary sources:
- `docs/specification/data_api/openapi_data.json` (bank data server — raw client/holding/product rows)
- `docs/specification/data_api/openapi_proposal.json` (proposal server — proposal + data-lookup endpoints)
- `docs/specification/data_api/bank_data_contract.md` (human-readable bank hand-off contract: semantics + field tables)
- `docs/specification/data_api/client_api.md`
- `docs/specification/data_api/product_api.md`

## Endpoint Table

### Bank data server (raw rows — `openapi_data.json`)

| Domain | Operation ID | Method | Path | When to use | Required inputs | Key outputs | Common errors |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Client | `list_clients_api_v1_clients_get` | GET | `/api/v1/clients` | List raw client rows (comma-separated filter) | optional `client_id`, `offset`, `limit` | full raw client rows | `422` validation |
| Client | `get_client_api_v1_clients__client_id__get` | GET | `/api/v1/clients/{client_id}` | Retrieve one raw client row | path `client_id` | raw client row | `404` not found, `422` validation |
| Holding | `list_holdings_api_v1_holdings_get` | GET | `/api/v1/holdings` | List raw holding rows (comma-separated filter) | optional `client_id`, `offset`, `limit` | raw holding rows | `422` validation |
| Product | `list_products_api_v1_products_get` | GET | `/api/v1/products` | List raw product rows (comma-separated filter) | optional `product_id`, `offset`, `limit` | raw product rows | `422` validation |
| Product | `get_product_api_v1_products__product_id__get` | GET | `/api/v1/products/{product_id}` | Retrieve one raw product row | path `product_id` | raw product row | `404` not found, `422` validation |

### Proposal server data-lookup endpoints (business logic — `openapi_proposal.json`)

| Domain | Operation ID | Method | Path | When to use | Required inputs | Key outputs | Common errors |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Client | `get_holdings_maturing_api_v1_clients_holdings_maturing_get` | GET | `/api/v1/clients/holdings/maturing` | Find clients with maturing fixed-income holdings | optional `product_types`, `within_days`, `as_of_date` | `{client_id, product_id, market_value, days_to_mature}` | `422` validation |
| Client | `get_investor_readiness_api_v1_clients_readiness_get` | GET | `/api/v1/clients/readiness` | Retrieve readiness-ranked clients | optional `top_n` | readiness rank and component scores | `422` validation |
| Product | `search_similar_products_api_v1_products_search_similar_post` | POST | `/api/v1/products/search-similar` | Find similar products and diversification alternatives | query payload + optional ranking knobs | ranked product list + similarity_score | `422` validation |
| Product | `get_reinvestment_candidates_api_v1_products_reinvestment_candidates_post` | POST | `/api/v1/products/reinvestment-candidates` | Get reinvestment candidates from a seed product | seed product + options | ranked candidates + similarity_score | `422` validation |
| Product | `get_product_fitness_score_api_v1_products_fitness_score_post` | POST | `/api/v1/products/fitness-score` | Score client x product candidates | `client_ids`, `product_ids`, options | `(client_id, product_id, product_name, fitness_score, component_scores)` | `422` validation |

## Usage Notes for Coding Assistants

- Prefer operation IDs and schema in `openapi_data.json` / `openapi_proposal.json` over prose when there is any mismatch.
- Use this file for endpoint selection, then read the relevant `openapi_*.json` for exact request/response shape.
- Regenerate the specs after any endpoint change with `./.venv/bin/python scripts/export_openapi.py`.
- Runtime implementation is under `src/integrations` and must stay aligned with this contract.
- Empty result for list endpoints is a valid success path (HTTP `200`) with empty list/section.
