# PlanBot Config Consolidation (Refactor Proposal)

> Status: Draft — proposal for discussion. No implementation yet.

## 1. Purpose

`config/config_planbot.yaml` currently describes each API-served proposal in **two overlapping places**, plus carries a dead CLI-only block. This proposal consolidates to a **single source of truth per proposal**, removes the dead `run_configurations` block, and keeps the **FastAPI endpoints valid** (the CLI is no longer used).

## 2. Current state

### 2.1 Two config trees describe each proposal

| Concern | Where | Consumer |
| --- | --- | --- |
| CrewAI definition (`task`, `crewai_config_folder`, `references{name,purpose}`, `output_root`, `output_filename`, `overwrite_output_folder`, `llm_model`) | **top-level** sections (`reinvestment_proposal`, `product_investor_matching`, `product_opportunity_proposal`, `portfolio_review`) | `load_planbot_config()` → `run_crew_planbot()` |
| Input resolution + prompt packaging (`request_contract`, `execution`, `inputs`, `input_policy`, `prompt_packaging`, `quality_gates`) | **`pipeline.*`** sections (`product_investor_matching`, `reinvestment`, `product_opportunity`, `portfolio_review`) | `PipelineEngine` |
| `matcher` tuning (`readiness_pool_size`, `llm_client_pool_size`, `extract_patterns`) | **top-level** `product_investor_matching.matcher` only | `product_investor_matcher.py:107` and `:758` directly |

The two trees **overlap in intent** (both list reference files / model / output) but feed **different code paths**, so there is no safe "comment out the duplicate".

### 2.2 How the API flows combine them (all four)

Each integration (`reinvestment_proposal.py`, `product_opportunity_proposal.py`, `product_investor_matcher.py`, `portfolio_review.py`) uses a hybrid:

1. `PipelineEngine(proposal_id=…).prepare()` → resolves file/static inputs (`proposal_instructions`, `section_guides`, `guidelines`, `market_outlook`).
2. `run_crew_planbot(proposal_name="<top-level key>", …)` → `load_planbot_config()` reads the **top-level** section for the CrewAI definition.

Note: `PipelineEngine` *also* has a `run()`/`_run_pipeline()` path that synthesizes a temp config (`temp/pipeline_<id>.yaml`) and calls `run_crew_planbot(proposal_name="pipeline_<id>")` — but the integrations **bypass** this in favour of `.prepare()` + a direct `run_crew_planbot` call (they need fine control over `api_resolver` merging and `output_file_override`).

### 2.3 Dead config (CLI-only)

- `run_configurations` block (already marked `DEPRECATED` in YAML).
- Consumed only by `src/main.py` `run-pipeline` → `PipelineRunner` → `PipelineOrchestrator` + `ProposalExecutor`.
- `orchestrator.py:load_config()` returns `data.get("run_configurations", {})`.
- No FastAPI endpoint reads `run_configurations`.

> **Note — deprecation confirmed.** No FastAPI endpoint reads `run_configurations`; the only consumer is the CLI `run-pipeline` subcommand (already marked DEPRECATED and superseded by `/api/v1/product-opportunity-proposal-automatch`). The only importers of `ExecutionContext` / filters (`product_investor_matching_filter`, `client_holdings_filter`) are `pipeline_runner.py`, `proposal_executor.py`, and `tests/test_proposal_executor.py` — all deleted in step 7. The `run_configurations` block is removed from `config_planbot.yaml` as part of this task.

## 3. Goals

1. One config section per API-served proposal — no top-level vs. `pipeline.*` duplication.
2. Keep `/api/v1/*` endpoints valid: `product-investor-matcher`, `product-opportunity-proposal(-automatch)`, `reinvestment-proposals`, `portfolio-review`.
3. Delete `run_configurations` + the `run-pipeline` CLI + `PipelineRunner` / `PipelineOrchestrator` / `ProposalExecutor` (CLI is not used anymore).
4. Preserve existing output format and behavior (no functional change).

## 4. Proposed target state

