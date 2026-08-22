# Proposal Pipeline Concept Draft

Date: 2026-08-06  
Status: Draft concept for discussion

---

## 1. Purpose

Define a proposal pipeline architecture that modernizes proposal generation while preserving current PlanBot behavior.

This draft is intentionally architecture-first and implementation-oriented. It focuses on the contract between YAML configuration, shared runtime resolution, and proposal output generation.

---

## 2. Design Intent

The proposal pipeline should:

1. Use a single execution backbone for all proposal types.
2. Keep proposal-specific differences in YAML configuration.
3. Support both runtime API data and file-glob references with predictable fallback.
4. Treat prior-step outputs as optional or required through explicit policy.
5. Produce similar proposal output quality with a simpler, intuitive configuration model.

### 2.1 Design principles

The pipeline should be fully configuration-driven so adding or changing a proposal does not require new Python branching logic. In practice, this means:

1. Proposal-specific prompt sections are declared in YAML and treated as the source of truth for behavior.
2. Shared Python code provides slot resolvers, formatters, and execution orchestration only.
3. Optional sections that depend on previous function calls use explicit policy such as `skip`, `fallback_to_static`, or `error`.
4. A new proposal type is primarily a configuration change plus content assets rather than a new orchestration branch.

### 2.2 Current proposal data input landscape

The current implementation already converges through a common execution path. The remaining differences are primarily in per-proposal resolver wrappers that hardcode what to include and when.

#### Runtime resolver paths

| `api://` path | Reinvestment | Product Opp. | Matcher |
|---|---|---|---|
| `client_profile` | ✅ `format_client_and_holdings(cp, extra=…)` | ✅ `format_client_and_holdings(cp)` | ✅ `format_client_and_holdings(cp, extra=…)` |
| `product_catalog` | ✅ `format_product_catalog(suggested, holdings, alts, pfs)` | ✅ same | ❌ `format_product_multi()` |
| `suggested_products_and_rationale` | — | ✅ gated via extra docs | — |
| `market_outlook` | — (YAML glob) | ✅ when provided | ✅ when provided |

#### What the LLM currently receives

| Section | Reinvestment | Product Opp. | Matcher | Shared function? |
|---|---|---|---|---|
| Task prompt | ✅ | ✅ | ✅ | ✅ `tasks.yaml` |
| Proposal instructions | ✅ | ✅ | ✅ | ✅ `load_references` |
| Guidelines | ✅ | ✅ | ✅ | ✅ `load_references` |
| Client profile (composite: includes holdings) | ✅ | ✅ | ✅ | ✅ `format_client_and_holdings` |
| Investor Readiness Score | ✅ | ❌ | ✅ | ✅ `format_irs_section` |
| Wallet Inflow Event | ✅ | ❌ | ❌ | ❌ wrapper-only |
| Product catalog (composite: suggested + holdings + alts) | ✅ | ✅ | ❌ multi | ✅ `format_product_catalog` |
| Multi-product listing | ❌ | ❌ | ✅ | ❌ `format_product_multi` |
| Product Fitness Scores | ✅ | ✅ | ✅ | ✅ `format_pfs_table` |
| Suggested products and rationale | ❌ | ✅ gated | ❌ | ❌ wrapper-only |
| Market outlook | ✅ YAML glob | ✅ API or YAML glob | ✅ API or YAML glob | ✅ `load_references` |

### 2.3 Current gaps to address

1. Matcher still uses a different product-catalog structure from the other proposals.
2. Product opportunity currently has no IRS section by default.
3. Proposal differences still live in Python wrapper logic rather than in a shared declarative contract.
4. Per-target and per-pair processing still carries duplicated control flow.
5. The formatting layer should converge on a small set of shared `format_*` helpers per logical data type, such as client profile, wallet inflow event, holdings table, product catalog, and PFS sections, so proposal-specific rendering is driven by data shape rather than bespoke wrapper logic.

---

## 3. Current Implementation Baseline (As-Is)

The concept is anchored to the current implementation:

