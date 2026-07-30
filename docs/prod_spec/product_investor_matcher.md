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
4. API filters clients to top-K by investor readiness score (descending), where `K` is a standalone config value `default_number_of_candidates_from_investor_readiness` defined in `config/config_planbot.yaml` under `product_investor_matching.matcher`. Default: `K = 20` (or all clients if fewer exist).
5. For each remaining client, API computes product fitness score against all eligible products using the existing implementation documented in `docs/prod_spec/score_card/product_fitness_score.md`.
6. Build an LLM input package for each candidate pair using the in-memory payload builder ``build_matcher_llm_payload()`` in ``src/planbot/workflow.py`` (same pattern as the reinvestment proposal's ``build_llm_input`` — no temp files). The payload includes:
   - market outlook (from request `market_outlook`)
   - `product.investment_note` (house-view narrative from product API)
   - `client.qualitative_profile` (RM notes from client API)
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
- `client_selection`: optional object passed through to client API `search` endpoint as filter criteria. Supported keys are limited to the current client API contract: `risk_rating`, `age`, `product_types_in_holdings`, `concentration_score`, `cash_score`. Additional keys are ignored in Sprint 1.
- `top_n`: int, default 5, max configurable. This is the output limit `N` after descending score sort.
- `market_outlook`: optional object/string. When provided, it is passed to the LLM input package as market context. When absent, fall back to the file-globbed market outlook from `config/config_planbot.yaml` under `product_investor_matching.references.market_outlook` (same pattern as other proposals). The in-memory payload builder loads these files at runtime — no temp files.

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
  - return `422` with validation errors
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
- Handle empty-result cases explicitly:
  - no clients retrieved from client API
  - clients retrieved but none pass readiness filtering

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
| AC7 | When client API returns no clients, matcher returns HTTP `200` with empty results and warning code `NO_CLIENTS_RETRIEVED`. |
| AC8 | When clients are retrieved but none pass readiness filtering, matcher returns HTTP `200` with empty results and warning code `NO_ELIGIBLE_CLIENTS`. |

## Sprint 2 - Quality and Observability Hardening

Sprint 2 Objective:

- Harden quality, governance, and observability of the end-to-end matcher while keeping current LLM-first decision policy for O2 and O3.

Deliverables:

- Ensure product fitness score outputs (score + component breakdown) are consistently fed into LLM input context for ranking and rationale generation.
- Add score/ranking calibration test suite to measure run-to-run stability and recommendation quality.
- Add proposal quality evaluation rubric for business review (rationale quality, suitability consistency, and funding source coherence).
- Add observability fields in output metadata for auditability:
  - scorecard version references
  - prompt version/tag
  - ranking inputs used (readiness score, fitness score, LLM buying score)
- Refine LLM prompts to be concise, deterministic in structure, and explicit about required output sections.
- Define decision gate from test results for O2 and O3:
  - either keep current LLM-first policy
  - or introduce deterministic guardrails/caps in the next sprint

Acceptance Criteria:

| AC ID | Criterion |
| --- | --- |
| S2-AC1 | Product fitness score and component breakdown are present in LLM input payload for all ranked candidates. |
| S2-AC2 | Calibration suite is implemented and produces repeatable metrics for ranking stability and output quality. |
| S2-AC3 | Prompt revisions are applied and required output sections are consistently populated (no empty required sections). |
| S2-AC4 | Response metadata includes scorecard references and prompt version/tag sufficient for audit/replay analysis. |
| S2-AC5 | Test report explicitly evaluates O2 (score governance) and O3 (amount logic) and recommends keep/adjust decision. |
| S2-AC6 | If quality thresholds are met, current LLM-first policy for O2 and O3 is retained for the next release; otherwise a follow-up change request is created for deterministic guardrails. |

## Sprint 3 - Governance and Contract Hardening

Sprint 3 Objective:

- Resolve the remaining outstanding implementation items by formalizing governance, metadata, client-selection, and context contracts.

Deliverables:

- Decide and implement the final buying-score governance rule for O2.
- Decide and implement the final investment-amount governance rule for O3.
- Define numeric quality thresholds and pass/fail metrics for Sprint 2 exit criteria.
- Extend response contract with audit/replay metadata fields.
- Finalize client-selection schema against the supported client API contract.
- Finalize minimum client/product context fields required for LLM rationale generation.

Acceptance Criteria:

| AC ID | Criterion |
| --- | --- |
| S3-AC1 | Final buying-score governance for O2 is implemented and reflected in the matcher flow and tests. |
| S3-AC2 | Final investment-amount governance for O3 is implemented and reflected in the matcher flow and tests. |
| S3-AC3 | Sprint 2 quality thresholds are defined numerically and can be executed as a pass/fail decision gate. |
| S3-AC4 | Response metadata includes the agreed audit/replay fields and is returned by the API. |
| S3-AC5 | Client-selection inputs are aligned to the supported client API contract and validated by tests. |
| S3-AC6 | Minimum client/product context payloads are defined and used by the matcher and proposal generation flow. |

# 9. Sprint 1 Implementation Notes

(All implementation notes resolved — no open issues for Sprint 1.)

# 10. Testing Requirements

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

# 11. Traceability to Existing References

- Flow alignment with `docs/prod_spec/product_client_matching.d2`
- In-memory LLM payload builder: `src/planbot/workflow.py` → `build_matcher_llm_payload()` (same pattern as reinvestment proposal's `build_llm_input`)
- Final JSON compatibility with `docs/prod_spec/proposal_JSON_output_s1.md`
- Qualitative suitability cues can reuse matrix guidance in `docs/prod_spec/qualitative_matching_matrix.md`
- Client/product data retrieval contract alignment with `docs/prod_spec/tool`
- Client/product integration implementation reference: `src/integrations`
- Investor readiness score source of truth: `docs/prod_spec/score_card/investor_readiness_score.md`
- Product fitness score source of truth: `docs/prod_spec/score_card/product_fitness_score.md`

# 12. Open Issues for Further Discussion

| ID | Topic | Current Proposal | Why Discussion Is Needed | Suggested Direction |
| --- | --- | --- | --- | --- |
| O2 | Buying Score Governance | LLM ranks only post-filter candidates with deterministic score inputs | Need policy on how much buying score can override low qualitative confidence or suitability flags | Handle in Sprint 3: define and implement the final buying-score governance rule after the current LLM-first phase. |
| O3 | Investment Amount Logic | LLM suggests amount with funding source rationale | Need deterministic caps/rules (for example % of liquid assets, concentration limits) to prevent over-allocation | Handle in Sprint 3: define and implement the final investment-amount governance rule after the current LLM-first phase. |
| O5 | Sprint 2 Quality Threshold Definition | S2-AC6 references "if quality thresholds are met" | No numeric thresholds or pass/fail metrics are currently defined, so sprint exit is not objectively testable | Handle in Sprint 3: define numeric quality thresholds and pass/fail metrics for the Sprint 2 exit gate. |
| O6 | Response Metadata Contract for Auditability | Sprint 2 expects metadata (scorecard refs, prompt version/tag, ranking inputs) | Response schema section does not explicitly define where these fields are returned | Handle in Sprint 3: extend the response contract with audit/replay metadata fields. |
| O8 | Client Selection Contract Gap | Request section references `client_selection` examples such as region/RM/book filters | Current client API contract does not clearly support full RM/book-style filters, creating implementation mismatch for request handling | Handle in Sprint 3: finalize client-selection schema against the supported client API contract. |
