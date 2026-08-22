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

## 3. Goals

1. One config section per API-served proposal — no top-level vs. `pipeline.*` duplication.
2. Keep `/api/v1/*` endpoints valid: `product-investor-matcher`, `product-opportunity-proposal(-automatch)`, `reinvestment-proposals`, `portfolio-review`.
3. Delete `run_configurations` + the `run-pipeline` CLI + `PipelineRunner` / `PipelineOrchestrator` / `ProposalExecutor` (CLI is not used anymore).
4. Preserve existing output format and behavior (no functional change).

## 4. Proposed target state

Merge the top-level CrewAI definition into `pipeline.<id>` so a single section carries everything. Concretely, add the missing CrewAI keys to each `pipeline.<id>` entry:

```yaml
pipeline:
  product_investor_matching:
    task: product_investor_matching_task            # ← moved from top-level
    crewai_config_folder: data/planbot/product_investor_matching/crewai   # ← moved
    llm_model: deepseek_tool                        # ← already have execution.model (dedupe)
    matcher:                                        # ← moved from top-level
      readiness_pool_size: 15
      llm_client_pool_size: 5
      extract_patterns: { ... }
    execution:
      model: deepseek_tool                          # dedupe with llm_model
      output:
        folder: runs/product_investor_matching
        filename_template: product_investor_matching_{date}.md
    inputs: [ ... ]                                  # already present
    ...
```

The top-level `product_investor_matching` / `reinvestment_proposal` / `product_opportunity_proposal` / `portfolio_review` sections are then **deleted** (or reduced to nothing). `stock_analysis_proposal` is a CLI `run-planbot`-only proposal with no `pipeline` entry — out of scope for this refactor (left as-is).

## 5. Step-by-step plan

| # | Step | Files |
| --- | --- | --- |
| 1 | Add CrewAI keys (`task`, `crewai_config_folder`, `llm_model`) + `matcher` to each `pipeline.<id>` section in `config_planbot.yaml`. Dedupe `llm_model` vs `execution.model` (keep one). | `config/config_planbot.yaml` |
| 2 | Extend `PipelineEngine` to surface `task` / `crewai_config_folder` / `llm_model` so the integration can pass them to `run_crew_planbot` without a top-level section. (Or extend `run_crew_planbot` to accept an explicit proposal-def dict, bypassing `load_planbot_config`.) | `src/planbot/pipeline_engine.py`, `src/planbot/crew_workflow.py`, `src/planbot/config.py` |
| 3 | Update the four integrations to source the CrewAI definition from the pipeline config instead of `load_planbot_config`'s top-level lookup. | `reinvestment_proposal.py`, `product_opportunity_proposal.py`, `product_investor_matcher.py`, `portfolio_review.py` |
| 4 | Repoint `matcher` reads to `pipeline.product_investor_matching.matcher`. | `product_investor_matcher.py:107`, `:758` |
| 5 | Delete top-level `product_investor_matching` / `reinvestment_proposal` / `product_opportunity_proposal` / `portfolio_review` sections. | `config/config_planbot.yaml` |
| 6 | Delete `run_configurations` block. | `config/config_planbot.yaml` |
| 7 | Remove `run-pipeline` subcommand + import; delete `PipelineRunner`, `PipelineOrchestrator`, `ProposalExecutor` (and their tests). | `src/main.py`, `src/planbot/pipeline_runner.py`, `src/planbot/orchestrator.py`, `src/planbot/proposal_executor.py`, `tests/test_proposal_executor.py` |
| 8 | Run the end-to-end regression suite `tests/test_proposal_API.py` + full `pytest tests/` to confirm the endpoints remain valid. | `tests/` |

## 6. Verification

- All `/api/v1/*` endpoints return identical outputs (format + content) before/after.
- `tests/test_proposal_API.py` (the slow end-to-end regression) passes.
- `tests/test_product_investor_matcher.py`, `tests/test_product_opportunity_proposal.py`, `tests/test_reinvestment_proposal.py`, `tests/test_data_server_api.py` pass.
- `python src/main.py run-pipeline` is removed (no longer exists).

## 7. Outstanding issues

1. **Direction of merge** — merge top-level CrewAI keys *into* `pipeline.*` (proposed here), or keep top-level as the CrewAI definition and delete the `pipeline.*` input duplication instead? Recommend the former (pipeline is the newer, config-driven approach and already owns input/prompt packaging).
2. **`run_crew_planbot` API** — should `PipelineEngine`/integrations pass an explicit proposal-def dict to `run_crew_planbot` (bypassing `load_planbot_config`), or should `load_planbot_config` learn to read from `pipeline.*`? The former is smaller and avoids touching `load_planbot_config`'s Pydantic model; the latter is cleaner long-term.
3. **`llm_model` vs `execution.model`** — the pipeline section already has `execution.model`; the top-level has `llm_model`. Dedupe to a single key (recommend keeping `llm_model` for CrewAI semantics, or map `execution.model`).
4. **`PipelineEngine.run()` vs `.prepare()`** — there is already a `_run_pipeline()` that synthesizes a temp config and invokes `run_crew_planbot`. Should the integrations switch to `run()` (removing the temp-config hack) or keep `.prepare()` + direct call? Recommend consolidating on `run()` with an explicit resolver factory.
5. **`stock_analysis_proposal`** — top-level only, CLI `run-planbot`-only, no `pipeline` entry. Keep as-is, or also migrate? Recommend out of scope.
6. **Orchestrator/filter removal blast radius** — `orchestrator.py` also defines `product_investor_matching_filter` / `client_holdings_filter` used by `run_configurations`. Confirm nothing else (tests aside) imports `ExecutionContext` / filters before deleting. (Only `pipeline_runner.py`, `proposal_executor.py`, and `tests/test_proposal_executor.py` import them today.)
