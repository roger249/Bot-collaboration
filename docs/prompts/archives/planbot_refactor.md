## 1. Goal

Make proposal prompt assembly fully configuration-driven so adding or changing a proposal does not require new Python branching logic.

### Target outcome

1. All proposal-specific prompt sections are declared in YAML.
2. Python code provides shared slot resolvers/formatters only.
3. Optional sections that depend on previous function calls are handled by policy (`skip`, `fallback_to_glob`, `error`) instead of ad hoc `if` blocks.
4. New proposal type = config section + CrewAI files.


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

## Test Strategy

Minimum regression tests after migration:

1. Product opportunity with matcher context present -> runtime doc override injected.
2. Product opportunity with matcher context absent -> fallback to glob works.
3. Reinvestment includes wallet inflow + IRS via slot config.
4. Matcher produces product catalog + PFS section via slot config.
5. Required runtime doc with `if_missing=error` fails with deterministic error code.

Add one normal-flow and one exception-condition unit test per new shared component.

### Acceptance Criteria (AC)

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
