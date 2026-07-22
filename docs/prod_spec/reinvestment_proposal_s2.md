# Reinvestment Proposal – Sprint 2

## Overview

Sprint 1 delivered an end-to-end API-backed reinvestment proposal pipeline.
Sprint 2 hardens the architecture, improves production readiness, and adds
missing capabilities that were intentionally deferred.

The central architectural change in Sprint 2 is replacing the
**temp-file round-trip** with an **in-memory API resolver** inside
`load_references`.  When `get_client_product_from_db: true` is set on a
proposal, client profiles and product catalogs are fetched via API and
injected directly into the reference payload — no disk I/O, no temp-file
cleanup, no thread-safety issues.

## Design decision: boolean flag, not mixed YAML entries

Sprint 1 introduced a `get_client_product_from_db` toggle.
Sprint 2 places it under `common` so it applies to all proposals
(reinvestment, portfolio review, client product fit analysis,
product investor matching, stock analysis) that share the same
`run_crew_planbot` → `load_references` path.

**Config contract:**

```yaml
common:
  get_client_product_from_db: true   # applies to all proposals
  api_endpoints: http://localhost:8000/api/v1

reinvestment_proposal:
  references:
    client_profiles:
      - name: clients/*.md           # used only when flag is false
        purpose: Client profiles and suggested product for each client in markdown format
      - name: clients/*.csv          # used only when flag is false
        purpose: Client profiles and suggested product for each client in csv format
    product_catalogs:
      - name: ../shared/product_catalog/*.md
        purpose: Selected products to consider for reinvestment recommendation in markdown format
      - name: ../shared/product_catalog/*.csv
        purpose: Full list of the investable assets available for recommendation in csv format
      - name: ../shared/product_catalog/*.json
        purpose: Full product details including type_specific attributes in JSON format
```

## Sprint 2 scope

### 1. Merge reinvestment_proposal.py logic into CrewAI workflow

**Current state (Sprint 1):**
`src/integrations/reinvestment_proposal.py` contains substantial logic that
duplicates or runs parallel to the CrewAI workflow path:

- `_build_client_reference_files` — writes temp profile markdown + holdings CSV
- `_build_product_catalog_files` — writes temp catalog JSON
- `_build_llm_input` — assembles the LLM input payload
- `_process_one_target` — orchestrates fetch → temp files → CrewAI → cleanup

These functions live outside `crew_workflow.py` / `input_loader.py` and are
not reusable by other proposals (portfolio review, client product fit analysis).

**Target (Sprint 2):**
Eliminate temp files and merge the remaining logic into the shared workflow path:

| Current location | Merge target |
|---|---|
| `_build_client_reference_files` | Removed (replaced by §2 `api_resolver`) |
| `_build_product_catalog_files` | Removed (replaced by §2 `api_resolver`) |
| `_build_llm_input` | Move to `src/planbot/workflow.py` as a single shared `_build_llm_input` usable by all proposals (reinvestment, portfolio review, client product fit analysis). Different proposals pass different data blocks but the assembly pattern is the same. |
| `_process_one_target` | Simplify to thin caller: fetch data → build resolver → `run_crew_planbot` |
| `propose_reinvestment` | Keep as public API entry point; delegate internals to shared workflow |

The end state: `reinvestment_proposal.py` is a thin API layer.  All
reference assembly and CrewAI invocation flows through the shared
`crew_workflow.py` / `input_loader.py` path.

**Implementation note:** Tasks in this section and §2 that touch
temp-file logic should be done together in a single pass to avoid an
intermediate broken state.

**Acceptance criteria:**
| # | Criterion | Verification |
|---|---|---|
| AC1 | `reinvestment_proposal.py` no longer creates temp files | Unit test + code review |
| AC2 | `_build_llm_input` logic moves to `src/planbot/workflow.py` as a single shared function for all proposals | Code review |
| AC3 | `propose_reinvestment` delegates to shared `run_crew_planbot` path | Integration test |
| AC4 | Existing regression test passes unchanged | `pytest tests/test_run_client_investment_proposal.py::test_propose_reinvestment_for_maturing_holdings` |
| AC5 | FastAPI integration: `POST /api/v1/reinvestment-proposals` returns 200 with valid payload (use `TestClient`, not real server) | `pytest tests/test_reinvestment_proposal.py::test_fastapi_propose_reinvestment` |

---

### 2. In-memory API resolver in load_references (replaces temp-file approach)

