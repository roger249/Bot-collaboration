# PlanBot Proposal Prompt-Building Refactor Design

**Date:** 2026-08-05  
**Status:** Design ready for implementation review

---

## 1. Goal

Make proposal prompt assembly fully configuration-driven so adding or changing a proposal does not require new Python branching logic.

### Target outcome

1. All proposal-specific prompt sections are declared in YAML.
2. Python code provides shared slot resolvers/formatters only.
3. Optional sections that depend on previous function calls are handled by policy (`skip`, `fallback_to_glob`, `error`) instead of ad hoc `if` blocks.
4. New proposal type = config section + CrewAI files.

---

## 2. Scope

This design covers:

1. Reinvestment proposal
2. Product opportunity proposal
3. Product investor matching
4. Shared resolver + prompt-input assembly path

This design does not change:

1. Scoring formulas
2. OpenAPI contract semantics
3. CrewAI agent/task authoring model

---

## 3. Current-State Reference

All proposal runs already converge through a common execution entry point. Remaining divergence is mainly in per-proposal resolver wrappers that hardcode what to include and when.

## Current LLM Input per Proposal

Each proposal sends a task prompt + JSON reference payload to the LLM. Bold cells are resolver-built (runtime API data); plain cells are YAML file globs.

### API resolver paths

| `api://` path | Reinvestment | Product Opp. | Matcher |
|---|---|---|---|
| `client_profile` | ✅ `format_client_and_holdings(cp, extra=…)` | ✅ `format_client_and_holdings(cp)` | ✅ `format_client_and_holdings(cp, extra=…)` |
| `product_catalog` | ✅ `format_product_catalog(suggested, holdings, alts, pfs)` | ✅ same | ❌ `format_product_multi()` |
| `suggested_products_and_rationale` | — | ✅ gated `extra_docs` | — |
| `market_outlook` | — (YAML glob) | ✅ when provided | ✅ when provided |

### What the LLM sees

| Section | Reinvestment | Product Opp. | Matcher | Same shared function? |
|---|---|---|---|---|
| **Task prompt** | ✅ | ✅ | ✅ | ✅ `tasks.yaml` |
| **Proposal instructions** | ✅ | ✅ | ✅ | ✅ `load_references` |
| **Guidelines** | ✅ | ✅ | ✅ | ✅ `load_references` |
| **Client profile** | | | | |
| Standard fields + RM Notes | ✅ | ✅ | ✅ | ✅ `format_client_profile_markdown` |
| **Investor Readiness Score** | ✅ via `format_irs_section(total=cp.irs, cash_drag=cp.cash_score, …)` | ❌ | ✅ via `format_irs_section(total=rm.total_score, rank=…, cash_drag=rm.s_cash, …)` | ✅ `format_irs_section` — shared across both |
| **Wallet Inflow Event** | ✅ (maturing product) | ❌ | ❌ | ❌ `_build_api_resolver` only |
| **Holdings table** | ✅ 6-col bundled | ✅ 6-col bundled | ✅ 6-col bundled | ✅ `format_client_and_holdings` |
| **Product Catalog** | | | | |
| Suggested product | ✅ | ✅ | ❌ | ✅ `format_product_catalog` |
| Holdings (in catalog) | ✅ | ✅ | ❌ | ✅ `format_product_catalog` |
| Alternative products | ✅ | ✅ | ❌ | ✅ `format_product_catalog` |
| Multi-product listing | ❌ | ❌ | ✅ | ❌ `format_product_multi` |
| **Product Fitness Scores** | ✅ 8-col (suggested+alts) | ✅ 8-col (suggested+alts) | ✅ 8-col (all products) | ✅ `format_pfs_table` |
| **suggested_products_and_rationale** | ❌ | ✅ gated | ❌ | ❌ `_build_proposal_resolver` only |
| **Market outlook** | ✅ YAML glob | ✅ API or YAML glob | ✅ API or YAML glob | ✅ `load_references` |

### Current gaps

1. Matcher still uses `format_product_multi()` instead of a suggested/holdings/alternatives structure.
2. Product opportunity currently has no IRS section by default.
3. Resolver wrappers still encode proposal differences in Python.
4. Per-target/per-pair processing has duplicated control flow.

---

## 4. Design Principles

1. YAML decides sections; Python executes generic mechanics.
2. Missing upstream runtime data must be policy-driven and explicit.
3. Fallback to file globs should remain first-class for backward compatibility.
4. Existing API contracts should remain valid during migration.
5. Each slot has one responsibility and predictable output markdown.

---

## 5. Target Architecture

### 5.1 Building blocks

1. **Proposal slot config** in `config/config_planbot.yaml`.
2. **Slot source resolver** to collect data from:
   - request payload
   - previous function output (runtime context)
   - data-service APIs
   - YAML file globs fallback
3. **Slot formatter registry** mapping slot type -> formatter function.
4. **Unified resolver builder** assembling:
   - client content
   - product content
   - runtime docs (`api://...`)
   - runtime reference overrides

### 5.2 Runtime context model