1. Core proposal generation already converges through `run_crew_planbot`.
2. Reference loading supports both file globs and `api://` resolver paths.
3. Runtime reference overrides are already used for proposal-specific injection.
4. Proposal-specific resolver wrappers still contain hardcoded branching for section assembly.
5. Existing `config_planbot.yaml` defines proposal metadata, reference groups, model settings, and some matcher behavior.
6. Legacy CLI run configuration exists but API-driven flows are now primary.

This means the pipeline revamp should preserve runtime behavior and output shape, while allowing a cleaner configuration schema.

---

## 4. Core Concept

Proposal Pipeline is a configuration-driven context assembly and generation flow:

1. Intake
2. Context hydration
3. Input-based content assembly
4. Reference resolution (runtime + file fallback)
5. Prompt compilation
6. LLM generation
7. Output normalization and artifact emission

### 4.1 Pipeline object model

1. `ProposalRequest`
   - proposal name
   - seed identifiers (client/product)
   - optional runtime context from previous functions

2. `RuntimeContext`
   - hydrated entities (client profile, holdings, products)
   - computed scores (IRS/PFS)
   - optional upstream artifacts (for example matcher rationale markdown)

3. `PromptAssemblyPlan`
   - loaded from proposal YAML section
   - defines inputs and policies for missing data

4. `CompiledPromptPayload`
   - task prompt
   - reference sections payload
   - runtime override manifest

---

## 5. Pipeline Stages

### 5.1 Stage A: Intake and validation

Validates request shape and determines execution mode:

1. API-first mode (runtime resolver)
2. File-glob fallback mode
3. Hybrid mode (runtime where present, static refs otherwise)

### 5.2 Stage B: Context hydration

Hydrates normalized runtime context from available providers:

1. Client profile and holdings
2. Source and candidate products
3. Market outlook
4. Readiness and fitness score artifacts
5. Prior-step proposal artifacts when provided

### 5.3 Stage C: Input-based assembly

Builds prompt payload by reading configured inputs in order:

1. instruction inputs
2. context inputs
3. supporting document inputs

Each input applies policy for missing data:

1. `skip`
2. `fallback_to_static`
3. `error`

### 5.4 Stage D: Reference resolution

Produces final prompt inputs for the compiler:

1. Mandatory runtime overrides are injected.
2. Conditional runtime overrides are injected only when resolved.
3. Unresolved conditional docs fall back to static reference globs when configured.

### 5.5 Stage E: Prompt compilation and generation

Compiles task prompt plus reference payload and invokes CrewAI generation with configured model.

### 5.6 Stage F: Output and diagnostics

Produces:

1. final markdown output
2. prompt snapshot artifact
3. structured execution metadata
4. logs for input outcomes and override decisions

---

## 6. Configuration Model

The pipeline should move to one simple proposal configuration model with these top-level blocks:

1. proposal identity and request contract
2. execution settings
3. unified inputs (sections + references)
4. input policy
5. prompt packaging
6. quality gates

### 6.1 Conceptual schema (simplified)

The proposal configuration lives under two top-level keys in
`config/config_planbot.yaml`: `input_defaults` (shared, once) and `pipeline`
(one key per proposal type). The pipeline key **is** the proposal id — there is
no nested `proposal.id`/`proposal.name` object.

```yaml
# ── input_defaults: shared across all proposals (defined once) ──────────────
input_defaults:
   global:
      prompt_section: references
      required: false
   by_id:
      client_profile: { source: api, prompt_section: decision_context }
      product_catalog: { source: api, prompt_section: decision_context }
      # ... other known runtime-resolved ids

# ── pipeline: one key per proposal type ─────────────────────────────────────
pipeline:
   <proposal_id>:
      request_contract:
         required: [..]
         optional: [..]

      execution:
         model: <model_key>
         output:
            folder: <output_folder>
            filename_template: <template>
         logging:
            level: INFO

      inputs: [ ... ]           # unified sections + references

      input_policy:
         missing_data:
            default: <skip|error>
         per_input: { ... }

      prompt_packaging:
         decision_context_order: [ ... ]
         references_order: [ ... ]
         llm_payload:
            include_references: true

      quality_gates:
         required_sections: [ ... ]
         fail_on_missing_required_input: true
```

