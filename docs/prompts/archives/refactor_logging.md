# Refactor PlanBot Logging

We refactor the existing logging mechanism to fix long-standing bugs and
ensure all acceptance criteria are validated by unit tests.

## Context & current bugs

The logging subsystem suffers from seven concrete bugs that have persisted
across multiple rounds of changes:

| # | Bug | File / location | Impact |
|---|-----|-----------------|--------|
| 1 | **`api_debug_level` is dead config and over-engineered** | `config.yaml` → `AppConfig` → `configure_logging()` → `fileConfig(defaults=…)` | The value flows through 4 layers only to land in `fileConfig`'s `defaults` dict — but `logging_config.ini` has no `%(api_debug_level)s` placeholder, so it's silently ignored.  The fix is to **delete** the entire chain and set the `src.integrations` level directly in the ini. |
| 2 | **IRS scorecard only logs at DEBUG** | `src/integrations/client_api.py` : `search_by_investor_readiness_score` | Request + response are `LOGGER.debug(…)` only.  When the root logger is at INFO there is *zero* trace of an IRS call — impossible to debug scoring issues in production. |
| 3 | **PFS scorecard logs component scores at INFO** | `src/integrations/product_tool.py` : `search_product_by_fitness_score` | The fix applied 2026-07-31 logs per-client top-3 with full component breakdowns at INFO.  Per the AC, INFO should be brief; component detail belongs at DEBUG. |
| 4 | **Log files created under `runs/`** | `src/planbot/pipeline_runner.py` : `run_pipeline()` | Calls `configure_logging()` with a pipeline-scoped path under `runs/pipelines/…/logs/`.  Stale log files from old runs remain on disk (e.g. `runs/reinvestment_proposal/…/logs/planbot.log`). |
| 5 | **Standalone CLI uses `logging.basicConfig`** | `src/planbot/investor_readiness_score.py` line 734 | When the module runs via `python investor_readiness_score.py`, it bypasses `logging_config.ini` and creates its own handler.  Behavior differs between CLI and server modes. |
| 6 | **`configure_logging` fights with `logging_config.ini`** | `src/shared/logging_utils.py` : `_configure_chat_history_logger` | After `fileConfig()` loads `logging_config.ini` (which defines a `chat_history` logger with `chatHistoryFileHandler` writing to `log/chat_history.log` in *overwrite* mode), the code immediately calls `_configure_chat_history_logger()` which **removes all handlers** and adds a `RotatingFileHandler` in *append* mode.  The `.ini` definition is dead on arrival. |
| 7 | **CrewAI verbose trace mixed into `planbot.log`** | `src/planbot/crew_workflow.py` : `_tee_stdout_to_log` | When `crewai_verbose` is enabled, CrewAI's execution trace (task/agent progress, tool calls, thinking output) is tee'd from stdout directly into `log/planbot.log`.  This noise drowns out structured application log messages, making post-mortem analysis harder. |

## Design decisions

### 1. `logging_config.ini` is the single, self-contained source

`config/logging_config.ini` is the *only* place that defines handlers,
formatters, files, and logger levels.  Every level is a literal value
(`DEBUG`, `INFO`, etc.) — no `%(…)s` placeholders that require a `defaults`
dict.  You can point `logging.config.fileConfig()` at it with no arguments
and it works.

No ad-hoc `logging.basicConfig()` anywhere in `src/`.  The `api_debug_level`
key is **removed** from `config.yaml` and `AppConfig` — the `src.integrations`
logger level is set directly in the ini like every other logger.

A single `init_logging()` helper in `src/shared/logging_utils.py` wraps
`fileConfig(ini_path)` and handles the `log/` directory creation.  Every
module that needs logging — servers, pipelines, CLI entry points — calls
this one function.  No module touches `logging.config` directly.

### 2. Two log directories — no crossover

- **`log/`** — Permanent log files (overwritten per execution in dev,
  rotation-ready in prod).  Root logger, chat_history, and integration
  loggers write here.
