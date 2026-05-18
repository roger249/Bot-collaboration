Pipe and filter between report
==============================

# Introduction

The idea is to build a generic data pipe and filter infrastructure to chain proposal runs so one orchestrated run can generate all downstream proposals with consistent inputs and logs.

We have three client proposals that are related for now. Details in the configuration file config/config_planbot.yaml

1. product_investor_matching
    - Input is a list of clients and their holdings under data/planbot/shared/client_profile
    - Output is 10 selected clients and their recommended products in md format
2. client_product_fit_analysis
    - Input is holding and profile of one client under data/planbot/client_product_fit/clients.  
3. portfolio_review
    - Input is holding and profile of one client under data/planbot/portfolio_review/clients

To produce 2 properly, the flow is as below.

```python
for each client_id, client_profile in outputs(product_investor_matching):
    client_holding= extract_holding(holding_csv, client_id)
    client_product_fit_analysis(client, client_holding)
    # portfolio_review(client, client_holding)
```

I'd like a pipe and filter module to orchestrate the execution of the above logic in a configurable way.  Please refer to section "run_configurations" in the configuration file config/config_planbot.yaml

- Ideally the data between the execution are stored in memory and generate on the fly.
- The file to read, or generate shall refer to the corresponidng section of the proposal definition in the config_planbot.yaml
- The number of executions for a proposal solely depends on the number of items in the list of the first line of the section client_profiles.  In current configuration file it's the number of items in the client_profiles
- Any failure of the report will be logged.  The run will continue at its best effort.  So one failure will be limited to one client proposal only.  no retry needed.
- For each new execution, if the output_folder has the file of same name, it'll be overwritten.

# Execution contract (proposed)

## 1) Canonical pipeline

1. Run product_investor_matching once.
2. Filter output into `client_profiles` and `client_ids`.
3. Enrich each client id with holding data from shared csv.
4. Fan out one execution per client id for downstream proposal(s).
5. Persist each proposal output file with deterministic name.

## 2) Fan-out rule

- The execution count is determined by the length of the `from` source list: `product_investor_matching_filter.output.client_profiles`.
- One item in that list maps to one client execution context.
- The `alias` section binds placeholder names to filter outputs; each alias value is resolved per iteration.
- If a client id is missing after filtering, skip that item and log as warning.

## 3) Per-iteration context binding

During each fan-out iteration, the orchestrator resolves placeholder values from the `alias` section and `references_section_binding`:

- `client_id`: extracted from `alias.client_id` binding (resolved per iteration from client_ids list).
- `client_profile_markdown`: from `references_section_binding[0]` (product_investor_matching_filter output).
- `client_holding`: from `references_section_binding[1]` (client_holdings_filter output, keyed by client_id).

Example resolved context for one client iteration:

```
client_id = "C0001"
client_profile_markdown = <section from product_investor_matching_filter matching "## Client ID: C0001">
client_holding = <entry from by_client_id["C0001"]>
output_file = "runs/sample_outputs/client_product_fit_analysis_C0001.md"
```

## 4) Fan-out binding contract

Define in the `alias` section which placeholder names are available for use in `references_section_binding` and `output_file`.

Example:

```yaml
alias:
  client_id: product_investor_matching_filter.output.client_ids
```

**Rule:** Every placeholder token used downstream (e.g., `{client_id}`) must be defined as a key in `alias`. If a token is used but not defined, the orchestrator will fail validation.

## 5) References section binding

The `references_section_binding` list provides per-client data files to inject into proposal references at runtime.

Example:

```yaml
references_section_binding:
  - product_investor_matching_filter.output.client_profiles.{client_id}.md
  - client_holdings_filter.output.by_client_id.{client_id}.md
```

Each item is resolved with `alias` values substituted, and the result is passed to the proposal's `client_profiles` reference section.

## 6) Failure and overwrite policy

- Per-client isolation: one failed client must not stop the run.
- No retry by default (`retry_count = 0`).
- Continue best-effort for remaining clients.
- Output file overwrite is allowed for same file name.

## 7) Logging contract

For each run:
- Log start/end timestamps and run_id.
- Log selected client count.

For each client:
- Log `client_id`, proposal name, output path, status (`success|failed|skipped`).
- Log failure reason if failed.

**Log fields:**

```text
run_id, stage, proposal, client_id, status, output_path, elapsed_ms, error
```

## 8) Config binding rule

Each proposal step in `run_configurations` must map to an existing top-level proposal section in `config_planbot.yaml`.

Example:
- `execute.proposal: client_product_fit_analysis` must map to top-level section `client_product_fit_analysis`.
- Its input/output folders should still be taken from that section unless the run config explicitly overrides output file name.

# Minimal implementation notes

## Runtime ordering

1. Build all filters first (matching -> ids -> holdings).
2. Build a list of execution contexts (one context per client).
3. Run downstream proposals sequentially per client (safe default).
4. Add optional parallelism later with stable deterministic output paths.

## Validation before run

- Confirm all filter output references in `fan_out.from`, `alias`, and `references_section_binding` can be resolved.
- Confirm proposal names in `execute` exist as top-level config sections.
- Confirm output template contains `{client_id}` or other defined placeholder when fan-out is active.
- Fail fast only on invalid pipeline definition; do not fail fast on one client execution.