Each `inputs` entry is a mapping with an `id` plus optional `source`, `paths`,
`prompt_section`, `required`, and `source_priority`; omitted keys fall back to
`input_defaults.by_id`, then `input_defaults.global`, then the engine default
(see Section 6.5).

The task prompt (what the model must do) is sourced from `tasks.yaml`
`description:`, matching CrewAI's native `Task.description`. The `inputs` list
carries reference material (including `proposal_instructions` format files); it
does not supply the task prompt.

### 6.2 Sample YAML: Reinvestment Proposal

```yaml
pipeline:
   reinvestment:
      request_contract:
         required:
            - client_id
            - source_product_id
         optional:
            - market_outlook_text

      execution:
         model: deepseek_tool
         output:
            folder: runs/reinvestment_proposal
            filename_template: reinvestment_{client_id}_{date}.md
         logging:
            level: INFO

      inputs:
         - id: proposal_instructions
           source: file
           paths:
              - data/planbot/reinvestment_proposal/proposal_instructions/*.md
           prompt_section: references
           required: true

         - id: section_guides
           source: file
           paths:
              - data/planbot/shared/proposal_section_instructions/*.md
           prompt_section: references
           required: true

         - id: general_guidelines
           source: file
           paths:
              - data/planbot/shared/common/general_guideline.md
           prompt_section: references
           required: true

         - id: financial_needs_guidelines
           source: file
           paths:
              - data/planbot/shared/financial_needs/*.md
           prompt_section: references
           required: true

         - id: client_profile
           required: true
           # source/api + prompt_section/decision_context come from input_defaults.by_id;
           # composite: always includes holdings table

         - id: investor_readiness_score
           # optional — omitted required defaults to false

         - id: wallet_inflow_event
           required: true

         - id: product_catalog
           required: true
           # composite: always includes suggested product + holdings in catalog + alternatives

         - id: product_fitness_scores

         - id: market_outlook
           source_priority:
              - request.market_outlook_text
              - data/planbot/shared/market_outlook/*.md

      input_policy:
         missing_data:
            default: error
         per_input:
            investor_readiness_score: skip
            market_outlook: fallback_to_static
            product_fitness_scores: skip

      prompt_packaging:
         decision_context_order:
            - client_profile
            - investor_readiness_score
            - wallet_inflow_event
            - product_catalog
            - product_fitness_scores
            - market_outlook
         references_order:
            - proposal_instructions
            - section_guides
            - general_guidelines
            - financial_needs_guidelines
         llm_payload:
            include_references: true

      quality_gates:
         required_sections:
            - client_profile
            - wallet_inflow_event
            - product_catalog
         fail_on_missing_required_input: true
```

### 6.3 Why this model is intuitive

1. Proposal setup reads top-to-bottom like execution flow.
2. One unified `inputs` list removes duplicated concepts between decision context and references.
3. `prompt_section` makes packaging intent explicit (`decision_context` vs `references`).
4. `id` is the stable semantic key and implicit API plus formatter selector in shared code.
5. Missing-data behavior is visible per input, not hidden in code.
6. `client_profile` and `product_catalog` are composite IDs — each backed by a single shared formatter that returns multiple logical sub-parts in one call. The pipeline does not need separate IDs for holdings, suggested product, holdings-in-catalog, or alternatives.

### 6.4 Fixed runtime source and enrichment (Sprint 1)

For Sprint 1, runtime data retrieval and enrichment should be fixed in shared code, not configured per proposal.

1. Input rows with `source: api` are resolved by a centralized resolver layer.
2. Proposal YAML should not carry provider/method boilerplate when there is only one supported source path.
3. Re-externalize source/enrichment only when genuine multi-source variation is needed.

### 6.4.1 Sprint 1 mapping assumption

For Sprint 1, API selection and formatter selection are both driven by `id`.

1. Each runtime-resolved `id` maps to one shared API retrieval path.
2. Each `id` also maps to one shared formatter in code.
3. The current model assumes a one-to-one mapping between `id`, API path, and formatter.
4. Proposal YAML selects which inputs are needed, but does not choose among multiple APIs or multiple formatters for the same `id`.
5. If future requirements need multiple APIs or render styles for one logical input, the schema can be extended later.

