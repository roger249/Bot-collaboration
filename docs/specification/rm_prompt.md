# RM Prompt — Relationship Manager Fine-Tuning Note

> Status: **Draft** (pending review of outstanding issues at the end)

## 1. Objective

When a Relationship Manager (RM) reads a generated proposal, they may want to
fine-tune the next run without rewriting the whole prompt. We let the RM enter a
free-text note that is passed through to the LLM as an additional, high-salience
guidance block.

Examples:

- *"The interest rate outlook really goes to rise rate in next two months, good
  to recommend product that will benefit from rate hiking."*
- *"Client doesn't like structured product, please try to avoid this."*

`rm_prompt` is exposed as a request parameter on **all proposal APIs**, defaulting
to empty. It is a **per-investor** note keyed by `client_id` (a plain string is
accepted for single-client endpoints). When present, each client's note is
injected into the LLM prompt so the model must consider it when generating that
client's proposal.

## 2. Scope

`rm_prompt` applies to every proposal endpoint that invokes the CrewAI pipeline:

| # | Endpoint | Integration function |
| --- | --- | --- |
| 1 | `POST /api/v1/product-investor-matcher` | `product_investor_matcher()` |
| 2 | `POST /api/v1/reinvestment-proposals` | `propose_reinvestment()` |
| 3 | `POST /api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings` | `propose_reinvestment_for_maturing_holdings()` |
| 4 | `POST /api/v1/product-opportunity-proposal` | `propose_product_opportunity()` |
| 5 | `POST /api/v1/product-opportunity-proposal-automatch` | `propose_product_opportunity_automatch()` |
| 6 | `POST /api/v1/portfolio-review` | `propose_portfolio_review()` |
| 7 | `POST /api/v1/llm-product-matcher` | `propose_llm_product_matcher()` |

## 3. Design decision — which channel?

The prompt is assembled from two structurally different channels (see
`src/planbot/workflow.py` `_build_user_prompt`, and
`docs/specification/proposal/Migrate_to_shared_skills.md` §3.1):

| Channel | Nature | Carrier |
| --- | --- | --- |
| Task prompt | Imperative — what the model must *do* | `Task.description` |
| Reference payload | Reference material — *not instructions* | appended JSON sections |

`rm_prompt` is **imperative content** (a constraint/override the RM wants the
model to honour). Therefore it belongs in the **task prompt channel**, not the
reference JSON.

### 3.1 Rejected alternatives

| Option | Why rejected |
| --- | --- |
| **A new CrewAI skill** (`SKILL.md`) | Skills are **static**, authored once and loaded from disk at agent construction. `rm_prompt` is **runtime, per-request, free-form** — it cannot be a skill. |
| **A reference input** (like `market_outlook`) | The reference JSON is explicitly labelled *"not as instructions"*. Placing an RM constraint there would weaken its imperative force. |
| **The system prompt** (`role`/`goal`/`backstory`) | These are static per proposal and would require a per-request agent rebuild; also mixes per-run state into the agent definition. |

### 3.2 Decision

Append `rm_prompt` to the **task description** (`task_prompt` in
`run_crew_planbot`), so it lands in the imperative instruction position **before**
the reference JSON (see §4).

`rm_prompt` is distinct from the persistent `qualitative_profile` RM notes on the
client record: `qualitative_profile` is static CRM context already fed as part of
`client_profile` (and used by `similarity_to_RM_note` scoring), whereas
`rm_prompt` is a transient per-request instruction. Any residual overlap is
acceptable and safely handled by the LLM (agreed).

## 4. Prompt placement and format

`rm_prompt` is appended to `task_prompt` in `run_crew_planbot` **before**
`_build_user_prompt()` wraps it with the reference JSON. This gives the final
user-message ordering:

1. base task description (from `tasks.yaml` `description`)
2. `## RM Guidance` block (only when `rm_prompt` is non-empty)
3. reference JSON

`rm_prompt` is implemented **independently of** the pending skill-reordering work
(`rearrange_skill_before_json_reference.md`): the block is appended to the base
description, before the reference JSON, regardless of where CrewAI currently
places skill sections. The two changes are treated as completely separate items.

The block is wrapped in a fixed, clearly-marked heading so the model
distinguishes the RM's transient override from the static task rules. Each
client's note is listed as a bullet so per-investor guidance stays unambiguous
(the multi-client endpoints produce many proposals in one LLM call):