Merge the top-level CrewAI definition into `pipeline.<id>` so a single section carries everything. Rather than copying the CrewAI keys (`task`, `crewai_config_folder`, `output_root`, `output_filename`, `llm_model`) verbatim, **derive them from the pipeline id** so they are not repeated in YAML.

### 4.1 Derivation rule

Given `pipeline.<id>`, the CrewAI definition is derived as:

| Field | Rule |
| --- | --- |
| `task` | `<id>_task` |
| `crewai_config_folder` | `data/planbot/<id>/crewai` |
| `data_root` / `references_root` | `data/planbot/<id>` |
| `output_root` | `runs/<id>` |
| `output_filename` | `<id>.md` |
| `overwrite_output_folder` | `execution.output.overwrite` (default `false`) |
| `llm_model` | `execution.model` (no separate key) |

This makes `id` the single source of truth — no `task` / `crewai_config_folder` / `llm_model` keys appear in `pipeline.*` at all.

> **Note — `overwrite_output_folder`.** Today `product_opportunity_proposal` sets `overwrite_output_folder: true` (the others default `false`). To preserve that behavior, `overwrite_output_folder` is declared per proposal under `execution.output.overwrite` rather than derived. `product_opportunity` keeps `overwrite: true`; the other three omit it (default `false`).

### 4.2 Id alignment (rename to make derivation work)

Two pipeline ids currently drop the `_proposal` suffix, breaking the `data/planbot/<id>` and `<id>_task` convention. Align them by renaming folder + task key:

| Pipeline id | Current folder | Current task key | Target folder | Target task key |
| --- | --- | --- | --- | --- |
| `reinvestment` | `data/planbot/reinvestment_proposal` | `reinvestment_proposal_task` | `data/planbot/reinvestment` | `reinvestment_task` |
| `product_opportunity` | `data/planbot/product_opportunity_proposal` | `product_opportunity_proposal_task` | `data/planbot/product_opportunity` | `product_opportunity_task` |
| `product_investor_matching` | (already aligned) | (already aligned) | — | — |
| `portfolio_review` | (already aligned) | (already aligned) | — | — |

Ripple effects of the two folder renames:

- `config/config_planbot.yaml` — top-level `data_root`/`references_root`/`crewai_config_folder` (to be deleted anyway) + the `inputs[].paths` globs in `pipeline.*`.
- `tests/test_pipeline_engine.py` — fixture paths (`reinvestment_proposal` ×3, `product_opportunity_proposal` ×4).
- `tests/test_proposal_executor.py` — `references_root` fixtures (×3, removed if that CLI test is deleted in step 7).
- `data/planbot/<id>/crewai/tasks.yaml` — rename the top-level task key (`reinvestment_proposal_task` → `reinvestment_task`, etc.).
- Docs that quote these paths (non-blocking, update opportunistically).

### 4.3 Target YAML (single proposal, fully derived)

```yaml
pipeline:
  product_investor_matching:
    matcher:                                        # proposal-specific tuning (matcher only)
      readiness_pool_size: 15
      llm_client_pool_size: 5
      extract_patterns: { ... }
    execution:
      model: deepseek_tool
      output:
        folder: runs/product_investor_matching
        filename_template: product_investor_matching_{date}.md
        overwrite: false          # default; omit unless true (product_opportunity)
    inputs: [ ... ]                                  # already present; each input = one section
    input_policy: { ... }
    prompt_packaging: { ... }
    quality_gates: { ... }
```

The top-level `product_investor_matching` / `reinvestment_proposal` / `product_opportunity_proposal` / `portfolio_review` sections are then **deleted**. `stock_analysis_proposal` is a CLI `run-planbot`-only proposal with no `pipeline` entry — out of scope for this refactor (left as-is).

There is **no separate `reference_sections` block**. Each input id is its own LLM-visible section, and the section `purpose` is the input's `description` (from `input_defaults.by_id.<id>.description`). This collapses the old grouped vocabulary (`proposal_instructions_and_format`, `guidelines`, `client_profiles`, `product_catalogs`) to 1:1 input-id sections.

### 4.4 Single-step delivery (config consolidation + section normalization)