**Current state (Sprint 1):**
`ProposalExecutor._create_client_reference_files` writes per-client
`{client_id}_profile.md`, `{client_id}_holdings.csv`, and optionally
`{client_id}_demographics.md` to disk.  These files are passed as
`runtime_reference_overrides` → `load_references` globs them back from
disk → `ReferenceDocument` list.

**Problems:**
- Filesystem round-trip adds latency and I/O.
- Temp-file cleanup is fragile (`cleanup_temp_files` must walk directory
  trees and handle OS-level edge cases).
- Multi-threaded fan-out risks filename collisions under the same
  `generated_dir`.

**Target (Sprint 2):**
Extend `load_references` with an `api_resolver` callable.  When a glob
starts with `api://`, delegate to the resolver instead of the filesystem.
The resolver returns `ReferenceDocument` objects with content populated
in-memory — no disk.

```python
# input_loader.py — signature extension
def load_references(
    root_dir: Path,
    glob_pattern: str | list[str],
    api_resolver: Callable[[str], ReferenceDocument] | None = None,
) -> list[ReferenceDocument]:
```

**API resolver contract:**

A resolver is a simple callable `(api_path: str) -> ReferenceDocument`.
The call site builds it with the client/product context it has.
The resolver factory owns the `api://` path-to-API mapping; call sites
pass only the `client_id`.

When the underlying API call fails (connection refused, timeout, 5xx),
the resolver raises with a clear message.  In multi-proposal runs, skip
only the affected proposal; others continue.

```python
def _build_api_resolver(client_id: str) -> Callable:
    def resolve(api_path: str) -> ReferenceDocument:
        if api_path == "api://client_profile":
            data = search_by_id(client_id)       # v1: local import; v2: FastAPI HTTP
            return ReferenceDocument(
                path=Path(f"api://client/{client_id}"),
                content=json.dumps(data, ensure_ascii=False, default=str),
                source_type="api_json",
            )
        if api_path == "api://product_catalog":
            data = search_aligned_products(...)   # v1: local import; v2: FastAPI HTTP
            return ReferenceDocument(...)
        raise ValueError(f"Unknown API path: {api_path}")
    return resolve
```

**Migration path from local import to FastAPI HTTP:**
- **Phase A (Sprint 2 initial):** `api_resolver` calls `src.integrations.*`
  directly (local Python import).  This eliminates temp files immediately.
- **Phase B (Sprint 2 final):** `api_resolver` calls FastAPI endpoints
  (`GET /api/v1/clients/{client_id}`, `GET /api/v1/products/search`, etc.)
  over `localhost`.  Zero code changes in `load_references` or
  `crew_workflow.py` — only the resolver factory changes.

| Phase | Client lookup | Product lookup |
|---|---|---|
| A | `search_by_id(client_id)` (local import) | `search_aligned_products(...)` (local import) |
| B | `GET /api/v1/clients/{client_id}` (HTTP) | `GET /api/v1/products/search` (HTTP) |

**ProposalExecutor changes:**

`_create_client_reference_files` is **removed**.  Instead, the executor
builds an `api_resolver` for the current client and passes it through
`runtime_reference_overrides` to `run_crew_planbot`.  The overrides dict
now carries `api://` patterns instead of filesystem paths:

```python
# Before (Sprint 1)
runtime_overrides = {
    "client_profiles": [
        self._to_relative_path(profile_file),   # temp file on disk
        self._to_relative_path(holdings_file),   # temp file on disk
    ],
}

# After (Sprint 2)
runtime_overrides = {
    "client_profiles": ["api://client_profile"],
}
```

**Files changed:**
| File | Change |
|---|---|
| `src/planbot/input_loader.py` | `load_references` gains `api_resolver` parameter |
| `src/planbot/crew_workflow.py` | `run_crew_planbot` passes `api_resolver` through |
| `src/planbot/proposal_executor.py` | Remove `_create_client_reference_files`, `cleanup_temp_files`, `_format_holdings_as_csv`, `_format_profile_data_as_markdown`; build resolver instead |
| `src/planbot/config.py` | Parse `get_client_product_from_db` from `common` section |
| `config/config_planbot.yaml` | Add `get_client_product_from_db: true` under `common` |