### 6.5 Defaults and shorthand to reduce boilerplate

To keep production YAML concise, the pipeline should support default field values when keys are omitted.

`input_defaults` lives in `config/config_planbot.yaml` as a top-level `input_defaults` block, shared by all proposals. At load time, the pipeline reads the defaults, then overlays the proposal-specific YAML on top.

Suggested default values:

1. `prompt_section: references`
2. `required: false`
3. `source: file` when `paths` is present
4. `source: api` when the `id` is a known runtime-resolved input
5. `source: runtime_or_static` when `source_priority` is present
6. `input_policy.missing_data.default: skip`

Recommended precedence order:

1. Explicit value on the input row
2. `input_defaults.by_id` value
3. `input_defaults.global` value
4. Engine hard default

Compact YAML pattern:

```yaml
schema_version: 1

input_defaults:
   global:
      prompt_section: references
      required: false
   by_id:
      client_profile:
         source: api
         prompt_section: decision_context
         # composite: always includes holdings
      investor_readiness_score:
         source: api
         prompt_section: decision_context
      wallet_inflow_event:
         source: api
         prompt_section: decision_context
      product_catalog:
         source: api
         prompt_section: decision_context
         # composite: always includes suggested + holdings in catalog + alternatives
      product_fitness_scores:
         source: api
         prompt_section: decision_context
      market_outlook:
         source: runtime_or_static

input_policy:
   missing_data:
      default: skip
   per_input:
      client_profile: error
      product_catalog: error

inputs:
   - id: proposal_instructions
      paths:
         - data/planbot/reinvestment_proposal/proposal_instructions/*.md

   - id: client_profile
      required: true

   - id: market_outlook
      source_priority:
         - request.market_outlook_text
         - data/planbot/shared/market_outlook/*.md
```

This keeps configuration intuitive while avoiding repetitive fields on most input rows.

### 6.5.1 Compact example: Product opportunity proposal

The following example intentionally omits keys when defaults already provide the desired behavior.

```yaml
schema_version: 1

# shared defaults, defined once for all proposal configurations
input_defaults:
   global:
      prompt_section: references
      required: false
   by_id:
      client_profile: { source: api, prompt_section: decision_context, note: "composite: includes holdings" }
      investor_readiness_score: { source: api, prompt_section: decision_context }
      product_catalog: { source: api, prompt_section: decision_context, note: "composite: includes suggested + holdings + alternatives" }
      product_fitness_scores: { source: api, prompt_section: decision_context }
      suggested_products_and_rationale: { source: runtime_or_static, prompt_section: references }
      market_outlook: { source: runtime_or_static, prompt_section: references }

proposal:
   id: product_opportunity_proposal
   name: Product Opportunity Proposal

request_contract:
   required:
      - client_id
      - product_id
   optional:
      - suggested_products_and_rationale
      - market_outlook_text
      - alternative_count

execution:
   model: deepseek_tool
   output:
      folder: runs/product_opportunity_proposal
      filename_template: product_opportunity_{client_id}_{date}.md

input_policy:
   missing_data:
      default: skip
   per_input:
      client_profile: error
      product_catalog: error
      suggested_products_and_rationale: fallback_to_static
      market_outlook: fallback_to_static

inputs:
   - id: proposal_instructions
      required: true
      paths:
         - data/planbot/product_opportunity_proposal/proposal_instructions/*.md

   - id: section_guides
      required: true
      paths:
         - data/planbot/shared/proposal_section_instructions/*.md

   - id: general_guidelines
      required: true
      paths:
         - data/planbot/shared/common/general_guideline.md

   - id: financial_needs_guidelines
      required: true
      paths:
         - data/planbot/shared/financial_needs/*.md

   - id: client_profile
      required: true

   - id: investor_readiness_score

   - id: product_catalog
      required: true

   - id: product_fitness_scores

   - id: suggested_products_and_rationale
      source_priority:
         - request.suggested_products_and_rationale
         - data/planbot/product_opportunity_proposal/suggested_products/*.md

   - id: market_outlook
      source_priority:
         - request.market_outlook_text
         - data/planbot/shared/market_outlook/*.md

prompt_packaging:
   decision_context_order:
      - client_profile
      - investor_readiness_score
      - product_catalog
      - product_fitness_scores
   references_order:
      - proposal_instructions
      - section_guides
      - general_guidelines
      - financial_needs_guidelines
      - suggested_products_and_rationale
      - market_outlook
   llm_payload:
      include_references: true

quality_gates:
   required_sections:
      - client_profile
      - product_catalog
   fail_on_missing_required_input: true
```

