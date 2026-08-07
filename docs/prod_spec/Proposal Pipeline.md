# Proposal Pipeline Concept Draft

Date: 2026-08-06  
Status: Draft concept for discussion

---

## 1. Purpose

Define a proposal pipeline concept that modernizes proposal generation while staying aligned with current PlanBot behavior.

This draft is intentionally implementation-light. It focuses on architecture, contracts, boundaries, and operating principles.

---

## 2. Design Intent

The proposal pipeline should:

1. Use a single execution backbone for all proposal types.
2. Keep proposal-specific differences in YAML configuration.
3. Support both runtime API data and file-glob references with predictable fallback.
4. Treat prior-step outputs as optional or required through explicit policy.
5. Produce similar proposal output quality with a simpler, intuitive configuration model.

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
2. `fallback_to_glob`
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

```yaml
schema_version: 2
proposal:
   id: <proposal_id>
   name: <display_name>

request_contract:
   required: [..]
   optional: [..]

execution:
   model: <model_key>
   output: { ... }

inputs: [ ... ]

input_policy:
   missing_data:
      default: error
   per_input: { ... }

prompt_packaging:
   decision_context_order: [ ... ]
   references_order: [ ... ]
   llm_payload: { ... }

quality_gates: { ... }
```

### 6.2 Sample YAML: Reinvestment Proposal

```yaml
schema_version: 2
proposal:
   id: reinvestment
   name: Reinvestment Proposal
   description: Recommend reinvestment options for a client with maturing positions

request_contract:
   required:
      - client_id
      - source_product_id
   optional:
      - market_outlook_text
      - max_alternatives
      - response_mode

execution:
   model: deepseek_tool
   output:
      folder: runs/reinvestment_proposal
      filename_template: reinvestment_{client_id}_{date}.md
   logging:
      level: INFO
      trace_input_resolution: true

inputs:
   - id: proposal_instructions
      source: static_glob
      paths:
         - data/planbot/reinvestment_proposal/proposal_instructions/*.md
      prompt_section: references
      required: true

   - id: section_guides
      source: static_glob
      paths:
         - data/planbot/shared/proposal_section_instructions/*.md
      prompt_section: references
      required: true

   - id: general_guidelines
      source: static_glob
      paths:
         - data/planbot/shared/common/general_guideline.md
      prompt_section: references
      required: true

   - id: financial_needs_guidelines
      source: static_glob
      paths:
         - data/planbot/shared/financial_needs/*.md
      prompt_section: references
      required: true

   - id: client_profile
      source: dynamic_by_api
      prompt_section: decision_context
      required: true

   - id: investor_readiness_score
      source: dynamic_by_api
      prompt_section: decision_context
      required: false

   - id: wallet_inflow_event
      source: dynamic_by_api
      prompt_section: decision_context
      required: true

   - id: holdings_table
      source: dynamic_by_api
      prompt_section: decision_context
      required: true

   - id: suggested_product
      source: dynamic_by_api
      prompt_section: decision_context
      required: true

   - id: holdings_in_catalog
      source: dynamic_by_api
      prompt_section: decision_context
      required: true

   - id: alternative_products
      source: dynamic_by_api
      prompt_section: decision_context
      required: false

   - id: product_fitness_scores
      source: dynamic_by_api
      prompt_section: decision_context
      required: false

   - id: market_outlook
      source: runtime_or_static
      source_priority:
         - request.market_outlook_text
         - data/planbot/shared/market_outlook/*.md
      prompt_section: decision_context
      required: false

input_policy:
   missing_data:
      default: error
   per_input:
      investor_readiness_score: skip
      market_outlook: fallback_to_static
      alternative_products: skip
      product_fitness_scores: skip

prompt_packaging:
   decision_context_order:
      - client_profile
      - investor_readiness_score
      - wallet_inflow_event
      - holdings_table
      - suggested_product
      - holdings_in_catalog
      - alternative_products
      - product_fitness_scores
      - market_outlook
   references_order:
      - proposal_instructions
      - section_guides
      - general_guidelines
      - financial_needs_guidelines
   llm_payload:
      task_prompt_from: proposal_instructions
      include_references: true

quality_gates:
   required_sections:
      - client_profile
      - wallet_inflow_event
      - holdings_table
      - suggested_product
   fail_on_empty_required_section: true
```

### 6.3 Why this model is intuitive

1. Proposal setup reads top-to-bottom like execution flow.
2. One unified `inputs` list removes duplicated concepts between decision context and references.
3. `prompt_section` makes packaging intent explicit (`decision_context` vs `references`).
4. `id` is the stable semantic key and implicit API plus formatter selector in shared code.
5. Missing-data behavior is visible per input, not hidden in code.
6. New proposal onboarding is mostly editing one YAML file.

