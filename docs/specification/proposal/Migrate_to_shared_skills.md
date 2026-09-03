# Migrate to Shared Skills

Date: 2026-09-03
Status: Draft for discussion

---

## 1. Purpose

Allow a shared block of prompt text (for example, the cross-proposal general guidelines)
to be authored once and injected into multiple proposal task prompts, without duplicating
the text in every `data/planbot/<proposal>/crewai/tasks.yaml`.

The mechanism uses CrewAI's built-in **Agent Skills** (`SKILL.md`): a shared instruction
fragment is packaged as a skill directory and attached to the agents that need it. CrewAI
discovers the skill, loads its instruction body, and appends it to the task prompt at
execution time — no custom templating or resolver code is required.

---

## 2. Background / Problem

Several proposals (`product_investor_matching`, `llm_product_matcher`, `reinvestment`,
`product_opportunity`, `portfolio_review`) contain near-identical instruction blocks —
for example, the rules for recommending a product (scoring, one recommendation per
client, funding source, diversification caps, return/liquidity thresholds). Today these
are copy-pasted into each proposal's `tasks.yaml` `description:`, so a rule change must be
applied in N places and can drift.

We already have one attempt at this — `data/planbot/shared/common/general_guideline.md` —
but it is wired in two inconsistent ways:

1. A **decorative pointer** in `tasks.yaml` (`Observe the guideline
   ../shared/common/general_guideline.md`) that the LLM cannot actually read (the agent
   has no filesystem tools).
2. A **reference input** (`general_guidelines` under `pipeline.*.inputs`) that loads the
   file into the JSON reference payload, which the prompt itself labels *"not as
   instructions"*.

The result is that instruction-grade content ends up in a channel meant for reference
material, and the pointer in `description` is inert.

This spec formalizes a single, correct channel for shared **instruction** content, using
CrewAI's native Skill mechanism.

---

## 3. Design Decision

### 3.1 Two channels, one rule

The prompt is assembled from two structurally different channels (see `src/planbot/workflow.py`):

| Channel | Source | Nature | Carrier |
|---|---|---|---|
| **Task prompt** | `tasks.yaml` `description:` + skill context | Imperative — what the model must *do* | `Task.description` |
| **Reference payload** | `pipeline.*.inputs` | Reference material — *not instructions* | appended JSON sections |

Rule: **instruction content is injected into the task prompt channel; reference/format
content stays in the reference payload channel.** The "how to recommend a product" block
is instruction content, so it belongs in the task prompt.

### 3.2 Use CrewAI Agent Skills

CrewAI 1.14.4 (and later) ships a built-in **Agent Skills** mechanism
(`crewai/skills/*`) that satisfies the requirement without custom code:

- **Direct substitution semantics** — the skill's instruction body is inlined into the
  task prompt at execution time (via `append_skill_context`), not a "go read this file"
  pointer.
- **Filesystem discovery** — CrewAI reads the file for us; there is no file-read code to
  write.
- **Deterministic and maintained** — the mechanism is first-class, versioned, and
  actively maintained across CrewAI releases.

We reject an indirect "go read this file" pointer because agents have no filesystem
 tools, and indirect reasoning is unreliable on the small/cheap models this project uses.

### 3.3 Design trade-offs

Agent Skills move the file-read into CrewAI (no custom resolver code), at the cost of two
conventions this spec accepts:

1. A **structured convention** — directory + `SKILL.md` + YAML frontmatter instead of a
   flat markdown file.
2. **Append semantics** — skill content is appended as a `## Skill:` section to the task
   prompt, rather than substituted at an arbitrary position.

Both are lightweight and acceptable: the convention is small, and appended instruction
content is functionally equivalent for our use case (shared rules that must always be
observed).

---

## 4. How CrewAI Agent Skills work (mechanism)

This section describes the behavior of the installed `crewai` package (verified against
1.14.4).

### 4.1 `SKILL.md` structure

A skill is a **directory** containing a `SKILL.md` file. The file has YAML frontmatter
(delimited by `---`) followed by the instruction body:

```markdown
---
name: product-recommendation
description: Rules for recommending an investment product to a client
allowed-tools: search_similar
---

- Assign each client a 1-5 buying score indicating likelihood to buy.
- Only one product recommendation is allowed per client.
- ...
```

- **Frontmatter** = machine-readable metadata (validated).
- **Body** = the instruction content injected into the prompt.

### 4.2 Frontmatter constraints

Validated by `crewai/skills/validation.py` and `crewai/skills/models.py`:

| Field | Required | Constraint |
|---|---|---|
| `name` | ✅ | `^[a-z0-9]+(?:-[a-z0-9]+)*$` (1–64 chars); **must equal the directory name** |
| `description` | ✅ | 1–1024 chars |
| `license` | no | free text |
| `compatibility` | no | max 500 chars |
| `metadata` | no | string → string map |
| `allowed-tools` | no | space-delimited list of pre-approved tool names |

Body size is capped by a warning threshold (`_MAX_BODY_CHARS = 50_000`); larger bodies
still load but log a context-window warning.

### 4.3 Progressive disclosure

Skills load in three disclosure levels (see `crewai/skills/models.py`):

| Level | Name | Loaded |
|---|---|---|
| 1 | `METADATA` | `name` + `description` only |
| 2 | `INSTRUCTIONS` | full `SKILL.md` body |
| 3 | `RESOURCES` | catalog `scripts/`, `references/`, `assets/` |

Path-based attachment auto-activates to `INSTRUCTIONS` (full body). We rely on level 2.

### 4.4 Attachment

A skill is attached to an agent or crew as a **path to a directory** (not the `.md`
file). The path points at a folder; `discover_skills` scans it one level deep and loads
every subdirectory that contains a `SKILL.md`:

```python
Agent(skills=[Path("data/planbot/shared/common_skills")])   # discovers every common skill
# or, crew-level (merged into every agent):
Crew(skills=[Path("data/planbot/shared/common_skills")])
```

- `discover_skills(path)` scans the folder for skill subdirectories (each with a
  `SKILL.md`) and loads their metadata.
- `activate_skill(skill)` promotes each to `INSTRUCTIONS` (full body).
- A folder containing **multiple** skill subdirectories therefore yields multiple skills
  from a single `skills:` entry.

### 4.5 Injection

At execution time, `append_skill_context` (in `crewai/agent/utils.py`) appends each
activated skill to the task prompt as:

```text
## Skill: product-recommendation
Rules for recommending an investment product to a client

<full SKILL.md body>
```

The appended section lands **after** the task description (post memory/knowledge
retrieval, in `Agent._finalize_task_prompt`), so the instruction appears in the
imperative task-prompt position.

---

## 5. Configuration Model

### 5.1 Skill directory layout

Common (cross-proposal) skills live as **subdirectories** under a single folder,
`data/planbot/shared/common_skills/`. CrewAI's `discover_skills` scans a folder one level
deep, treating each subdirectory that contains a `SKILL.md` as a skill:

```
data/planbot/shared/common_skills/
└── general-guideline/
    └── SKILL.md                 # migrated from shared/common/general_guideline.md (see §5.4)
```

Each subdirectory name **must** equal the `name` in its `SKILL.md` frontmatter. Adding a
new common skill later is just a new subdirectory — no agent config change.

Proposal-specific skills (such as `product-recommendation`, whose rules differ per
proposal) are **not** placed in `common_skills/`. They live in a per-proposal
`skills/` folder under the proposal's own data directory, one subdirectory per skill:

```
data/planbot/<proposal>/skills/<skill-name>/SKILL.md
```

For example `data/planbot/product_investor_matching/skills/product-recommendation/SKILL.md`.
Such skills are attached to individual agents ad hoc (see §5.2).

> The `product-recommendation` skill captures the recommendation rules currently duplicated
> across `tasks.yaml` `description:` blocks — the 1–5 buying score,
> one-recommendation-per-client, funding source, diversification caps, return/liquidity
> thresholds, and "Do not increase holding for any product other than the suggested
> product." Because these rules vary slightly per proposal, the skill is attached ad hoc
> (not via `common_skills/`) so each proposal can keep its own variant.

> Flat files (e.g. the old `general_guideline.md`) are ignored by `discover_skills`; only
> subdirectories containing `SKILL.md` are discovered.

### 5.2 Attaching skills via `agents.yaml`

Skills are agent-level, and agent config already lives in `agents.yaml` (the `tools:`
list is read by `_resolve_agent_tools`). An agent lists one or more skill **directories**
in a `skills:` list — either the common folder (auto-discovers every skill inside it) or a
proposal-specific skill directory:

```yaml
investment_advisor_agent:
  role: >
    Expert Financial Investment Advisor ...
  goal: >
    Output a complete, actionable investment proposal ...
  backstory: >
    Your advice is grounded in historical market data ...
  tools:
    - ProductSearchTool
  skills:
    - data/planbot/shared/common_skills                                          # all common skills
    - data/planbot/product_investor_matching/skills/product-recommendation   # ad hoc
  verbose: true
```