Notes on omitted keys:

1. Most runtime business inputs omit `source` because `input_defaults.by_id` already maps them to `api`.
2. Decision-critical inputs omit `prompt_section` because `input_defaults.by_id` already maps them to `decision_context`.
3. Optional inputs omit `required` because the global default is `false`.
4. `suggested_products_and_rationale` and `market_outlook` only specify `source_priority` because their `source` and `prompt_section` are already defaulted.
5. `client_profile` and `product_catalog` are composite IDs — each is backed by a single API call that returns multiple logical sub-parts.

### 6.6 Quality gate semantics

Quality gates validate the **assembled prompt content**, not the LLM output. The check runs at the end of Stage D (Reference resolution), before LLM generation: if a required input resolved successfully and is present in the compiled prompt, the gate passes. Post-hoc checking of LLM output belongs in a separate validation layer and is not part of this pipeline.

The key `fail_on_empty_required_section` is renamed to `fail_on_missing_required_input` to avoid ambiguity about what is being validated.

### 6.7 `source_priority` and `missing_data` interaction

When an input has `source: runtime_or_static`, it carries a `source_priority` chain. The same input can also have an entry in `input_policy.missing_data.per_input`. The evaluation order is:

1. Walk the `source_priority` chain top to bottom.
2. If a source resolves, stop and use it — `missing_data` policy does not fire.
3. If the entire chain is exhausted without resolution, consult `input_policy.missing_data.per_input[id]` (falling back to `.default`) and apply `skip`, `fallback_to_static`, or `error` per that policy.

`source_priority` defines *what to try*; `missing_data` defines *what to do when everything fails*.

---

## 7. Handling Prior-Function Dependencies

Some proposal sections come from previous function calls and may be absent for certain runs.

The concept resolves this with input-policy behavior, not proposal-specific branching:

1. If upstream section exists, inject via runtime doc override.
2. If upstream section is missing and input policy is `fallback_to_static`, use configured file glob.
3. If upstream section is missing and policy is `skip`, omit section.
4. If upstream section is missing and policy is `error`, fail deterministically.

This is the core mechanism that prevents unnecessary hard dependencies between proposal stages.

---

## 8. Proposal Types in Scope

### 8.1 Reinvestment proposal

Expected assembly pattern:

1. client profile + holdings
2. IRS (when available)
3. wallet inflow event
4. suggested product + alternatives + PFS
5. market outlook (runtime or static)

### 8.2 Product opportunity proposal

Expected assembly pattern:

1. client profile + holdings
2. IRS (policy-controlled)
3. suggested product + alternatives + PFS
4. suggested_products_and_rationale (runtime if available; static fallback)
5. market outlook (runtime or static)

### 8.3 Product investor matching

The matcher is structurally different from single-client proposals: it pre-fetches all eligible clients, runs PFS as a client × product matrix, and builds a closure-based resolver that returns multi-client content from a single `api://client_profile` call. Multi-client iteration is owned by the resolver implementation, not by YAML configuration.

Expected assembly pattern:

1. multi-client profile blocks (all clients concatenated by the resolver)
2. readiness framing per client
3. product universe view with PFS per client (appended by the resolver)
4. market outlook (runtime or static)

`request_contract` for the matcher accepts `client_selection` criteria rather than a single `client_id`.

---

## 9. Runtime Contracts

### 9.1 Input contract

The proposal pipeline accepts:

1. proposal identity
2. required seed IDs
3. optional runtime artifacts from upstream steps
4. execution options (output mode, debug flags)

### 9.2 Output contract

The proposal pipeline returns:

1. generation status (`success`, `partial_error`, `error`)
2. proposal outputs (path and/or markdown)
3. optional diagnostics
4. stable error codes for assembly failures