- **`runs/`** — Generated proposal output (markdown, JSON, generated
  inputs).  *No log files of any kind belong here.*

### 3. Scorecard logging discipline

Each scorecard follows the *same* pattern:

- **INFO**: one line summarising the call and its result (counts only).
- **DEBUG**: full request parameters and response payload (up to a
  truncation limit).

This applies to:

- **IRS** — `search_by_investor_readiness_score()` in
  `src/integrations/client_api.py`
- **PFS** — `search_product_by_fitness_score()` in
  `src/integrations/product_tool.py`

### 4. CrewAI trace has its own logger and file

CrewAI verbose output (agent thought process, task execution progress, tool
invocations) is *not* application log data — it is third-party library trace
output.  We channel it through a dedicated `crewai_trace` logger writing to
`log/crewai_trace.log`, completely separate from `log/planbot.log`.

Implementation:

- `_tee_stdout_to_log()` is replaced by a `crewai_trace` logger handler that
  receives the stripped stdout stream.
- The `crewai_trace` logger is defined in `logging_config.ini` with its own
  file handler.  It does **not** propagate to the root logger so trace noise
  never appears in `planbot.log`.  The handler always exists (file is
  overwritten each run).  When `crewai_verbose` is *disabled*, the file is
  created but left empty — no conditional handler registration, no
  conditional file creation.

## Acceptance criteria

Each AC has one or more unit tests that validate it in isolation.

| AC | Description | Test approach |
|----|-------------|---------------|
| AC-1 | All logs live under `log/`.  The only log files created by any code path are `log/planbot.log`, `log/chat_history.log`, and `log/crewai_trace.log`.  No log file or `logs/` directory is created anywhere under `runs/`. | Call `init_logging()`, inspect handler filenames on all loggers, assert every path starts with `<root>/log/` and the set of filenames is exactly `{planbot.log, chat_history.log, crewai_trace.log}`. |
| AC-2 | No `.log` files exist under `runs/`.  `pipeline_runner.py` uses `init_logging()` (which writes to `log/`) instead of creating a pipeline-scoped log path under `runs/`. | Run a pipeline, `os.walk(runs/)`, assert zero files ending in `.log`. |
| AC-3 | IRS scorecard logged at INFO (brief) and DEBUG (full).  INFO: one line with client count.  DEBUG: full request + response (first 5 clients, truncated). | `assertLogs(INFO)` → brief message present, full payload absent.  `assertLogs(DEBUG)` → both present. |
| AC-4 | PFS scorecard logged at INFO (brief) and DEBUG (full).  INFO: one summary line with pair/client counts.  DEBUG: per-client component breakdowns + final trimmed result. | Same `assertLogs` technique as AC-3. |
| AC-5 | `src.integrations` logger level is controlled by `logging_config.ini`.  Changing the ini's `[logger_src.integrations]` `level=` between `INFO` and `DEBUG` toggles scorecard detail, with zero code changes. | Load ini with `level=DEBUG`, call a scorecard, assert DEBUG messages appear.  Edit ini to `level=INFO`, reload, assert only INFO+ messages. |
| AC-6 | No `logging.basicConfig()` anywhere in `src/**/*.py`.  The `investor_readiness_score.py` `__main__` block uses `init_logging()`. | `grep` across `src/` for `basicConfig` → zero results. |
| AC-7 | `logging_config.ini` is the sole handler config.  No code-side removal/replacement of chat_history handlers after `fileConfig`.  chat_history logger has exactly 1 file handler. | Call `init_logging()` with the ini, inspect `logging.getLogger('chat_history').handlers` → exactly 1, no `RotatingFileHandler`. |
| AC-8 | CrewAI verbose trace writes to `log/crewai_trace.log` only.  Zero CrewAI trace lines appear in `log/planbot.log`.  When `crewai_verbose` is off, `crewai_trace.log` is empty (0 bytes). | Enable `crewai_verbose=True`, run a proposal, assert `log/crewai_trace.log` has content and `log/planbot.log` contains no ANSI escape codes or CrewAI progress-bar artifacts.  With `crewai_verbose=False`, assert `crewai_trace.log` is 0 bytes. |
| AC-9 | `logging_config.ini` is self-contained.  Every logger level is a literal value (no `%(…)s` placeholders).  Calling `fileConfig(ini_path)` with no `defaults` dict produces a fully working logging setup. | Parse the ini with `configparser`, assert no value contains `%(`.  Then `fileConfig()` it bare and assert the root logger handles events at the expected level. |
| AC-10 | One `init_logging()` helper initializes all logging.  No module calls `logging.config.fileConfig()`, `logging.basicConfig()`, or `logging.FileHandler()` directly — they all import and call `init_logging()` from `src.shared.logging_utils`. | Grep `src/` for `fileConfig|basicConfig|FileHandler(` — only `logging_utils.py` should match.  The test itself calls `init_logging()` and asserts loggers are set up. |
| AC-11 | `init_logging()` is idempotent.  Calling it twice in the same process does not double-register handlers, duplicate log lines, or raise an error. | Call `init_logging()` twice, count handlers on every logger, assert count equals the count after the first call. |
| AC-12 | `init_logging()` creates the `log/` directory if it does not exist.  Calling `init_logging()` on a fresh workspace (no `log/` dir) succeeds without `FileNotFoundError`. | `tmp_path` fixture, delete `log/` if present, call `init_logging()`, assert `log/` exists and log files were created inside it. |