```markdown
## RM Guidance (override)

Per-client guidance from the relationship manager. Treat each as a hard
constraint for that client and weigh it strongly in the recommendation:

- PB-HK-000001-8 (David Kim): Client dislikes structured products; avoid.
- PB-HK-000005-9 (Emma Thompson): Favour inflation-protection themes.
```

For a single-client endpoint the block contains exactly one bullet.

Rules:

- When `rm_prompt` is empty (all notes empty/whitespace), **no block is emitted**
  (prompt is byte-identical to today).
- Each note body is injected verbatim (no trimming beyond stripping surrounding
  whitespace).
- The wrapper heading/preamble is a hardcoded module-level constant (see §7).

## 5. Threading path

Each endpoint threads `rm_prompt` down to `run_crew_planbot`:

```
endpoint (proposal_server.py request model)
  → integration function (..., rm_prompt: dict[str, str] | str | None = None)
    → run_crew_planbot(..., rm_prompt=rm_prompt)
      → task_prompt = base_description + RM_GUIDANCE_BLOCK(rm_prompt)
```

Concretely:

1. **`src/planbot/workflow.py`** — add a helper `_build_rm_guidance_block(rm_prompt, client_names=None) -> str` returning `""` for empty input, else the §4 block. `client_names` maps `client_id` → display name so each bullet reads `ID (Name)`.
2. **`src/planbot/crew_workflow.py`** — `run_crew_planbot()` gains `rm_prompt: dict[str, str] | str | None = None`; after loading `task_prompt` it appends the block when non-empty. The single-string form is normalised to the single-client map before building the block.
3. **Each integration function** in `src/integrations/*.py` gains `rm_prompt: dict[str, str] | str | None = None` and forwards it to its `run_crew_planbot(...)` call.
4. **`src/integrations/proposal_server.py`** — each of the 7 request models gains
   `rm_prompt: dict[str, str] | str | None = Field(None, description=...)`; each endpoint forwards `body.rm_prompt`.

## 6. API contract

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `rm_prompt` | `dict[str, str]` \| `string` \| `null` | `null` (empty) | Per-investor RM fine-tuning note keyed by `client_id`. Single-client endpoints accept a plain string (treated as that client's note). When non-empty, injected as the `## RM Guidance` instruction block. |

The field is added to all seven request schemas in
`docs/specification/proposal_api/openapi_proposal.json` (regenerate after the
Pydantic models are updated).

## 7. Wrapper template (hardcoded)

**Agreed:** the wrapper template (heading + preamble) is a hardcoded module-level
constant in `src/planbot/workflow.py` (e.g. `_RM_GUIDANCE_HEADING` and
`_RM_GUIDANCE_PREAMBLE`). YAML externalization is **not** required for this
first pass and may be revisited later if the phrasing needs to be tuned without
a code change.

The RM note body itself is runtime user input and is never hardcoded or
externalized.

## 8. Testing (Standard)

Two minimal regression tests, per the project's unit-test convention
(`python unittest`):

1. **Normal flow** — a non-empty per-investor `rm_prompt` (map of two clients)
   produces a task prompt containing the `## RM Guidance` block with one bullet
   per client, positioned **before** the reference-JSON marker line.
2. **Exception/edge flow** — an empty `rm_prompt` (empty map, or all notes blank)
   emits **no** block and leaves the prompt identical to a run with `rm_prompt`
   omitted.

Target files: extend `tests/test_reinvestment_proposal.py` (or a new
`tests/test_rm_prompt.py`) asserting on `_build_user_prompt` / the composed
`task_prompt`.

## 9. Resolved decisions (review 2026-09-03)

| # | Decision |
| --- | --- |
| 1 | `rm_prompt` is **per-investor** (keyed by `client_id`); single-client endpoints accept a plain string. |
| 2 | Wrapper heading/preamble is a **hardcoded** module constant (no YAML externalization). |
| 3 | Overlap with `qualitative_profile` is acceptable — transient run-time note vs. persistent CRM context; any residual overlap is safely handled by the LLM. |
| 4 | RM guidance is a **hard constraint** that overrides base task rules. |
| 5 | `rm_prompt` is implemented **independently of and before** the skill-reordering work; the two are treated as completely separate items. |