Semantics:

- `skills` is an optional list of **root-relative directory paths**; each path is scanned
  by `discover_skills`, which loads every skill subdirectory inside it.
- Paths are resolved against `app_config.root_dir` and passed to `Agent(skills=[...])`.
- Referencing the common folder yields **all** common skills, so the common `skills:` line
  stays stable as new common skills are added.
- Proposal-specific skills (e.g. `product-recommendation`) are listed ad hoc, per agent, in
  that proposal's own `agents.yaml`, pointing at
  `data/planbot/<proposal>/skills/<skill-name>`.

> Decision: skill paths are configured **agent-level** in `agents.yaml` (alongside
> `tools:`). No top-level `skills:` map in `config_planbot.yaml` is introduced.

Common skills are flat and shared with no per-proposal override. If a proposal ever needs
different rules, the agent simply **does not** reference `common_skills/` (and, if needed,
lists its own skill directory instead). The cost is that the agent becomes a special case;
this is accepted and reversible — re-attach `common_skills/` to return to the shared rules.

> Decision: ad hoc (proposal-specific) skills follow the location convention
> `data/planbot/<proposal>/skills/<skill-name>/SKILL.md`. Common skills use
> `data/planbot/shared/common_skills/<skill-name>/SKILL.md`.

### 5.3 Crew-level alternative (not currently wired)

CrewAI also supports `Crew(skills=[...])`, which merges the skills into every agent. This
is useful if a proposal later uses multiple agents that all need the same shared rules.
For now, per-agent `skills:` in `agents.yaml` is the primary mechanism, matching the
existing one-agent-per-proposal structure.

> Decision: CrewAI stays pinned at **1.14.4**. The Skill mechanism exists in this version,
> so no upgrade is required or coupled to this change.

### 5.4 Migrating `general_guidelines` from a reference input to a skill

The existing `general_guidelines` reference input is migrated to a skill:

1. Create `data/planbot/shared/common_skills/general-guideline/SKILL.md` with the content
   of `data/planbot/shared/common/general_guideline.md` (frontmatter
   `name: general-guideline` plus the guideline body).
2. Add `data/planbot/shared/common_skills` to the `skills:` list of every agent that
   currently receives `general_guidelines` (the folder reference auto-discovers all common
   skills, including `general-guideline`).
3. Remove the `general_guidelines` entry from `pipeline.*.inputs` in
   `config_planbot.yaml` for those proposals.
4. Remove the inert `Observe the guideline ../shared/common/general_guideline.md` line
   from `tasks.yaml` `description:`.

All other reference inputs (`proposal_instructions`, `section_guides`,
`financial_needs_guidelines`, and the data sections) remain in the reference JSON
unchanged.

---

## 6. Resolution, Injection, and Prompt Capture

### 6.1 Resolution and injection

1. Read the agent definition from `agents.yaml` (already done in
   `src/planbot/crew_workflow.py` via `agents_cfg`).
2. Resolve the `skills:` list to absolute paths (analogous to `_resolve_agent_tools`).
   Entries include the common folder `data/planbot/shared/common_skills` and, optionally,
   proposal-specific skill directories (e.g. `product-recommendation`).
3. Pass them to `Agent(skills=[...])`.
4. At kickoff, CrewAI `set_skills()` runs `discover_skills()` over each path (loading
   every skill subdirectory), activates each to `INSTRUCTIONS`, and
   `append_skill_context()` appends the bodies to the task prompt.

The skill content is injected **by CrewAI**, so the project code only needs to resolve and
forward the configured paths — no prompt rewriting.

### 6.2 Capturing the prompt sent to the LLM

Skill bodies are injected inside `kickoff()`, so they do **not** appear in the pre-run
`prompt_snapshot.md` (which is built before the agent runs). To keep the final prompt
auditable, capture the exact user-message prompt via CrewAI's event bus.

CrewAI emits `AgentExecutionStartedEvent` (from `crewai.events`) **after** skill injection.
Its `task_prompt` field carries the fully composed task prompt — description, expected
output, the reference JSON (already embedded in `description` by `_build_user_prompt`),
memory/knowledge, and the appended `## Skill:` sections:

```python
from crewai.events import crewai_event_bus, AgentExecutionStartedEvent

def _capture(source, event):
    write_text(
        run_root / "prompt_sent_to_llm.md",
        f"# Prompt sent to LLM\n\n{event.task_prompt}",
    )

crewai_event_bus.on(AgentExecutionStartedEvent)(_capture)
try:
    result = crew.kickoff()
    crewai_event_bus.flush()
finally:
    crewai_event_bus.off(AgentExecutionStartedEvent, _capture)
```

