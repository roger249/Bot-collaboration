# Rearrange Skill Before the JSON Reference

Date: 2026-09-03
Status: Proposed (not yet implemented)

## Problem

CrewAI's Agent Skills (`## Skill:` sections) are appended **after** the JSON
reference payload, not before it. We want the ordering:

1. task description
2. `## Skill:` blocks (rules/guidelines)
3. reference JSON

## Root cause

CrewAI hardcodes the injection as an append at the end of the task prompt:

- `crewai/agent/utils.py` → `append_skill_context()` does
  `task_prompt += "\n\n" + ...` (always appends).
- `crewai/agent/core.py` → `_finalize_task_prompt()` calls
  `append_skill_context()` after `task.prompt()`.

Because our reference JSON is embedded in `Task.description` (built by
`_build_user_prompt` in `src/planbot/workflow.py`), and skill context is always
appended, the `## Skill:` blocks necessarily land after the JSON. There is no
CrewAI config knob to change this order.

## Proposed restructure

Stop relying on CrewAI's `Agent(skills=...)` append; instead inline the skill
text into `description` ourselves, placed between the task text and the
reference JSON. Reuse CrewAI's own loader for correct formatting.

### Desired prompt order
1. task description
2. `## Skill:` sections
3. reference JSON

### Edits (3, all in our code)

1. `src/planbot/crew_workflow.py` — add a helper that resolves + formats skills
   into a string, reusing CrewAI's loader:

   ```python
   from crewai.skills.loader import discover_skills, activate_skill, format_skill_context

   def _build_skill_context(agent_def, root_dir) -> str:
       paths = _resolve_agent_skills(agent_def, root_dir)
       blocks = []
       for p in paths:
           for skill in discover_skills(p):
               blocks.append(format_skill_context(activate_skill(skill)))
       return "\n\n".join(blocks)
   ```

2. `src/planbot/workflow.py` — extend `_build_user_prompt` to insert skill
   context before the reference JSON:

   ```python
   def _build_user_prompt(task_prompt, reference_payload_json, skill_context=""):
       parts = [task_prompt.strip(), ""]
       if skill_context.strip():
           parts += [skill_context.strip(), ""]
       parts += [
           "The following reference sections are provided as JSON. ...",
           "",
           reference_payload_json,
       ]
       return "\n".join(parts)
   ```

3. `src/planbot/crew_workflow.py` — in `run_crew_planbot`, load the agent
   config (same logic already used in `_generate_with_crew`), build the skill
   text, pass it into `_build_user_prompt`; then tell `_generate_with_crew` to
   **not** attach `skills=` to the Agent (otherwise the same skills are injected
   twice).

## Trade-offs

| | CrewAI native `skills=` (current) | Inline into `description` (proposed) |
|---|---|---|
| Ordering | fixed (last) | fully controlled |
| Skill metadata enforcement (`allowed-tools`, `license`) | CrewAI applies | bypassed (only body text injected) |
| `prompt_sent_to_llm.md` | skill at end | skill in correct position |
| Code ownership | zero | ~15 lines we maintain |

We give up only `allowed-tools` gating, which is unused (our skills have no tool
restrictions).

## Rejected alternative

Keep `Agent(skills=...)` but move the reference JSON into the system prompt
(`role`/`goal`/`backstory`). This makes references precede the task
instructions, which is worse, and bloats the system prompt.

## Related

- Skill discovery / path bug: see
  `docs/specification/proposal/Migrate_to_shared_skills.md` (§4.4, §5.2) and the
  fix to `data/planbot/*/crewai/agents.yaml` (point `skills:` at the **parent**
  folder, not the `<skill-name>` dir).
- Skill content sources:
  - `data/planbot/shared/common_skills/general-guideline/SKILL.md`
  - `data/planbot/shared/skills/product-suggestion/SKILL.md`