---

## 10. Reliability and Observability Principles

1. Every input resolution is logged as `resolved`, `skipped`, `fallback`, or `error`.
2. Runtime override decisions are logged explicitly.
3. Failures use stable machine-readable error codes:
   - `REQUIRED_INPUT_MISSING` — a `required: true` input failed resolution.
   - `RUNTIME_DOC_REQUIRED_MISSING` — an upstream doc with `if_missing: error` was absent.
   - `QUALITY_GATE_FAILED` — a required input was missing at the quality gate check.
   - `RESOLUTION_FALLBACK_EXHAUSTED` — a `source_priority` chain ran dry with policy `error`.
4. Non-critical missing context should fail-soft only when policy permits.

---

## 11. Backward Compatibility

Backward compatibility of legacy YAML shape is not a goal in this concept.

What should be preserved:

1. Similar proposal output content and section completeness.
2. Existing API-level behavior expected by proposal callers.
3. Ability to use both runtime inputs and static references where needed.

---

## 12. Non-Goals (This Draft)

This document does not define:

1. code-level class diagrams
2. detailed sprint task breakdown
3. exact method signatures
4. specific refactor sequencing by file
5. migration adapters for legacy YAML schema

Those should be defined in a separate implementation plan after concept approval.

---

## 13. Conceptual Success Criteria

The concept is successful when:

1. Proposal behavior differences are strictly YAML-declared inputs and policies.
2. Prior-function-derived sections no longer require hardcoded per-proposal branching.
3. Runtime and static references coexist under explicit policies.
4. New proposal onboarding requires configuration and content authoring, not custom orchestration logic.

### 13.1 Acceptance criteria — proposal generation tests

The following tests serve as the minimal regression gate for the pipeline refactor. Each proposal type has one normal-flow and one exception-flow test, matching the project convention of two tests per component.

**AC-13-01 Reinvestment proposal (normal flow)**
- Given a valid `client_id` and `source_product_id` with all required runtime inputs resolvable
- When the reinvestment proposal pipeline runs
- Then the run completes with `status: success`
- And the output markdown contains `client_profile`, `wallet_inflow_event`, and `product_catalog` sections
- And no error codes are present in diagnostics

**AC-13-02 Reinvestment proposal (exception flow)**
- Given a `client_id` that does not exist or a `source_product_id` with no matching product
- When the reinvestment proposal pipeline runs
- Then the run fails with `REQUIRED_INPUT_MISSING` or produces `status: partial_error` with diagnostics identifying the missing input

**AC-13-03 Product opportunity proposal (normal flow)**
- Given a valid `client_id` and `product_id` with all required runtime inputs resolvable
- When the product opportunity pipeline runs
- Then the run completes with `status: success`
- And the output markdown contains `client_profile` and `product_catalog` sections

**AC-13-04 Product opportunity proposal (exception flow)**
- Given a `suggested_products_and_rationale` is missing and input policy is `fallback_to_static`
- When the product opportunity pipeline runs
- Then the run completes successfully using the static fallback glob
- And logs record the resolution outcome as `fallback` for that input

**AC-13-05 Product investor matcher (normal flow)**
- Given valid `product_ids` and `client_selection` criteria returning at least one eligible client
- When the matcher pipeline runs
- Then the run completes with `status: success`
- And the output markdown contains multi-client profile blocks and per-client PFS tables

**AC-13-06 Product investor matcher (exception flow)**
- Given `client_selection` criteria that return zero eligible clients
- When the matcher pipeline runs
- Then the run completes with `status: warning` and `NO_ELIGIBLE_CLIENTS` in warnings

**AC-13-07 Legacy YAML sections removed**
- Given the pipeline migration is complete
- When `config/config_planbot.yaml` is loaded
- Then no top-level sections named `reinvestment_proposal`, `product_investor_matching`, `product_opportunity_proposal`, or `portfolio_review` exist
- And proposal configuration for these types lives exclusively under the top-level `pipeline` block
- And `stock_analysis_proposal` may remain as a legacy section until it is migrated to the pipeline

---

## 14. Resolved design choices captured in this spec

The following architectural choices are now explicitly embodied in this specification and do not require further debate before implementation:

