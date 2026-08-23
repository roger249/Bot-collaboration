Product maturing
================

An API `search_holdings_maturing` is developed to return the product in the holding that are going to mature in `within_days` from `as_of_date`

The maturity of different product_types are covered by the following rules.
- Structured Product or Note or Bond matured

This could be the product_type matured field.
- Potential barrier breached

Below will be done in next phase.

- Option, in particular sell call will be exercised.

This could be the product_type expiry field.

- Potential Knock out 



## API specification
### 3. `search_holdings_maturing`

Find clients with bonds or fixed‑income products maturing within a given window.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `product_types` | `[str]` | no | e.g. `["bond"]` — match product catalog `product_type`.  If omitted, all FI types are included. |
| `within_days` | `int` | no | Calendar days to maturity.  Default 14. |
| `as_of_date` | `str` (ISO 8601) | no | Reference date for computing days‑to‑maturity.  Defaults to system date. |

```
search_holdings_maturing(product_types=["bond"], within_days=14) → [
  {client_id, product_id, notional, days_to_mature}
]
```

