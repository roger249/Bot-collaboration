# PlanBot Proposal Prompt-Building Refactor Review

**Date:** 2026-08-05
**Scope:** Identify duplicate implementations and suggest unification across all proposal prompt-building code.

---

## Already Unified — Core Design (Well Done)

All five proposals (`product_opportunity_proposal`, `reinvestment_proposal`, `product_investor_matching`, `portfolio_review`, `stock_analysis`) build their prompts through a **single function**:

**`run_crew_planbot()`** in `src/planbot/crew_workflow.py` — the one and only entry point. The flow:

1. Load YAML config via `load_planbot_config()`
2. Iterate `cfg.reference_sections`, load documents via `load_references()`
3. Build prompt via `_build_reference_payload()` → `_build_user_prompt()`
4. Send to CrewAI via `_generate_with_crew()`

Differentiation between proposals is entirely driven by their section in `config_planbot.yaml` — exactly the design intent. File globbing, API resolution, and formatting in `input_loader.py` are unified across all proposals.

---

## 🔴 Duplicate Implementations Found

### 1. `_read_http_resolver_config()` — Full verbatim duplication

| File | Line |
|---|---|
| `src/integrations/reinvestment_proposal.py` | ~239 |
| `src/integrations/product_opportunity_proposal.py` | ~453 |

Exact same function, character for character. Should be moved to `src/shared/` (e.g., in `resolver_formatters.py` or a new `resolver_utils.py`).

### 2. `_process_one_target()` vs `_process_one_pair()` — Structural twins

| | `reinvestment_proposal.py` | `product_opportunity_proposal.py` |
|---|---|---|
| Function | `_process_one_target()` (~270 lines) | `_process_one_pair()` (~252 lines) |
| Steps | ① Read HTTP config → ② Phase B/A resolver → ③ Fitness scores → ④ Call `run_crew_planbot()` → ⑤ Return dict |

Both flows are identical. The only differences:
- Resolver builder (`_build_api_resolver` vs `_build_proposal_resolver`)
- `proposal_name` (`"reinvestment_proposal"` vs `"product_opportunity_proposal"`)
- Override keys — both pass `client_profiles` + `product_catalogs`; product-opportunity additionally passes `suggested_products_and_rationale` (matcher context)

This should be a **single function** with proposal-specific parameterization.

### 3. `_build_api_resolver()` vs `_build_proposal_resolver()` — Variations on the shared base

Both delegate to the shared `build_proposal_resolver()` (from `resolver_formatters.py`), but each adds different extras:

| | `reinvestment::_build_api_resolver` | `pop::_build_proposal_resolver` |
|---|---|---|
| Extra sections | Investor Readiness Score + Wallet Inflow Event | Suggested products and rationale context |
| Product catalog | `format_product_catalog(suggested=, holdings=, alternatives=)` | Same |
| Market outlook | None (handled elsewhere) | Optionally passed in |

### 4. `_build_matcher_api_resolver()` — Structural variant (and a correctness gap — see §5)

More complex (multi-client + multi-product), but still calls:
- `format_client_and_holdings(cp, extra_sections=[...])` — same pattern as `reinvestment_proposal._build_api_resolver`
- `format_product_multi(products)` — with fitness score table appended

The structural duplication is clear, but there is a deeper problem here: the matcher's resolver is the **only one** that injects Product Fitness Scores into the LLM prompt. See §5.

### 5. 🔴 Correctness Gap: PFS missing from reinvestment & product-opportunity prompts

The principle is: **all proposals that present a suggested product and alternatives to the LLM should include the full PFS component breakdown in the prompt.** The matcher does this correctly; the other two do not.

| PFS data | Matcher | Reinvestment | Product Opp. |
|---|---|---|---|
| `search_product_by_fitness_score()` called? | ✅ Yes (line ~237) | ❌ Never called | ✅ Yes (line ~337) |
| PFS in LLM prompt? | ✅ Full component table | ❌ None — `candidate_products` have only `similarity_score` (cosine, not PFS) | ❌ Computed but only placed in `metadata` dict, never fed to resolver |
| What the LLM sees | Fitness, Risk Match, Concentration, Experience, Better Product scores per client per product | Nothing | Nothing |

**Concrete evidence:**

