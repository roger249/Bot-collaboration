## Deferred to Sprint 3+

| # | Item | Rationale |
|---|---|---|
| N/A | Market outlook source selection standardization | Not required for core API stabilization |
| N/A | Token-optimized format evaluation in production | Depends on real traffic volume data |


| T12 | Add bounded concurrency with `max_concurrency` | `src/integrations/reinvestment_proposal.py` |
| T13 | Add compact LLM input format (`context_format` parameter) | `src/planbot/workflow.py` |
| T14 | Add deterministic candidate explanations | `src/integrations/reinvestment_proposal.py` |



### 4. Concurrency / parallel fan-out

**Current state (Sprint 1):**
`client_ids` iteration is sequential.

**Target (Sprint 2):**
Add bounded parallelism with configurable concurrency:

- `max_concurrency: int` parameter on the reinvestment proposal endpoint.
- Default 1 (sequential, backward-compatible).
- Each target runs in its own thread/async task.
- Partial failure handling (one client failure does not abort others).

The in-memory resolver design from §1 makes parallelism safe: no shared
temp directories, no file-collision risk.

**Acceptance criteria:**
| # | Criterion | Verification |
|---|---|---|
| AC16 | `max_concurrency > 1` runs multiple targets in parallel | Timed integration test |
| AC17 | One client failure does not block others | Failure injection test |
| AC18 | Response shape unchanged from Sprint 1 | Golden test |



### 5. Compact LLM input format (token optimization)

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
| AC19 | `context_format="compact"` produces pipe-delimited holdings | Snapshot test |
| AC20 | `context_format="compact"` produces key=value product blocks | Snapshot test |
| AC21 | Proposal quality does not degrade vs JSON format | Golden-file comparison |

---

### 6. Candidate explanation ownership

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
| AC22 | Each candidate in `llm_input` includes structured rationale fields | Unit test |
| AC23 | Rationale is computed deterministically from scores | Unit test |

---