1. Resolution behavior is determined by the input definition and the input-policy model in Section 7. Each input declares its `source`, and the engine applies the configured fallback behavior when a runtime payload is absent.
2. Proposal behavior is driven by YAML configuration. Proposal-specific differences are expressed through input selection, policies, packaging order, and quality gates rather than custom Python branching.
3. Shared runtime logic owns retrieval and formatting. Proposal YAML selects which inputs matter, while shared resolvers and `format_*` helpers handle the common rendering path for logical data types.
4. The matcher is treated as a first-class proposal variant within the same schema model, with differences expressed by configuration rather than hardcoded wrapper behavior.
5. The implementation path should preserve current output shape while introducing a cleaner configuration contract and a clear migration boundary for legacy wrapper logic.

## 15. Open issues for discussion before implementation

*All issues resolved. Section retained for future items.*


## 16. Cross-Reference

This concept is aligned with the operational proposal metadata in `config/config_planbot.yaml` and uses YAML as the primary contract for proposal behavior. The document is intended to stand on its own as the canonical design reference for the pipeline model and should remain the basis for subsequent implementation planning.

---

## 17. Implementation review — outstanding objectives

The following spec objectives are not yet implemented (beyond the legacy-section removal captured in AC-13-07). These are tracked here for discussion before the next implementation pass.

2. **Quality gates are not enforced at runtime.** Section 6.6 / 5.4 require `fail_on_missing_required_input` to reject a run when a required input is missing. `prepare()` never calls `_check_quality_gates`; only the unused `run()` does.

3. **Stage E–F (compilation/generation + output/diagnostics) is dead code.** Section 5.5 / 5.6. Wrappers only call `prepare()`; `run()` and `_run_pipeline()` (the temp-config-file path) are unreachable.

4. **`portfolio_review` is not migrated.** `portfolio_review.py` still uses `proposal_name="portfolio_review"` with no `PipelineEngine` integration.

5. **Stable error codes never reach API callers.** Section 9.2 / 10 define `{code, message}` errors, but wrappers catch exceptions and emit `str(exc)`, so the structured contract is lost.

6. **Stage F diagnostics are discarded.** `_resolve_inputs` builds a `resolution_log`, but `prepare()` drops it; per-input outcomes are not surfaced to the output.

## 18. Implementation review — overlooked spec issues

The following are internal inconsistencies or gaps in the specification itself, identified during implementation review.

A. **§6.5 "Compact YAML pattern" and §6.5.1 are stale.** They still show the old `schema_version` + `proposal: {id, name}` object form, contradicting the `pipeline:`-keyed §6.1/§6.2.

B. **§6.4.1 "one-to-one `id` ↔ API ↔ formatter" is violated.** `investor_readiness_score`, `wallet_inflow_event`, and `product_fitness_scores` have no standalone formatter or API path — they are baked into the composite `format_client_and_holdings` / `format_product_catalog`. The engine's `_resolve_api` marks them "pending" with no real resolution path.

C. **`decision_context_order` / `references_order` are decorative.** The YAML declares them and `prepare()` returns them, but the wrappers rebuild their own section maps by iterating `pipeline_engine.inputs` with hardcoded id→legacy-section logic. The ordering fields have no effect.

D. **`request_contract.required` is never validated.** Section 5.1 "Stage A: Intake and validation" is unimplemented — `prepare()` does not check that required seed IDs (`client_id`, `source_product_id`, …) are present.

E. **`input_policy.missing_data.default: error` cannot fire for `api` inputs.** API inputs are marked `pending` (not `error`), so a `default: error` policy is meaningless for them; it only guards `file` / `runtime_or_static`.

F. **The `api:/resolved/` single-slash convention is fragile.** The engine stores `api:/resolved/{id}` (Path normalizes `//` → `/`), wrappers send `api://resolved/{id}`, and the merged resolvers do `.replace("//", "/")`. Overloading the `api://` scheme is brittle; a dedicated prefix would be cleaner.

G. **§8 omits `portfolio_review`.** It lists only three proposal types, yet AC-13-07 and the YAML include `portfolio_review`. Inconsistent scope.