- **Reinvestment** `_build_api_resolver()` calls `format_product_catalog(suggested=, holdings=, alternatives=candidate_products)` — the `candidate_products` dicts carry a `similarity_score` from `search_similar_to_product()` which is **semantic cosine similarity**, not PFS. The 4-dimensional PFS (`risk_rating_match_score`, `concentration_score`, `has_similar_investment_experience_score`, `better_product_score`) is never computed and never reaches the prompt.

- **Product Opportunity** `_build_proposal_resolver()` has the same `format_product_catalog(suggested=, holdings=, alternatives=alt_products)` call with no PFS. Meanwhile `_process_one_pair()` *does* compute PFS at lines 333-341 via `search_product_by_fitness_score()`, but only stores the aggregate `fitness_score` in `metadata` — never passes component scores into the resolver.

- **Matcher** `_build_matcher_api_resolver()` is the sole correct implementation: its `_format_product_catalog()` inner function appends `## Product Fitness Scores (per client)` with the full 8-column table (Fitness Score, Risk Match, Concentration, Experience, Better Product).

**Fix:** The PFS component table must be injected into the `product_content` of every proposal's resolver, not just the matcher's. The `format_product_catalog()` function in `resolver_formatters.py` should accept an optional `pfs_scores` parameter and render the table when present. Each proposal's `_process_one_*` must call `search_product_by_fitness_score()` and pass results through.

**PFS scope:** Only the **suggested product** and its **alternatives** are scored — not the client's existing holdings. Holdings appear in the prompt as portfolio context only (the `## Client Holdings` table). The `pfs_scores` dict maps `product_id → component_scores` for suggested + alternatives; `format_product_catalog()` renders a `## Product Fitness Scores` section after the alternatives table.

### 6. 🔴 `suggested_products_and_rationale` override always fires — not gated like `market_outlook`

In `_process_one_pair()` (lines 347-351):

```python
overrides: dict[str, list[str]] = {
    "client_profiles":                  [API_CLIENT_PROFILE],
    "product_catalogs":                 [API_PRODUCT_CATALOG],
    "suggested_products_and_rationale": [API_SUGGESTED_PRODUCTS_AND_RATIONALE],
}
if market_outlook is not None:
    overrides["market_outlook"] = [API_MARKET_OUTLOOK]
```

`suggested_products_and_rationale` is always included unconditionally, even when `suggested_products_and_rationale=""`. This means:

- The override always fires → `load_references()` delegates to the API resolver for that path.
- When content is empty, `_build_proposal_resolver()` produces an empty `extra_docs`, so the resolver returns an empty `ReferenceDocument`.
- The YAML file glob (`data/planbot/product_opportunity_proposal/suggested_products/*.md`) is **preempted** — it never gets a chance to load from disk.

The `market_outlook` override already follows the correct pattern: gate it on whether content exists. `suggested_products_and_rationale` should do the same.

**Fix:** Conditional gate — only add to overrides when `suggested_products_and_rationale` is non-empty. This is a one-line change matching the existing `market_outlook` pattern.

---

## 🟡 Dead Code / Legacy

| Symbol | Location | Status |
|---|---|---|
| `build_matcher_llm_payload()` | `workflow.py:195` | **Never called** — imported but unused in `product_investor_matcher.py` |
| `_build_fit_analysis_resolver()` | `product_investor_matcher.py:629` | **Never called** — only referenced in spec docs |
| `format_product_single()` | `resolver_formatters.py:375` | Marked **deprecated**, thin wrapper around `format_product_catalog()` |

---

## 📊 Issue → Resolution Mapping

| # | Issue | Type | Resolved by |
|---|---|---|---|
| 1 | `_read_http_resolver_config()` duplicated verbatim | Structural duplication | Phase A.1 |
| 2 | `_process_one_target` / `_process_one_pair` are structural twins | Structural duplication | Phase B.3 |
| 3 | `_build_api_resolver` / `_build_proposal_resolver` / `_build_matcher_api_resolver` are resolver-builder variants | Structural duplication | Phase B.4 |
| 4 | `_build_matcher_api_resolver` has different shape (multi-client) | Structural variant | Phase B.4 |
| 5 | **PFS missing from reinvestment & product-opportunity prompts** | 🔴 Correctness bug | Phase A.3 |
| 6 | **`suggested_products_and_rationale` override always fires** — preempts YAML file glob when empty | 🔴 Correctness bug | Phase A.4 |
| D1 | `build_matcher_llm_payload()` — dead code | Dead code | Phase A.2 |
| D2 | `_build_fit_analysis_resolver()` — dead code | Dead code | Phase A.2 |
| D3 | `format_product_single()` — deprecated wrapper | Legacy | Already marked; remove when no callers remain |

