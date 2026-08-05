# PlanBot Proposal Prompt-Building Refactor Review

**Date:** 2026-08-05  
**Last update:** 2026-08-05 (Phase A implemented)  
**Status:** Phase A complete ✅ — Phase B & C outstanding

---

## Already Unified — Core Design (Well Done)

All five proposals build their prompts through a **single function**:

**`run_crew_planbot()`** in `src/planbot/crew_workflow.py` — the one and only entry point. Differentiation between proposals is driven by their section in `config_planbot.yaml`.

---

## Phase A — Implemented (2026-08-05)

| # | What | Before → After |
|---|---|---|
| A.1 | `_read_http_resolver_config()` duplicated verbatim | → Moved to `src/shared/resolver_formatters.py` as `read_http_resolver_config()` |
| A.2 | Dead code: `build_matcher_llm_payload()`, `_build_fit_analysis_resolver()` | → Removed |
| A.3 | PFS missing from reinvestment & product-opportunity prompts | → Added `pfs_scores` param to `format_product_catalog()`. Both resolvers now call shared `compute_pfs_for_products()` and pass results. PFS table for suggested + alternatives only (not holdings). |
| A.4 | `suggested_products_and_rationale` override always fired, preempting YAML file glob | → Gated on content non-empty, matching `market_outlook` pattern |

**Files changed:** `resolver_formatters.py`, `workflow.py`, `product_investor_matcher.py`, `product_opportunity_proposal.py`, `reinvestment_proposal.py`, 3 test files. All 29 unit tests pass.

---

## Outstanding Issues

### #2. `_process_one_target()` vs `_process_one_pair()` — Structural twins

Both are ~250-line functions with identical flow: ① Read HTTP config → ② Phase B/A resolver → ③ Compute PFS → ④ Call `run_crew_planbot()` → ⑤ Return dict. They differ only in resolver builder and `proposal_name`. Should be a **single function** with proposal-specific parameterization.

### #3. `_build_api_resolver()` vs `_build_proposal_resolver()` — Variations on shared base

Both delegate to `build_proposal_resolver()`. Difference is only in `extra_client_sections` and `extra_docs`:

| | `reinvestment::_build_api_resolver` | `pop::_build_proposal_resolver` |
|---|---|---|
| Extra sections | Investor Readiness Score + Wallet Inflow Event | Suggested products and rationale context |

### #4. `_build_matcher_api_resolver()` — Multi-client structural variant

More complex but calls the same shared formatters: `format_client_and_holdings(cp, extra_sections=[…])` and `format_product_multi(products)` with fitness table.

---

## Unification Plan (remaining)

### Phase B: Structural Unification (~half day)

| Item | Resolves | Description |
|---|---|---|
| B.3 | #2 | **Extract `run_proposal_for_pair()`** from `_process_one_target` / `_process_one_pair`. Place in `src/planbot/proposal_executor.py`. Unified flow: ① resolve data → ② build resolver via callback → ③ compute PFS → ④ inject PFS → ⑤ call `run_crew_planbot()` → ⑥ return dict. |
| B.4 | #3, #4 | **Collapse three resolver wrappers into one parameterized builder**. After Phase A, all sections are gated. The underlying `build_proposal_resolver()` needs no new logic. The matcher's multi-client loop stays but calls the same builder per client. |

### Phase C: Configuration-Driven — externalize per-proposal data slots to YAML

Currently `extra_client_sections` and `extra_docs` are the last hardcoded per-proposal differences. Phase C makes them YAML-declarable via a slot-formatter registry:

```yaml
reinvestment_proposal:
  client_data_slots:
    - type: investor_readiness_score
    - type: wallet_inflow_event
  product_data_slots:
    - type: product_fitness_scores

product_opportunity_proposal:
  client_data_slots:
    - type: investor_readiness_score
  product_data_slots:
    - type: product_fitness_scores
  runtime_docs:
    - suggested_products_and_rationale
```

**End state:** New proposal = YAML section + `agents.yaml`/`tasks.yaml`. Zero new Python.
