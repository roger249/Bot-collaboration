# Demo Control API

> **Status**: SPECIFICATION (draft for review — no implementation yet)

## 1. Objective

Give the demo (notebook / script / future UI) a small, HTTP-only way to drive
the demo scenarios — **mutate demo test data and reset it** — without the client
touching DuckDB directly.

This closes the gap in `demo_flow.md`: today the RM-note demo (Demo 1) is done
via raw SQL (`UPDATE clients SET qualitative_profile = ...`), which (a) a future
UI process cannot do, (b) risks DuckDB file-lock contention with the server's
read-only adapter, and (c) leaks internal storage details.

## 2. Motivation / problem solved

| Today | With demo control API |
|---|---|
| Notebook opens a read-write DuckDB connection next to the server's read-only one (lock risk) | Only the server touches the DB; client is pure HTTP |
| Demo teaches an integration pattern the UI can't use | The demo shows the same HTTP contract the UI will use |
| Reset is hand-edited SQL | Reset is one `POST` |

## 3. Scope

### 3.1 In scope

1. Mutate the RM note (`clients.qualitative_profile`) for a client — Demo 1.
2. Reset **all** demo-mutated data back to a canonical baseline — repeatability.
   `reset` covers every demo (1, 2, 3); the exact restore set grows as Demos 2/3
   are finalized (§10 issue #1).
3. (If needed later) inject/remove a maturing bond holding — Demo 3.

### 3.2 Out of scope

- A general CRUD API for clients/holdings/products — the demo tool mutates only
  the specific fields the scenarios need.
- Any use in production.  The demo surface is explicitly marked non-production.
- Working in bank-REST mode (`get_client_product_from_restapi: true`) — see §7.

## 4. Endpoints

All under the `/api/v1/demo/*` namespace to signal "demo-only, not production".

### 4.1 `PATCH /api/v1/demo/clients/{client_id}`

Set a client's RM note.  For the moment the only supported field is
`qualitative_profile` (Demo 1); other demo-tunable attributes are out of scope
until Demos 2/3 are finalized (§10 issue #2).

Request:

```json
{ "qualitative_profile": "<new note text>" }
```

Response `200`:

```json
{
  "client_id": "<client_id>",
  "qualitative_profile": "<new note text>",
  "previous_qualitative_profile": "<value before this update>"
}
```

- `previous_qualitative_profile` is returned so callers can log/audit the flip.
- `404` if the client does not exist.
- `422` if `qualitative_profile` is missing / not a string.

### 4.2 `POST /api/v1/demo/reset`

Restore all demo-mutated data to the canonical baseline (see §6).

Response `200`:

```json
{
  "status": "reset",
  "restored": ["clients.qualitative_profile:PB-HK-000001-8", "…"],
  "note": "demo data restored to canonical baseline"
}
```

- `restored` lists what was reset (human-readable, for the presenter).
- Idempotent: calling reset twice is harmless.

## 5. Data access — write connection

The read path uses `DuckDBDataAdapter` (`read_only=True`, a fresh connection per
fetch).  The demo tool needs its own **read-write** connection, but must follow
these rules to avoid contending with the read path:

- Open the read-write connection **transiently**, mutate, commit, and close it
  **within a single request**.  Never hold it across requests.
- Only for **DuckDB mode**.  DuckDB permits one read-write process at a time;
  the transient open/close keeps the window minimal.

## 6. Reset strategy — canonical baseline

Reset restores **known-good canonical values**, not a re-seed:

- The canonical baseline is a small, hardcoded map of `(table, key, column) →
  original value`, sourced from the seeders / `docs/how_to/how_to_add_fx_tarf.md`.
- Reset issues targeted `UPDATE`s back to those values.

Rationale (vs. an in-memory "undo log"):

| Strategy | Pro | Con |
|---|---|---|
| **Canonical baseline** (chosen) | deterministic, restart-safe (mutations persist to disk, so an in-memory undo log would be lost on restart) | couples reset to specific demo IDs/values |
| In-memory undo log | generic, no hardcoded values | lost on server restart → reset can no longer undo |

For a scripted demo with known IDs, canonical baseline is the safer choice.

## 7. When to refuse

- If `get_client_product_from_restapi: true` (bank-REST mode), the demo tool has
  no DuckDB to mutate → return `409 Conflict` with a clear message.
- If the demo DB file does not exist → `503`.

## 8. Config gating

The demo tool writes to the DB.  It is gated by a top-level section in
`config_planbot.yaml`, **enabled by default** (the demo surface is namespaced
under `/api/v1/demo/*` and is for demo/dev use):

```yaml
demo_tools:
  enabled: true    # set false to hide the /api/v1/demo/* endpoints
```

When `demo_tools.enabled` is false, the `/api/v1/demo/*` endpoints return `404`
(not merely `403`) so they are invisible in non-demo deployments.

## 9. Acceptance Criteria

1. `PATCH /api/v1/demo/clients/{client_id}` updates `qualitative_profile` and
   returns the previous value; `404` on unknown client; `422` on bad body.
2. `POST /api/v1/demo/reset` restores the canonical baseline and is idempotent.
3. Both endpoints are HTTP-only — no client-side DuckDB/SQL required.
4. With `demo_tools.enabled: false`, both endpoints return `404`.
5. In REST mode, both endpoints return `409`.
6. The read path (`DuckDBDataAdapter`) is unchanged and unaffected (no lock
   contention observed under the transient open/close).
7. New unit tests: normal (PATCH then reset restores) + exception (unknown
   client, disabled mode, REST mode).
8. OpenAPI regenerated (`scripts/export_openapi.py`) and
   `docs/specification/demo/demo_flow.md` updated to use the HTTP endpoints.

## 10. Decisions (resolved)

1. **`enabled` default** — `true` (the `/api/v1/demo/*` namespace is on by
   default; set `false` to hide it).
2. **Reset coverage** — `reset` covers **all** demos (1, 2, 3).
3. **Mutation surface** — `PATCH /clients/{id}` supports `qualitative_profile`
   only for now; no extra fields/endpoints until needed.

## 11. Outstanding issues (for discussion)

1. **Demo 2 / 3 injection** — do Demos 2 and 3 need data *injection* at all
   (e.g. a maturing bond for Demo 3, holdings tuning for Demo 2), or do the
   existing seeded FX-TARF clients + maturing holdings already suffice?  This
   determines whether `reset` needs anything beyond restoring the RM note.