Notes:

- The handler is registered with `on(...)` and removed with `off(...)` in a `finally` so it
  lives only for this run and can close over `run_root`. Sync handlers run in a thread
  pool, so the handler must not rely on shared mutable state.
- `scoped_handlers()` is **not** used: it temporarily removes *all* CrewAI event handlers
  (telemetry, tracing, checkpoint listeners registered at import), which would silently
  disable observability during the run. Target only our handler instead.
- `event.task_prompt` is the **user-message** side only; the system prompt (agent
  role/goal/backstory + tool descriptions) is built later and is not in this event. For
  skill auditability, `task_prompt` is the relevant part.
- This yields a second artifact `prompt_sent_to_llm.md` alongside the existing
  `prompt_snapshot.md`: the former is the *actual* prompt (skills included), the latter
  remains a human-readable rendering of the reference sections.
- **Positioning**: because `_build_user_prompt` embeds the reference JSON into
  `description`, the skill sections land at the very end of the task prompt — after the
  reference JSON and `expected_output`. Shared instructions therefore move from their
  current near-top position (in the JSON) to the end. Note this when validating output
  quality on the small models; it is CrewAI's native placement and is not configurable.

---

## 7. Distinction from `pipeline.*.inputs`

| Aspect | Agent Skills (this spec) | `pipeline.*.inputs` (existing) |
|---|---|---|
| Purpose | Shared **instructions** | **Reference** material + data |
| Injection target | task prompt (appended by CrewAI) | JSON reference payload (labeled "not as instructions") |
| Storage | `SKILL.md` directory | markdown file glob(s) or `api://` resolver |
| Loader | CrewAI `discover_skills` / `activate_skill` | `load_references` |
| Failure on missing | CrewAI discovery warns/skips; `FileNotFoundError` on bad search path | governed by `input_policy.missing_data` |

They are complementary and do not overlap: a fragment that is a rule (do/don't) goes in a
skill; a fragment that is data or format goes in `inputs`. Concretely, `general_guidelines`
is a rule and is migrated to a skill (§5.4); all other current reference inputs stay in
`inputs`.

---

## 8. Acceptance Criteria

1. The common skill `data/planbot/shared/common_skills/general-guideline/SKILL.md` exists
   with valid frontmatter (`name` matching the directory, non-empty `description`) and an
   instruction body.
2. `agents.yaml` gains a `skills:` list on the relevant agents, pointing at the common
   folder `data/planbot/shared/common_skills`; paths are root-relative and externalized
   (no hardcoded paths in Python). Proposal-specific skills may also be listed ad hoc.
3. `crew_workflow.py` resolves `skills:` and passes them to `Agent(skills=[...])`.
4. Running a proposal that references the common folder injects the `## Skill:` sections
   for every skill in the folder (observable in the CrewAI trace / verbose output).
5. A proposal that does **not** list the skill is unchanged (skill injection is opt-in per
   agent).
6. `general_guidelines` is delivered via the `general-guideline` skill (§5.4): the
   `general_guidelines` reference input is removed from `config_planbot.yaml`, and the
   inert pointer line is removed from `tasks.yaml`. All other reference inputs are
   unchanged.
7. Unit tests: (a) normal flow — a configured skill path resolves and is forwarded to the
   agent; (b) exception flow — a missing/invalid skill directory or `SKILL.md` name
   mismatch raises/skips cleanly without crashing the run.
8. `prompt_sent_to_llm.md` is written on each run and contains the injected `## Skill:`
   section (i.e. the captured prompt includes the skill content).
9. End-to-end regression: `tests/test_proposal_API.py` passes after the change. This suite
   exercises the three proposal API endpoints
   (`/api/v1/reinvestment-proposals/propose_reinvestment_for_maturing_holdings`,
   `/api/v1/product-opportunity-proposal`, and
   `/api/v1/product-opportunity-proposal-automatch`); it is slow and is run whenever
   significant integration changes are made.

---

## 9. Out of Scope

- Custom templating or prompt-rewriting logic (CrewAI Skills replaces it).
- Skill injection into the JSON reference payload or `expected_output` (skills inject only
  into the task prompt).
- Resource directories (`scripts/`, `references/`, `assets/`) — level 3 disclosure is not
  needed.
- Crew-level `skills:` wiring unless a multi-agent proposal emerges.
- Auto-discovery of skills beyond what `discover_skills` already provides.