```
src/integrations/
├── product_opportunity_proposal.py
│   ├── _read_http_resolver_config()           ← Issue #1
│   ├── _process_one_pair()                    ← Issue #2
│   ├── _build_proposal_resolver()             ← Issue #3
│   ├── [PFS computed but not in prompt]       ← Issue #5 🔴
│   └── [suggested_and_rationale always overrides]  ← Issue #6 🔴
│
├── reinvestment_proposal.py
│   ├── _read_http_resolver_config()           ← Issue #1
│   ├── _process_one_target()                  ← Issue #2
│   ├── _build_api_resolver()                  ← Issue #3
│   └── [PFS never computed]                   ← Issue #5 🔴
│
└── product_investor_matcher.py
    ├── _build_matcher_api_resolver()           ← Issue #4
    ├── _build_fit_analysis_resolver()          ← Issue D2 (dead)
    └── imports build_matcher_llm_payload       ← Issue D1 (dead)
```

---

## 🟢 Unification Plan

### Phase A: Quick Wins (no behavioral change, ~1 hour)

| Item | Resolves | Description |
|---|---|---|
| A.1 | #1 | **Move `_read_http_resolver_config()` to `src/shared/resolver_formatters.py`** (or `resolver_utils.py`). Remove duplicates from `reinvestment_proposal.py` and `product_opportunity_proposal.py`. |
| A.2 | D1, D2 | **Remove dead code**: delete `_build_fit_analysis_resolver()` from `product_investor_matcher.py`; delete `build_matcher_llm_payload()` from `workflow.py` and its import from `product_investor_matcher.py`. |
| A.3 | #5 🔴 | **Add PFS to `format_product_catalog()`**. Give `format_product_catalog()` in `resolver_formatters.py` an optional `pfs_scores: dict[str, list[dict]]` parameter (product_id → component scores). Only the **suggested** and **alternative** products are scored — holdings are not (they are portfolio context only). When `pfs_scores` is present, append a `## Product Fitness Scores` table below the alternatives section. Then: (a) in `_process_one_pair()` — pass the already-computed `product_fitness_scores` through to the resolver; (b) in `_process_one_target()` — call `search_product_by_fitness_score()` for `[source_product_id] + candidate_product_ids` and pass results through. |
| A.4 | #6 🔴 | **Gate `suggested_products_and_rationale` override on content**. In `_process_one_pair()`, only add `suggested_products_and_rationale` to the overrides dict when the content is non-empty — same pattern as `market_outlook`. One-line change: `if suggested_products_and_rationale: overrides["suggested_products_and_rationale"] = [API_SUGGESTED_PRODUCTS_AND_RATIONALE]`. |

### Phase B: Structural Unification (recommended, ~half day)

| Item | Resolves | Description |
|---|---|---|
| B.3 | #2 | **Extract `run_proposal_for_pair()`** from `_process_one_target` / `_process_one_pair`. Place in `src/planbot/proposal_executor.py` (already has `ProposalExecutor`). The unified flow: ① resolve HTTP/direct data → ② build resolver via callback → ③ compute PFS → ④ inject PFS into resolver → ⑤ call `run_crew_planbot()` → ⑥ return dict. The `build_resolver` callback and `reference_overrides` dict are the only proposal-specific parameters. |
| B.4 | #3, #4 | **Collapse three resolver wrappers into a single `build_proposal_resolver_with_extras()`**. After Phase A, all sections are gated (market_outlook, pfs_scores, extra_docs, extra_client_sections are all optional). The underlying `build_proposal_resolver()` already handles all of this — no new logic needed. The three wrappers (`_build_api_resolver`, `_build_proposal_resolver`, `_build_matcher_api_resolver`) differ only in what `extra_client_sections` and `extra_docs` they prepare before the call. Replace them with a single parameterized builder. The matcher's multi-client loop stays in the matcher module but calls this same builder per client. |