One pass, not two. Both the config consolidation and the prompt-section normalization land together, then are re-validated as a whole.

- **Config consolidation** — merge CrewAI definition into `pipeline.<id>`; derive `task`/`crewai_config_folder`/`output_*` from the id (§4.1–4.2); repoint `matcher`; delete the top-level sections.
- **Section normalization** — each input id becomes its own section; `description` serves as `purpose`; `tasks.yaml` `description:` is rewritten to name the input ids instead of the old grouped section names.

This is **behavior-changing** (the prompt vocabulary changes), so it requires the regression tests + human inspection in §6.1 before merge.

## 5. Step-by-step plan

| # | Step | Files |
| --- | --- | --- |
| 1 | Add CrewAI keys (`task`, `crewai_config_folder`, `llm_model`) + `matcher` to each `pipeline.<id>` section in `config_planbot.yaml`. Dedupe `llm_model` vs `execution.model` (keep one). Add `overwrite_output_folder` → `execution.output.overwrite` (per §4.1). | `config/config_planbot.yaml` |
| 2 | Teach `load_planbot_config` to read from `pipeline.<id>` (deriving `task` / `crewai_config_folder` / `output_root` / `output_filename` per §4.1), so `run_crew_planbot(proposal_name="<pipeline id>")` works without a top-level section. | `src/planbot/config.py` |
| 3 | Update the four integrations to source the CrewAI definition from the pipeline config instead of `load_planbot_config`'s top-level lookup. Consolidate on `PipelineEngine.run()` (with an explicit resolver factory) rather than `.prepare()` + a direct `run_crew_planbot` call — removes the dead `_run_pipeline()` temp-config hack. | `reinvestment_proposal.py`, `product_opportunity_proposal.py`, `product_investor_matcher.py`, `portfolio_review.py` |
| 4 | Repoint `matcher` reads to `pipeline.product_investor_matching.matcher`. | `product_investor_matcher.py:107`, `:758` |
| 5 | Rewrite `tasks.yaml` `description:` to name input ids instead of the old grouped section names (`proposal_instructions_and_format` → `proposal_instructions`/`section_guides`, `guidelines` → the three guideline inputs, `client_profiles` → `client_profile`, `product_catalogs` → `product_catalog`). | `data/planbot/<id>/crewai/tasks.yaml` |
| 6 | Delete top-level `product_investor_matching` / `reinvestment_proposal` / `product_opportunity_proposal` / `portfolio_review` sections. | `config/config_planbot.yaml` |
| 7 | Delete `run_configurations` block. | `config/config_planbot.yaml` |
| 8 | Remove `run-pipeline` subcommand + import; delete `PipelineRunner`, `PipelineOrchestrator`, `ProposalExecutor` (and their tests). | `src/main.py`, `src/planbot/pipeline_runner.py`, `src/planbot/orchestrator.py`, `src/planbot/proposal_executor.py`, `tests/test_proposal_executor.py` |
| 9 | Run the end-to-end regression suite `tests/test_proposal_API.py` + full `pytest tests/` to confirm the endpoints remain valid. | `tests/` |

## 6. Verification

- All `/api/v1/*` endpoints return identical outputs (format + content) before/after.
- `tests/test_proposal_API.py` (the slow end-to-end regression) passes.
- `tests/test_product_investor_matcher.py`, `tests/test_product_opportunity_proposal.py`, `tests/test_reinvestment_proposal.py`, `tests/test_data_server_api.py` pass.
- `python src/main.py run-pipeline` is removed (no longer exists).

### 6.1 Regression + human inspection

After the single-step consolidation + normalization lands, before merge:

1. **Regression tests on the three proposals** — reinvestment, product-opportunity, and product-investor-matcher each get an end-to-end test that invokes the real LLM path through the consolidated `pipeline.*` config and asserts the output is non-empty and structurally intact. These run as the minimal gate for the change.
2. **Human inspection** — generate one sample proposal of each of the three types and manually review the markdown + `prompt_snapshot.md` (section names, purposes, ordering) to confirm the consolidated config produces the intended prompts.

## 7. Outstanding issues

*None outstanding.*