## Implementation plan

1. **Fix `logging_config.ini`** — make it self-contained (literal level
   values, no `%(…)s` placeholders).  Set `[logger_src.integrations]`
   `level=INFO` (production default; change to `DEBUG` when troubleshooting).
   Add `[logger_crewai_trace]` section writing to `log/crewai_trace.log`
   with `propagate=0`.  Keep `chatHistoryFileHandler` as the sole handler
   for chat_history (remove the code-side override that replaces it).

2. **Fix `logging_utils.py` — replace `configure_logging` with `init_logging`**
   — add a single `init_logging()` function that calls
   `fileConfig(config/logging_config.ini)`, creates the `log/` directory,
   and is idempotent (no-op on subsequent calls).  Remove `api_debug_level`
   parameter, the `defaults=` dict, and the `_configure_chat_history_logger`
   handler-removal code.  `init_logging()` is the *only* function that
   touches `logging.config`.

3. **Fix `config.yaml` and `config_loader.py`** — delete the
   `api_debug_level` key from `config.yaml`.  Remove
   `logging_api_debug_level` from `AppConfig` and the `RawLogging` Pydantic
   model.  Remove `configure_logging` parameters from all call sites.

4. **Consolidate all call sites to `init_logging()`** — replace direct
   `fileConfig()` in `data_server.py:43` and `proposal_server.py:312`.
   Replace `configure_logging()` in `author_reviewer/crew_workflow.py`,
   `author_reviewer/workflow.py`, and `pipeline_runner.py`.  Replace
   `basicConfig()` in `investor_readiness_score.py:734`.  After this,
   `grep -rn 'fileConfig|basicConfig|FileHandler(' src/` returns only
   `logging_utils.py`.

5. **Fix `client_api.py`** — add INFO-level log line to
   `search_by_investor_readiness_score()` with brief summary; keep
   existing DEBUG lines.

6. **Fix `product_tool.py`** — move component-detail logs from INFO to
   DEBUG; keep only a single summary line at INFO.

7. **Fix `crew_workflow.py`** — replace `_tee_stdout_to_log` with a
   `crewai_trace` logger.  The trace logger is defined in
   `logging_config.ini` with a dedicated `log/crewai_trace.log` handler
   and `propagate=0`.

8. **Add unit tests** — one test class per AC in
   `tests/test_logging_refactor.py`, using `assertLogs`,
   `unittest.mock.patch`, and `logging.config.dictConfig`.