### Phase C: Configuration-Driven — externalize client/product data slots to YAML

Today, new proposals require writing Python because `extra_client_sections`, `extra_docs`, and PFS injection are hardcoded in each proposal module. Phase C makes them YAML-declarable.

#### What's currently hardcoded (per proposal)

| Hardcoded section | In reinvestment? | In product-opp? | In matcher? | Data source |
|---|---|---|---|---|
| **Investor Readiness Score** (IRS heading + component breakdown) | ✅ lines 430-437 | ❌ | ✅ lines 572-582 | `client_profile` fields + `readiness_map` API |
| **Wallet Inflow Event** (maturing product info) | ✅ lines 439-444 | ❌ | ❌ | `source_product_id` + `source_product.name` |
| **Cash %** | ❌ | ❌ | ✅ line 573 | `client_profile.cash_pct` |
| **PFS table** (Fitness Score, Risk Match, Concentration, Experience, Better Product) | ❌ | ❌ | ✅ lines 585-618 | `fitness_results` API |
| **`suggested_products_and_rationale`** (matcher per-client analysis) | ❌ | ✅ `extra_docs` | ❌ | Matcher output markdown |

All five are computed at runtime per client — they can't be static file globs. But they're also always derived from the same data sources (client profile API, readiness API, fitness API, matcher output). They just need to be declared per proposal.

#### Proposed YAML schema

Under each proposal section, add `client_data_slots` and `product_data_slots`:

```yaml
reinvestment_proposal:
  client_data_slots:
    - type: investor_readiness_score   # → "## Investor Readiness Score" + component rows
    - type: wallet_inflow_event        # → "# Wallet Inflow Event" + maturing product info
  product_data_slots:
    - type: product_fitness_scores     # → "## Product Fitness Scores" table

product_opportunity_proposal:
  client_data_slots:
    - type: investor_readiness_score
  product_data_slots:
    - type: product_fitness_scores
  runtime_docs:                        # api:// paths only injected when content available
    - suggested_products_and_rationale # passed through from matcher; gated on content
```

Each `type` maps to a **slot formatter** — a function in a registry that takes standard inputs (client dict, readiness dict, fitness dict, source product) and returns markdown. The unified pipeline runner iterates declared slots, calls the registered formatter, appends to the resolver. Adding a new slot type means writing one formatter — not a new resolver + process function + integration module.

| Item | Description |
|---|---|
| C.5 | **Implement `DataSlot` registry and YAML `client_data_slots` / `product_data_slots` / `runtime_docs` keys**. Define formatter functions for the five slot types above. Update `run_proposal_for_pair()` (from B.3) to read slots from config and invoke the registry. |
| C.6 | **Remove all hardcoded `extra_client_sections` and `extra_docs` preparation** from the three resolver wrappers. After C.5, they are redundant — the unified pipeline builds them from YAML. |

#### Impact

After Phase C, adding a **new proposal type** requires:
1. A YAML section with references, LLM model, `data_slots`, and `api_overrides`
2. A `config/crewai/planbot/<proposal>/` folder with `agents.yaml` + `tasks.yaml`

No new integration Python module. No new resolver wrapper. No new `_process_one_*`.

---

## 📈 Impact Assessment

| Change | Files Edited | Risk | Resolves |
|---|---|---|---|
| Extract `_read_http_resolver_config` | 3 files | Very low | #1 |
| Remove dead code | 2 files | None | D1, D2 |
| **Add PFS to `format_product_catalog` + wire through resolvers** | 3–4 files | Low | #5 🔴 |
| **Gate `suggested_products_and_rationale` on content** | 1 file, 1 line | Very low | #6 🔴 |
| Unify `_process_one_*` into `run_proposal_for_pair` | 3–4 files | Low | #2 |
| Parameterize resolver builders | 3–4 files | Medium | #3, #4 |
| Make overrides config-driven (Phase C.5) | 2–3 files + YAML | Medium | new proposal zero-code |
| Data-slot registry + formatters (Phase C.6) | 4–5 files | Medium | new proposal zero-code |
