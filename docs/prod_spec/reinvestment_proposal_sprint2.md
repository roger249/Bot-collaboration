# Reinvestment Proposal – Sprint 2

## Overview

Sprint 1 delivered an end-to-end API-backed reinvestment proposal pipeline.
Sprint 2 hardens the architecture, improves production readiness, and adds
missing capabilities that were intentionally deferred.

## Sprint 2 scope

### 1. FastAPI-first data retrieval

**Current state (Sprint 1):**
`generate_reinvestment_proposal` in `src/integrations/reinvestment_proposal.py`
calls client and product APIs via direct Python imports:

- `search_by_id` (local import)
- `search_by_product_id` (local import)
- `search_reinvestment_candidates` (local import)

**Target (Sprint 2):**
Replace all local imports with HTTP calls to the FastAPI endpoints running
on `localhost`:

| Current call | Sprint 2 replacement |
|---|---|
| `search_by_id(client_id)` | `GET /api/v1/clients/{client_id}` |
| `search_by_product_id(pid)` | `GET /api/v1/products/{pid}` |
| `search_reinvestment_candidates(...)` | `POST /api/v1/products/reinvestment-candidates` |

**Rationale:**
- Enforces loose coupling between services.
- Makes the proposal builder a true API consumer.
- Allows independent scaling/deployment of client/product services.
- Matches the architecture commitment in the Sprint 1 spec.

**Acceptance criteria:**
| # | Criterion | Verification |
|---|---|---|
| AC1 | All client lookups use `GET /api/v1/clients/{client_id}` | Code review + HTTP trace |
| AC2 | All product lookups use `GET /api/v1/products/{product_id}` | Code review + HTTP trace |
| AC3 | Candidate search uses `POST /api/v1/products/reinvestment-candidates` | Code review + HTTP trace |
| AC4 | Same tests pass (existing test suite unchanged) | `pytest tests/test_reinvestment_proposal.py` |

---

### 2. Discovery/orchestration endpoint

**Current state (Sprint 1):**
Callers must provide `reinvestment_targets` explicitly. No maturity-driven
auto-discovery exists.

**Target (Sprint 2):**
Add a new endpoint that wraps the full discovery-to-proposal flow:

- `POST /api/v1/reinvestment-proposals/discover`

**Request:**

```json
{
  "product_types": ["bond", "bond_fund"],
  "within_days": 180,
  "response_mode": "path",
  "include_debug_scores": false
}
```

**Behavior:**
1. Calls `search_holdings_maturing` (via `GET /api/v1/clients/holdings/maturing`).
2. Deduplicates by client, builds `reinvestment_targets`.
3. Calls `generate_reinvestment_proposal` (via `POST /api/v1/reinvestment-proposals`).
4. Returns the same response shape.

**Acceptance criteria:**
| # | Criterion | Verification |
|---|---|---|
| AC5 | Discovery endpoint accepts `product_types`, `within_days` | Integration test |
| AC6 | Output matches `POST /api/v1/reinvestment-proposals` response shape | Snapshot test |
| AC7 | Falls back gracefully when no maturing holdings are found | Unit test |

---

### 3. Concurrency / parallel fan-out

**Current state (Sprint 1):**
`client_ids` iteration is sequential.

**Target (Sprint 2):**
Add bounded parallelism with configurable concurrency:

- `max_concurrency: int` parameter on the reinvestment proposal endpoint.
- Default 1 (sequential, backward-compatible).
- Each target runs in its own thread/async task.
- Partial failure handling (one client failure does not abort others).

**Acceptance criteria:**
| # | Criterion | Verification |
|---|---|---|
| AC8 | `max_concurrency > 1` runs multiple targets in parallel | Timed integration test |
| AC9 | One client failure does not block others | Failure injection test |
| AC10 | Response shape unchanged from Sprint 1 | Golden test |

---

### 4. Compact LLM input format (token optimization)

**Current state (Sprint 1):**
`llm_input` is JSON. Reference files use Markdown + CSV.

**Target (Sprint 2):**
Introduce a token-optimized serialization layer:

- Holdings: pipe-delimited rows with a header line.
  ```
  product_id|name|asset_class|currency|market_value|yield_pct
  ```
- Products: key=value blocks.
  ```
  type=bond_fund risk=3 er=6.2 region=North America
  ```
- Gated behind `context_format: "json" | "compact"` parameter.
- Default stays `"json"` for backward compatibility.

**Estimated token savings:** ~3–4× vs Markdown, ~2× vs JSON.

**Acceptance criteria:**
| # | Criterion | Verification |
|---|---|---|
| AC11 | `context_format="compact"` produces pipe-delimited holdings | Snapshot test |
| AC12 | `context_format="compact"` produces key=value product blocks | Snapshot test |
| AC13 | Proposal quality does not degrade vs JSON format | Golden-file comparison |

---

### 5. Candidate explanation ownership

**Current state (Sprint 1):**
Candidate shortlist rationales are not assembled. The LLM infers them from
raw product data.

**Target (Sprint 2):**
The proposal service emits structured rationale per candidate:

- `fit_score` and component breakdown.
- `risk_match` summary.
- `reinvestment_fit` reasoning.
- `why_shortlisted` one-liner.

The LLM converts this into narrative text, keeping shortlist logic
deterministic and testable.

**Acceptance criteria:**
| # | Criterion | Verification |
|---|---|---|
| AC14 | Each candidate in `llm_input` includes structured rationale fields | Unit test |
| AC15 | Rationale is computed deterministically from scores | Unit test |

---

## Deferred to Sprint 3+

| # | Item | Rationale |
|---|---|---|
| N/A | Market outlook source selection standardization | Not required for core API stabilization |
| N/A | Token-optimized format evaluation in production | Depends on real traffic volume data |

## Outstanding (Sprint 2)

| # | Item | Suggested Approach |
|---|---|---|
| O1 | Switch client/product lookups to FastAPI HTTP calls | Replace `src.integrations.*` imports with `requests.get/post` on `localhost:8000` |
| O2 | Add discovery/orchestration endpoint | New `POST /api/v1/reinvestment-proposals/discover` |
| O3 | Add bounded concurrency | `max_concurrency` parameter with thread pool |
| O4 | Add compact LLM input format | `context_format` parameter with pipe/key=value serialization |
| O5 | Add deterministic candidate explanations | Emit structured rationale per candidate in service layer |