**Acceptance criteria:**
| # | Criterion | Verification |
|---|---|---|
| AC6 | `load_references` delegates `api://` patterns to `api_resolver` | Unit test with mock resolver |
| AC7 | `load_references` falls back to filesystem glob for non-`api://` patterns | Unit test with real file glob |
| AC8 | `ProposalExecutor` no longer creates temp files on disk | Unit test asserting no `write_text` calls |
| AC9 | `get_client_product_from_db: true` causes `api://` patterns to be used | Integration test with real DB |
| AC10 | `get_client_product_from_db: false` (or absent) uses file globs unchanged | Regression test |
| AC11 | Client profile and product catalog appear in `loaded_sections` with `source_type="api_json"` | Unit test |
| AC12 | Existing tests pass without modification | `pytest tests/` |

---

### 3. Discovery/orchestration endpoint (HTTP wrapper)

**Current state (Sprint 1):**
The Python function `propose_reinvestment_for_maturing_holdings` is already
implemented in `src/integrations/reinvestment_proposal.py`.  It calls
`search_holdings_maturing` internally, deduplicates by client, caps at
`max_clients`, and delegates to `propose_reinvestment`.  The heavy lifting
is done — only the HTTP endpoint wrapper is missing.

**Target (Sprint 2):**
Wrap the existing Python function with a thin FastAPI endpoint:

- `POST /api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings`

The endpoint delegates directly to the existing function.  No logic moves.

**Request:**

```json
{
  "product_types": ["bond", "bond_fund"],
  "within_days": 180,
  "response_mode": "path",
  "include_debug_scores": false
}
```

**Acceptance criteria:**
| # | Criterion | Verification |
|---|---|---|
| AC13 | Discovery endpoint accepts `product_types`, `within_days` | Integration test |
| AC14 | Output matches `POST /api/v1/reinvestment-proposals` response shape | Snapshot test |
| AC15 | Falls back gracefully when no maturing holdings are found | Unit test |
| AC16 | End-to-end regression: existing test passes | `pytest tests/test_run_client_investment_proposal.py::test_propose_reinvestment_for_maturing_holdings` |
| AC17 | FastAPI integration: `POST .../propose_reinvestment_for_maturing_holdings` returns 200 (use `TestClient`, not real server) | `pytest tests/test_reinvestment_proposal.py::test_fastapi_propose_reinvestment_for_maturing_holdings` |



## Tasks

### Phase A — merge-back + no temp files, local imports

| # | Task | Files |
|---|---|---|
| T1 | Merge `_build_llm_input` and `_process_one_target` logic from `reinvestment_proposal.py` into shared `crew_workflow.py` / `workflow.py` | `src/integrations/reinvestment_proposal.py`, `src/planbot/workflow.py` |
| T2 | Extend `load_references` with `api_resolver` parameter | `src/planbot/input_loader.py` |
| T3 | Add `api_resolver` passthrough in `run_crew_planbot` | `src/planbot/crew_workflow.py` |
| T4 | Parse `get_client_product_from_db` in `PlanBotConfig` | `src/planbot/config.py` |
| T5 | Replace `_create_client_reference_files` with in-memory resolver in `ProposalExecutor` | `src/planbot/proposal_executor.py` |
| T6 | Add `get_client_product_from_db: true` under `common` in config | `config/config_planbot.yaml` |
| T7 | Add unit tests for `api://` path in `load_references` | `tests/` |
| T8 | Remove `cleanup_temp_files` and related helpers | `src/planbot/proposal_executor.py` |
| T9 | Add FastAPI integration test: `POST /api/v1/reinvestment-proposals` | `tests/test_reinvestment_proposal.py` |

### Phase B — FastAPI HTTP switch + HTTP endpoints

| # | Task | Files |
|---|---|---|
| T10 | Replace local imports in api_resolver with HTTP calls to FastAPI | `src/planbot/crew_workflow.py` or new resolver module |
| T11 | Add retry/timeout config for HTTP calls | `config/config_planbot.yaml` |
| T12 | Add HTTP endpoint wrapper for `propose_reinvestment_for_maturing_holdings` | `src/integrations/server.py` |
| T13 | Add FastAPI integration test: `POST .../propose_reinvestment_for_maturing_holdings` | `tests/test_reinvestment_proposal.py` |

## Open questions

| # | Question | Recommendation |
|---|---|---|
| O1 | **FastAPI server lifecycle in tests.** T9, T13 need a running server. Options: `TestClient` (in-process, no port binding) or spawn `uvicorn` for true integration tests. | Use `TestClient` for Sprint 2; real-server tests deferred until CI has service orchestration. |
