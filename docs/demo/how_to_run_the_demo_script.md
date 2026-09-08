# How to Run the Demo Script

This guide covers the data the demo depends on, the pytest command to execute
the demo, and how to examine the generated proposals.

The demo is implemented as three `pytest` tests (not a standalone script), so it
doubles as an end-to-end regression of the proposal pipeline and runs one step
at a time from the VS Code Test explorer (or the CLI).

- Narrative / what each scenario proves: [`docs/specification/demo/demo_flow.md`](../specification/demo/demo_flow.md)
- Exact client/product IDs + data baseline: [`docs/specification/demo/demo_test_data.md`](../specification/demo/demo_test_data.md)
- HTTP mutation/reset surface: [`docs/specification/demo/demo_tool_api.md`](../specification/demo/demo_tool_api.md)
- Test file: [`tests/test_demo_flow.py`](../../tests/test_demo_flow.py)

---

## 1. Prerequisites (data)

The demo runs against the seeded DuckDB at `data/planbot/db/planbot.duckdb`. It
requires:

| Item | Where |
|---|---|
| Client `PB-HK-000001-8` (David Kim, risk 4) | Demo 1 (RM note) |
| Client `PB-HK-000002-6` (Sarah Chen, risk 5) | Demo 2 (structured product) |
| 6 × `FX-TARF-*` products | Demo 2 (`structures` group) |
| `PROD053` bond (maturity `2026-08-31`) | Demo 3 (reinvestment) |

The FX-TARF products + tuned clients are seeded per
[`docs/how_to/how_to_add_fx_tarf.md`](./how_to_add_fx_tarf.md); the rest come
from the standard client/product seeders. No additional data patching is needed
— Demo 1's RM-note mutation and reset are performed **over HTTP** by the demo
control endpoints (see §4).

### Provider key

The proposal LLM calls need the configured provider key. For the default
`bacherlier` provider this is `BACHERLIER_API_KEY`, loaded from `.env`:

```dotenv
BACHERLIER_API_KEY=<your_key>
```

> The tests start the FastAPI server **in-process** (a background thread), so
> you do **not** need a separate running server.  The server reads `.env` if the
> test process has those vars exported (the CLI examples below do this).

---

## 2. Run the demo

### 2.1 From the command line

Run all three demos (real LLM, slow):

```bash
cd "/Users/roger/Documents/GitHub/Bot collaboration"
set -a && source .env && set +a
.venv/bin/python -m pytest tests/test_demo_flow.py --run-slow -s -v
```

- `--run-slow` — required: the demos are marked `slow` (real LLM) and are
  skipped otherwise.
- `-s` — show the per-demo `print(...)` lines (the product change / timing).
- `-v` — one line per test.

Run a single demo (e.g. just the RM-note flip):

```bash
.venv/bin/python -m pytest tests/test_demo_flow.py::test_demo1_rm_note_changes_recommendation --run-slow -s -v
```

### 2.2 From the VS Code Test explorer

1. Open the **Testing** view (beaker icon).
2. Find `test_demo_flow.py` → the three `test_demo*` functions.
3. Click the green ▶ run button on an individual test (or the file).

> If VS Code shows the tests as **skipped**, the runner is not passing
> `--run-slow`.  Set `"python.testing.pytestArgs": ["--run-slow"]` in
> `.vscode/settings.json`, or run from the terminal as in §2.1.

---

## 3. What each demo does (and asserts)

| Test | Scenario | Assertion |
|---|---|---|
| `test_demo1_rm_note_changes_recommendation` | Mutate David Kim's `qualitative_profile` to favour technology, then re-run the matcher | recommended `product_id` changes (or the narrative turns tech) |
| `test_demo2_structured_product_proposed` | Run the matcher over the `structures` group for Sarah Chen | top pick starts with `FX-TARF-` |
| `test_demo3_reinvestment_discovery` | Discover maturing holdings with a pinned `as_of_date` | ≥1 client + a generated proposal |

Demo 1 prints the concrete flip, e.g.:

```
Demo1: before=PROD008 (…s) -> after=PROD001 (…s) changed=True
```

Demo 3 pins `as_of_date: "2026-08-01"` so the seeded `PROD053` (maturity
`2026-08-31`) is deterministically "maturing" regardless of the real system date.

---

## 4. Examine the results (proposals)

The generated markdown proposals are written under `runs/`:

| Demo | Output folder |
|---|---|
| 1 & 2 | `runs/product_investor_matching/` and `runs/product_opportunity_proposal/` |
| 3 | `runs/reinvestment_proposal/` |

The API response also returns `proposal_markdown` inline, but for a
presentation-ready read, open the newest `.md` file in the matching folder:

```bash
ls -t runs/product_investor_matching/*.md | head
ls -t runs/reinvestment_proposal/*.md | head
```

Useful runtime detail:

- `runs/<proposal>/<run_id>/prompt_snapshot.md` — the exact prompt sent to the
  LLM (sections, references, model). Good for verifying the RM note / product
  catalog reached the model.
- `log/planbot.log` and `log/crewai_trace.log` — pipeline + CrewAI trace.

---

## 5. Reset (repeatability)

Each test's teardown calls `POST /api/v1/demo/reset`, restoring the canonical
baseline (David Kim's original `qualitative_profile`). You can also reset
manually when the server is running:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/demo/reset
```

The demo control endpoints are gated by `demo_tools.enabled` in
`config/config_planbot.yaml` (default `true`); with `false` they return `404`.

---

## 6. Known caveats

1. **Model non-determinism.** The matcher's default model
   (`bacherlier_deepseek` → `deepseek-v4-flash-0731`) occasionally short-circuits
   and returns a tiny JSON fragment instead of the ranking markdown, which makes
   Demo 1 fail intermittently. Re-run the single test; a fix (model switch or
   output validation/retry) is a follow-up.
2. **Run duration.** Each demo makes several real LLM calls; the full set takes
   on the order of **minutes** (cold) and is cache-assisted on repeats.
3. **No concurrent execution.** The demo tests share the single DuckDB file
   `data/planbot/db/planbot.duckdb`, and Demo 1 mutates it via a transient
   read-write connection.  Run the demos **sequentially** (pytest's default) —
   do not run them in parallel (e.g. `pytest-xdist`), or DuckDB's single-writer
   constraint will cause lock/`file in use` errors.

---

## 7. Observed run durations (reference)

Recorded from a real end-to-end run (cache enabled) — use as a rough baseline
expectation, not a guarantee. The LLM provider (`bacherlier` → Aliyun MaaS
`deepseek-v4-flash-0731`) is the dominant variable; a slow/stalled provider call
inflates these numbers via the client's retry/backoff.

| Run | Scope | Result | Duration |
|---|---|---|---|
| Full demo suite (`tests/test_demo_flow.py --run-slow`) | 3 demos, ~5 LLM invocations | 2 passed, 1 failed (model short-circuit) | **9:04** (544.6 s pytest time) |
| Demo 1 — "before" call | one automatch (matcher + PFS + LLM) | — | **403.7 s** |
| Demo 1 — "after" call | one automatch | — | **466.7 s** |

Key takeaways for setting expectations:

- The **cold** cost is dominated by the LLM call — single calls can be several
  minutes.  The embedding model (`e5-base-v2`) loads once per process at
  **~10 s**, a negligible share of a multi-minute call.
- The demo tests start a **fresh server per test** (function-scoped fixture), so
  they do not share a warm process; a single long-lived server would amortize the
  ~10 s embedding-model load across demos.