### 6.4 Fixed runtime source and enrichment (Sprint 1)

For Sprint 1, runtime data retrieval and enrichment should be fixed in shared code, not configured per proposal.

1. Input rows with `source: dynamic_by_api` are resolved by a centralized resolver layer.
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

`input_defaults` should be defined once at schema or repository scope and shared across proposals unless a future need for proposal-local override appears.

Suggested default values:

1. `prompt_section: references`
2. `required: false`
3. `source: static_glob` when `paths` is present
4. `source: dynamic_by_api` when the `id` is a known runtime-resolved input
5. `source: runtime_or_static` when `source_priority` is present
6. `input_policy.missing_data.default: skip`

Recommended precedence order:

1. Explicit value on the input row
2. `input_defaults.by_id` value
3. `input_defaults.global` value
4. Engine hard default

Compact YAML pattern:

```yaml
schema_version: 2

input_defaults:
   global:
      prompt_section: references
      required: false
   by_id:
      client_profile:
         source: dynamic_by_api
         prompt_section: decision_context
      investor_readiness_score:
         source: dynamic_by_api
         prompt_section: decision_context
      wallet_inflow_event:
         source: dynamic_by_api
         prompt_section: decision_context
      holdings_table:
         source: dynamic_by_api
         prompt_section: decision_context
      suggested_product:
         source: dynamic_by_api
         prompt_section: decision_context
      holdings_in_catalog:
         source: dynamic_by_api
         prompt_section: decision_context
      alternative_products:
         source: dynamic_by_api
         prompt_section: decision_context
      product_fitness_scores:
         source: dynamic_by_api
         prompt_section: decision_context
      market_outlook:
         source: runtime_or_static

input_policy:
   missing_data:
      default: skip
   per_input:
      client_profile: error
      suggested_product: error

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
schema_version: 2

# shared defaults, defined once for all proposal configurations
input_defaults:
   global:
      prompt_section: references
      required: false
   by_id:
      client_profile: { source: dynamic_by_api, prompt_section: decision_context }
      investor_readiness_score: { source: dynamic_by_api, prompt_section: decision_context }
      holdings_table: { source: dynamic_by_api, prompt_section: decision_context }
      suggested_product: { source: dynamic_by_api, prompt_section: decision_context }
      holdings_in_catalog: { source: dynamic_by_api, prompt_section: decision_context }
      alternative_products: { source: dynamic_by_api, prompt_section: decision_context }
      product_fitness_scores: { source: dynamic_by_api, prompt_section: decision_context }
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
      suggested_product: error
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

   - id: holdings_table
      required: true

   - id: suggested_product
      required: true

   - id: holdings_in_catalog

   - id: alternative_products

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
      - holdings_table
      - suggested_product
      - holdings_in_catalog
      - alternative_products
      - product_fitness_scores
   references_order:
      - proposal_instructions
      - section_guides
      - general_guidelines
      - financial_needs_guidelines
      - suggested_products_and_rationale
      - market_outlook
   llm_payload:
      task_prompt_from: proposal_instructions
      include_references: true

quality_gates:
   required_sections:
      - client_profile
      - holdings_table
      - suggested_product
   fail_on_empty_required_section: true
```

Notes on omitted keys:

1. Most runtime business inputs omit `source` because `input_defaults.by_id` already maps them to `dynamic_by_api`.
2. Decision-critical inputs omit `prompt_section` because `input_defaults.by_id` already maps them to `decision_context`.
3. Optional inputs omit `required` because the global default is `false`.
4. `suggested_products_and_rationale` and `market_outlook` only specify `source_priority` because their `source` and `prompt_section` are already defaulted.
5. The example assumes `input_defaults` is shared globally and not repeated per proposal in real authoring.

---

## 7. Handling Prior-Function Dependencies

Some proposal sections come from previous function calls and may be absent for certain runs.

The concept resolves this with input-policy behavior, not proposal-specific branching:

1. If upstream section exists, inject via runtime doc override.
2. If upstream section is missing and input policy is `fallback_to_glob`, use configured file glob.
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

Expected assembly pattern:

1. multi-client profile blocks
2. readiness framing
3. product universe view with PFS per client
4. market outlook (runtime or static)

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
3. Failures use stable machine-readable error codes.
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

1. Proposal behavior differences are primarily YAML-declared inputs and policies.
2. Prior-function-derived sections no longer require hardcoded per-proposal branching.
3. Runtime and static references coexist under explicit policies.
4. New proposal onboarding requires configuration and content authoring, not custom orchestration logic.

---

## 14. Cross-Reference

This concept is aligned with:

1. `config/config_planbot.yaml` as current operational source of proposal metadata.
2. `docs/prompts/planbot_refactor.md` as input-driven prompt assembly direction.

These two documents remain the source anchors for subsequent implementation planning.