Introduce a normalized in-memory context object per proposal run:

```yaml
runtime_context:
  proposal_name: string
  client_id: string
  source_product_id: string
  client_profile: dict
  source_product: dict
  holdings_products: list[dict]
  alternative_products: list[dict]
  readiness: dict
  pfs_scores: dict
  matcher_context_markdown: string
  market_outlook: string|null
```

All slot resolvers read from this context and are prohibited from writing custom proposal-specific output structures.

---

## 6. YAML Schema (Sprint 1)

Add a new configuration block under each proposal:

```yaml
product_opportunity_proposal:
  prompt_assembly:
    client_slots:
      - type: standard_client_profile
      - type: investor_readiness_score
        required: false
        source: readiness_or_client_profile
        if_missing: skip
      - type: holdings_table

    product_slots:
      - type: suggested_product
      - type: holdings_products
      - type: alternative_products
        required: false
        source: matcher_or_similarity
        if_missing: skip
      - type: product_fitness_scores
        required: false
        source: pfs
        if_missing: skip

    runtime_docs:
      - reference_key: suggested_products_and_rationale
        api_path: api://suggested_products_and_rationale
        source: matcher_context_or_input
        required: false
        if_missing: fallback_to_glob

      - reference_key: market_outlook
        api_path: api://market_outlook
        source: request_or_system
        required: false
        if_missing: fallback_to_glob

    api_overrides:
      mandatory:
        - client_profiles
        - product_catalogs
      conditional:
        - suggested_products_and_rationale
        - market_outlook
```

### 6.1 Field semantics

1. `required: true|false`
   - true: unresolved source is an error
   - false: apply `if_missing`
2. `if_missing`
   - `skip`: do not include section
   - `fallback_to_glob`: do not add runtime override for this reference key
   - `error`: fail run with deterministic message
3. `source`
   - symbolic source strategy to keep logic declarative

---

## 7. Slot Registry

A shared registry maps `type` values to formatter handlers:

```text
standard_client_profile -> format_client_profile_markdown
investor_readiness_score -> format_irs_section
wallet_inflow_event -> format_wallet_inflow_section
holdings_table -> format_holdings_table

suggested_product -> formatter for catalog.suggested
holdings_products -> formatter for catalog.holdings
alternative_products -> formatter for catalog.alternatives
product_fitness_scores -> format_pfs_table
```

### 7.1 Registry contract

Each handler returns one of:

1. markdown text (non-empty)
2. empty text (treated as missing)
3. structured section object for product catalog assembly

No handler should directly modify runtime overrides.

---

## 8. Unified Prompt Assembly Flow

1. Load proposal config and runtime context.
2. Resolve client slots in order.
3. Resolve product slots in order.
4. Assemble `client_content` and `product_content`.
5. Resolve runtime docs with policy.
6. Build resolver document map.
7. Build `runtime_reference_overrides`:
   - add mandatory keys always
   - add conditional keys only when runtime docs are present
8. Invoke proposal run through existing entry path.

### 8.1 Key behavior for previous-function-call sections

If a section depends on a previous function call (example: matcher context):

1. Source resolver attempts runtime context first.
2. If missing and `if_missing=fallback_to_glob`, the section key is not overridden and static globs remain active.
3. If missing and `if_missing=skip`, section is omitted with no failure.
4. If missing and `if_missing=error`, fail fast with a clear code.

This solves the current issue where some proposals should not require prior call outputs.

---

## 9. Error and Logging Policy

### 9.1 Error codes

Use stable codes for assembly failures:

1. `SLOT_SOURCE_MISSING`
2. `SLOT_FORMAT_FAILED`
3. `RUNTIME_DOC_REQUIRED_MISSING`
4. `UNSUPPORTED_SLOT_TYPE`

### 9.2 Logging requirements

1. Log each slot resolution outcome (`resolved`, `skipped`, `fallback`, `error`).
2. Log whether each conditional runtime override key was injected.
3. Never use print statements.

---

## 10. Migration Plan

### Sprint 1.1: Config introduction (no behavior change)

1. Add `prompt_assembly` blocks for all 3 proposals.
2. Keep existing wrappers active as fallback.

### Sprint 1.2: Product opportunity first

1. Switch product opportunity to unified slot pipeline.
2. Validate optional `suggested_products_and_rationale` policies.

### Sprint 1.3: Reinvestment and matcher

1. Move reinvestment to slot pipeline.
2. Move matcher and replace `format_product_multi` path with structured catalog layout.

### Sprint 1.4: Cleanup

1. Remove old proposal-specific resolver wrappers.
2. Converge duplicated per-target/per-pair processing through one internal runner.

---

## 11. Backward Compatibility

1. Existing file-glob references remain supported.
2. Existing endpoint payload shapes remain unchanged.
3. If runtime data is absent, fallback behavior is controlled by per-slot policy.

---

## 12. Test Strategy

Minimum regression tests after migration:

1. Product opportunity with matcher context present -> runtime doc override injected.
2. Product opportunity with matcher context absent -> fallback to glob works.
3. Reinvestment includes wallet inflow + IRS via slot config.
4. Matcher produces product catalog + PFS section via slot config.
5. Required runtime doc with `if_missing=error` fails with deterministic error code.

Add one normal-flow and one exception-condition unit test per new shared component.

### 12.1 Acceptance Criteria (AC)

Use the following acceptance criteria for Sprint 1 exit sign-off of test scope.

1. **AC-12-01 Runtime doc injection (positive path)**
  - Given `suggested_products_and_rationale` is present in runtime context
  - When product opportunity proposal runs
  - Then `runtime_reference_overrides` includes `suggested_products_and_rationale`
  - And resolver serves non-empty content for `api://suggested_products_and_rationale`

2. **AC-12-02 Runtime doc fallback (missing prior output)**
  - Given `suggested_products_and_rationale` is missing in runtime context
  - And slot policy is `if_missing: fallback_to_glob`
  - When product opportunity proposal runs
  - Then `runtime_reference_overrides` does not include `suggested_products_and_rationale`
  - And proposal run completes without `RUNTIME_DOC_REQUIRED_MISSING`

3. **AC-12-03 Reinvestment slot completeness**
  - Given reinvestment proposal slot config includes IRS + wallet inflow
  - When a valid client and source product are processed
  - Then assembled client content contains both sections
  - And run completes successfully with no slot-resolution error

4. **AC-12-04 Matcher catalog + PFS rendering**
  - Given matcher slot config includes product catalog and per-client PFS sections
  - When matcher runs on at least one eligible client and one product
  - Then product catalog content is generated
  - And at least one PFS row is rendered for each included client with score data

5. **AC-12-05 Required runtime doc hard-fail**
  - Given a runtime doc slot is configured with `required: true` and `if_missing: error`
  - When that runtime doc source is absent
  - Then run fails deterministically with error code `RUNTIME_DOC_REQUIRED_MISSING`
  - And failure message identifies the missing `reference_key`

6. **AC-12-06 Slot policy observability**
  - Given any proposal run using `prompt_assembly`
  - When slot resolution executes
  - Then logs include outcome per slot (`resolved`, `skipped`, `fallback`, or `error`)
  - And conditional runtime override injection decisions are logged

7. **AC-12-07 Regression gate**
  - Sprint 1 test suite must pass with:
  - Zero failing unit tests in changed modules
  - At least one normal-flow and one exception-flow unit test for each new shared component
  - No new runtime exceptions in proposal assembly path for existing supported inputs

---

## 13. Example Config Profiles

### Reinvestment profile

```yaml
reinvestment_proposal:
  prompt_assembly:
    client_slots:
      - type: standard_client_profile
      - type: investor_readiness_score
        required: false
        if_missing: skip
      - type: wallet_inflow_event
        required: true
        if_missing: error
      - type: holdings_table
    product_slots:
      - type: suggested_product
      - type: holdings_products
      - type: alternative_products
      - type: product_fitness_scores
        required: false
        if_missing: skip
    runtime_docs:
      - reference_key: market_outlook
        api_path: api://market_outlook
        required: false
        if_missing: fallback_to_glob
```

### Product opportunity profile

```yaml
product_opportunity_proposal:
  prompt_assembly:
    client_slots:
      - type: standard_client_profile
      - type: investor_readiness_score
        required: false
        if_missing: skip
      - type: holdings_table
    product_slots:
      - type: suggested_product
      - type: holdings_products
      - type: alternative_products
      - type: product_fitness_scores
        required: false
        if_missing: skip
    runtime_docs:
      - reference_key: suggested_products_and_rationale
        api_path: api://suggested_products_and_rationale
        required: false
        if_missing: fallback_to_glob
      - reference_key: market_outlook
        api_path: api://market_outlook
        required: false
        if_missing: fallback_to_glob
```

### Matcher profile

```yaml
product_investor_matching:
  prompt_assembly:
    client_slots:
      - type: standard_client_profile
      - type: investor_readiness_score
        required: false
        if_missing: skip
      - type: holdings_table
    product_slots:
      - type: product_universe_catalog
      - type: product_fitness_scores_by_client
    runtime_docs:
      - reference_key: market_outlook
        api_path: api://market_outlook
        required: false
        if_missing: fallback_to_glob
```

---

## 14. Exit Criteria

Sprint 1 is complete when:

1. No proposal-specific resolver wrapper contains proposal-only section branching.
2. All section presence/absence behavior is controlled by YAML policy.
3. The 3 proposal types run successfully with equivalent or better output completeness.
4. Required outputs are present and no runtime resolver errors occur in standard flows.
5. Documentation and tests are updated together.

---

## 15. Decision Summary

1. Keep one shared resolver builder.
2. Move proposal section composition to YAML slot declarations.
3. Treat previous-call-dependent sections as optional-by-policy, not hardcoded prerequisites.
4. Preserve file-glob fallback to avoid fragile coupling between proposal stages.

This is the recommended implementation design for Sprint 1.
