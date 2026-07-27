Product-Investor matcher
========================

# 1. Purpose

The current engine is composed of two proposals:

- `product_investor_matching`
- `client_product_fit_analysis`

Today, matching and investment recommendation quality depends heavily on LLM judgment. This document defines a refined mechanism that introduces deterministic scorecards before LLM reasoning, so that candidate selection is consistent and explainable.

# 2. Objectives

- Reduce false-positive recommendations by filtering low-readiness clients before proposal generation.
- Improve recommendation quality by combining deterministic scorecards with LLM qualitative reasoning.
- Keep existing two-stage proposal flow and required artifacts.
- Expose a FastAPI endpoint that executes the end-to-end flow in one request.

# 3. Scope

## In Scope

- Investor readiness score computation per client.
- Product fitness score computation per client-product pair.
- Use existing scorecard logic already implemented in API and documented under `docs/prod_spec/score_card`.
- LLM buying score generation using scorecards plus narrative context.
- Top-N candidate selection and markdown output.
- Pass markdown in-memory to `client_product_fit_analysis` (no temp file handoff).
- FastAPI endpoint orchestration and error handling.
- API retrieval of client and product information via interfaces defined under `docs/prod_spec/tool`.
- Readiness filtering policy is inherited from existing scorecard/API configuration behavior; this spec does not redefine thresholds/formulas.
- Tool contract (`docs/prod_spec/tool`) and runtime integration (`src/integrations`) are both mandatory and must remain synchronized.
- Empty-result behavior is standardized: return HTTP `200` with empty results and warning `NO_ELIGIBLE_CLIENTS` when no eligible clients are found after filtering.

## Out of Scope (Current Phase)

- Portfolio optimization and efficient frontier modeling.
- Full goal-based planning module.
- Real-time stream ingestion.

# 4. End-to-End Flow

1. API receives request containing product universe (or product IDs), client selection criteria, and execution options.
2. API retrieves/normalizes client and product data through the tool contracts in `docs/prod_spec/tool` (clients are not passed in request payload).
3. API computes investor readiness score for each client using the existing scorecard implementation documented in `docs/prod_spec/score_card/investor_readiness_score.md` (not delegated to LLM).
4. API filters clients using readiness output and filtering policy from existing scorecard configuration/API behavior (no new threshold design in this document).
5. For each remaining client, API computes product fitness score against all eligible products using the existing implementation documented in `docs/prod_spec/score_card/product_fitness_score.md`.
6. Build an LLM input package for each candidate pair with:
   - market outlook
   - bank product description
   - client profile and investment context
   - investor readiness score
   - product fitness score
7. LLM generates buying score and rationale.
8. Sort opportunities by buying score in descending order and select top-N candidates, where `N = top_n` from request input.
9. Output compact markdown from `product_investor_matching`.
10. Invoke `client_product_fit_analysis` with markdown payload in-memory.
11. Return final proposal markdown and JSON (per `docs/prod_spec/proposal_JSON_output_s1.md`) from API.

# 5. Scoring Design

## 5.1 Investor Readiness Score (Client-Level)

Use the existing readiness scorecard design and implementation as the source of truth:

- `docs/prod_spec/score_card/investor_readiness_score.md`
- Runtime/config behavior in the current API implementation and config files

Rules for this matcher spec:

- Do not redefine readiness dimensions, formula, or hardcoded thresholds here.
- Consume readiness outputs produced by the existing scorecard implementation.
- Any readiness filtering policy changes must be made in scorecard specs/config, not in this document.

## 5.2 Product Fitness Score (Client-Product-Level)

Use the existing product fitness scorecard design and implementation as the source of truth:

- `docs/prod_spec/score_card/product_fitness_score.md`
- Runtime/config behavior in the current API implementation and config files

Rules for this matcher spec:

- Do not redefine product fitness dimensions, formula, or weights here.
- Consume fitness outputs produced by the existing scorecard implementation.
- Any fitness scoring policy changes must be made in scorecard specs/config, not in this document.

## 5.3 LLM Buying Score

LLM should not replace deterministic filtering. It should rank only candidate pairs that pass threshold gates.

Input to LLM must include:

- Investor readiness score and component breakdown
- Product fitness score and component breakdown
- Relevant product constraints and suitability notes
- Market narrative and client investment narrative

Output per candidate must include:

- Buying score (0-100)
- Client ID
- Product ID
- Suggested investment amount
- Funding source
- Rationale (concise, evidence-based)

# 6. Data Contract

## 6.1 Request (FastAPI)

- `product_ids`: list[string], optional if `product_source=default_yaml`
- `product_source`: enum[`default_yaml`, `request_payload`], default `default_yaml`
- `client_selection`: optional object (for example region/RM/book filters) used by API when querying client API
- `top_n`: int, default 5, max configurable. This is the output limit `N` after descending score sort.
- `score_card_options`: optional object passed to existing scorecard implementations according to scorecard/API specs
- `market_context`: optional object/string

Data source rule:

- The API shall retrieve client information from client API and product information via tool definitions under `docs/prod_spec/tool`.
- Runtime integration APIs are implemented under `src/integrations` and must remain aligned with `docs/prod_spec/tool` contracts.
- The API shall use the existing scorecard logic and behavior documented under `docs/prod_spec/score_card`.
- Direct ad-hoc retrieval bypassing those tool contracts is out of scope.

## 6.2 Response

- `run_id`: string
- `summary`: object
- `product_investor_matching_markdown`: string
- `final_proposal_markdown`: string
- `final_proposal_json`: object (schema aligned to `proposal_JSON_output_s1.md`)
- `warnings`: list[string]
- `errors`: list[object]

# 7. Execution and Error Handling

- No clients after readiness filter:
  - return `200` with empty proposal payload and warning code `NO_ELIGIBLE_CLIENTS`
- Invalid request payload:
  - return `400` with validation errors
- Downstream data retrieval failure:
  - return `502` with source-specific error code
- LLM generation failure:
  - retry with bounded attempts; if still failed, return `503` with failure details

# 8. Sprint Plan

## Sprint 1 - End-to-end FastAPI

Deliverables:

- Integrate existing investor readiness scorecard implementation from `docs/prod_spec/score_card/investor_readiness_score.md`.
- Integrate existing product fitness scorecard implementation from `docs/prod_spec/score_card/product_fitness_score.md`.
- Do not introduce a new scorecard formula/threshold design in this flow spec.
- Refactor `client_product_fit_analysis` to consume markdown payload in-memory.
- Remove temp-file communication between stages.
- Tighten prompt instructions for concise and deterministic outputs.
- Expose FastAPI endpoint for full orchestration.
- Integrate client/product retrieval using `docs/prod_spec/tool` contract.

Acceptance Criteria:

| AC ID | Criterion |
| --- | --- |
| AC1 | API returns proposal artifacts for valid requests. |
| AC2 | Readiness filter is enforced before LLM ranking. |
| AC2a | Scorecard computations are executed by existing API scorecard logic (deterministic), not by LLM. |
| AC2b | Client/product retrieval follows `docs/prod_spec/tool` contract. |
| AC2c | Clients are not accepted as direct request input; they are retrieved via client API according to selection criteria. |
| AC2d | No new scorecard dimensions/formulas/thresholds are introduced in this matcher spec; existing `docs/prod_spec/score_card` definitions are used. |
| AC3 | Output markdown contains Buying Score, Client ID, Product ID with investment amount, Funding source, and Rationale. |
| AC3a | Results are sorted by Buying Score in descending order. |
| AC3b | Output includes at most top-N records where `N = top_n`. |
| AC4 | `client_product_fit_analysis` successfully consumes stage-1 markdown and emits final proposal markdown + JSON. |
| AC5 | No temporary file is used for stage-to-stage handoff. |
| AC6 | Common exceptions are returned with explicit error codes/messages. |

## Sprint 2 - Product Fitness Score Integration

Status: deferred for now.

Planned items:

- Add deterministic product fitness score computation.
- Extend LLM prompt to incorporate product fitness breakdown.
- Introduce calibration tests for buying score stability.

# 9. Testing Requirements

- Unit tests for readiness score:
  - normal scenario
  - boundary/exception scenario
- Unit tests for product fitness score:
  - normal scenario
  - invalid product/client data scenario
- API integration tests:
  - successful end-to-end flow
  - no eligible clients
  - downstream dependency failure
- Output contract tests for final JSON schema compatibility.

# 10. Traceability to Existing References

- Flow alignment with `docs/prod_spec/product_client_matching.d2`
- Final JSON compatibility with `docs/prod_spec/proposal_JSON_output_s1.md`
- Qualitative suitability cues can reuse matrix guidance in `docs/prod_spec/qualitative_matching_matrix.md`
- Client/product data retrieval contract alignment with `docs/prod_spec/tool`
- Client/product integration implementation reference: `src/integrations`
- Investor readiness score source of truth: `docs/prod_spec/score_card/investor_readiness_score.md`
- Product fitness score source of truth: `docs/prod_spec/score_card/product_fitness_score.md`

# 11. Open Issues for Further Discussion

| ID | Topic | Current Proposal | Why Discussion Is Needed | Suggested Direction |
| --- | --- | --- | --- | --- |
| O2 | Buying Score Governance | LLM ranks only post-filter candidates with deterministic score inputs | Need policy on how much buying score can override low qualitative confidence or suitability flags | For current phase, grant LLM full authority to adjust final score/ranking after deterministic pre-filtering of clients/products. Revisit and finalize governance rule after test results (quality, consistency, and risk review). |
| O3 | Investment Amount Logic | LLM suggests amount with funding source rationale | Need deterministic caps/rules (for example % of liquid assets, concentration limits) to prevent over-allocation | For current phase, allow LLM to decide suggested investment amount/funding source. Rationale: product fitness already includes concentration dimension. Revisit need for deterministic caps after test outcomes and proposal quality review. |
