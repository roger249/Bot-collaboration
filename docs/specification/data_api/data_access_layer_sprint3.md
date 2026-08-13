# Data Access Layer — Sprint 3: Cross-System Inconsistency (Tier 2/3)

Status: **Planned** — scope for a future sprint; refine before start.

Tier 1 (idempotent key resolution) is already implemented in Sprint 1.  This
sprint adds the remaining two tiers, deferred until orphan rates are observed
in production — monitor first.

## Tier 2 — Single retry for transient races

If the inconsistency is a write-in-flight (e.g., a trade just booked), waiting
1–2 seconds and retrying once often resolves it:

```python
def _get_enriched_clients(adapter: DataAdapter, client_ids=None):
    clients = adapter.fetch_clients(client_ids)
    holdings = adapter.fetch_holdings(client_ids)
    products = adapter.fetch_products()

    orphan_count = _count_orphans(holdings, products)
    if orphan_count > 0:
        LOGGER.warning("%d orphan holdings — retrying product fetch once", orphan_count)
        time.sleep(1.5)
        products = adapter.fetch_products()  # second attempt

    return compute_derived_fields(clients, holdings, products, score_config)
```

## Tier 3 — Data-quality caveat in the proposal output

For the remaining edge cases (true data gaps, not races), the proposal markdown
itself carries the caveat:

```markdown
## Data Quality Note

At generation time, 2 of 14 holdings could not be matched to products in the
catalogue.  Exposure and concentration figures exclude these positions.
```

Implemented by the proposal assembly layer (not the Logic Layer) checking the
`warnings` list and appending a standard note when non-empty.

## Summary

| Tier | Mechanism | Trigger | Cost |
|---|---|---|---|
| 2 | Single retry after ~1.5s | Orphan count > 0 | One extra REST call |
| 3 | Data-quality caveat in markdown | Warnings still non-empty after retry | A few lines of text |

No distributed transactions. No sagas. No two-phase commit.
