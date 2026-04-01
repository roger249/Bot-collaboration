# Objective: Two-Bot Author-Reviewer Workflow

## Introduction

This workflow runs two cooperating AI bots to iteratively improve a specification:

1. Author bot drafts and revises the specification.
2. Reviewer bot checks quality, completeness, and implementation readiness.

The workflow is configuration-driven and reusable for different domains.

## Current Implementation Scope (Phase 1)

The implementation supports:

1. Config-driven model and prompt selection.
2. Iterative author-reviewer loop with round limits.
3. Structured outputs for author and reviewer.
4. Run artifacts stored under a timestamped run folder.
5. Transport-level request/response logging for diagnosis.

## Bot Roles

### Author Bot

Role: Senior Product Manager

Responsibilities:

1. Revise the current specification.
2. Address reviewer findings.
3. Provide change log and issue closure mapping.
4. Keep structure and terminology consistent.

### Reviewer Bot

Role: Composite reviewer (management, RM, operations perspectives)

Responsibilities:

1. Identify missing workflow steps, artifacts, data, and reporting gaps.
2. Provide actionable changes.
3. Validate issue closure quality.
4. Decide continue vs ready-for-finalization.

## Configuration

Source: [config/workflow.yaml](config/workflow.yaml)

Key parameters:

1. `workflow.spec_file`
2. `workflow.guideline_file`
3. `workflow.max_rounds`
4. `workflow.stop_on_no_blockers`
5. `bots.author` / `bots.reviewer` model and temperature
6. `providers.*.base_url` and `providers.*.timeout_seconds`

Prompt files:

1. [config/prompts/author_prompt.md](config/prompts/author_prompt.md)
2. [config/prompts/reviewer_prompt.md](config/prompts/reviewer_prompt.md)
3. [config/prompts/system_prompt.md](config/prompts/system_prompt.md)

## Prompt Placement Rules (Current)

As implemented in [src/workflow.py](src/workflow.py):

1. `author_prompt.md` and `reviewer_prompt.md` are sent as `system` messages.
2. The current specification and prior round context are sent as `user` messages.
3. Guideline content from `workflow.guideline_file` is appended to the `user` message under `Specification guideline:`.

## Iteration Process

Input seed:

1. Current spec file, for example `data/PB system spec.v1.md`.

Per round:

1. Author generates updated spec content.
2. System stores raw author output under `author/author_<next_spec_name>.md`.
3. System extracts `# Revised Specification` and writes extracted spec to `specs/<next_spec_name>.md`.
4. Reviewer evaluates extracted spec and produces findings.
5. System stores reviewer output under `comments/comment_<next_spec_name>.md`.
6. Progress summary is generated under `progress/progress_round_<n>.md`.

Stop conditions:

1. Reached `max_rounds`.
2. `stop_on_no_blockers=true` and reviewer has no critical/high blockers.
3. Prompt timeout (stopped reason: `prompt timeout`).

## Output Structure Per Run

Run root:

1. `runs/<workflow_name>_<timestamp>/`

Subfolders:

1. `author/`
2. `comments/`
3. `specs/`
4. `progress/`
5. `logs/`

Primary logs:

1. `logs/workflow.log`
2. `logs/chat_history.log` (transport request/response payloads)

## Logging and Diagnostics

Configured by [config/logging_config.ini](config/logging_config.ini):

1. Root logger for workflow events and exceptions.
2. `chat_history` logger hierarchy for dedicated transport tracing.
3. `chat_history.transport` entries include exact HTTP request body and raw response body.

## Error Handling (Current)

Implemented in [src/llm_client.py](src/llm_client.py) and [src/workflow.py](src/workflow.py):

1. Prompt timeout raises `PromptTimeoutError` and ends run with `stopped_reason: prompt timeout`.
2. HTTP/provider/network failures are logged with model and endpoint context.
3. Invalid JSON and unexpected response shape are logged and raised as errors.
4. Missing `# Revised Specification` section falls back to previous spec content with warning.

## Author Output Contract

Mandatory sections (from [config/prompts/author_prompt.md](config/prompts/author_prompt.md)):

1. `# Revised Specification`
2. `# Change Log`
3. `# Issue Closure Map`
4. `# Remaining Risks And Assumptions`

## Reviewer Output Contract

Mandatory sections (from [config/prompts/reviewer_prompt.md](config/prompts/reviewer_prompt.md)):

1. `# Findings`
2. `# Coverage Checklist`
3. `# Review Decision`
4. `# Progress Summary`

## Current Limitations and Next Improvements

1. Some models may emit reasoning-style preambles despite strict prompts.
2. Reviewer currently receives previous author output verbatim, which can propagate noisy content.
3. Consider adding:
   - Sanitization of reasoning preambles before reuse.
   - One-shot repair retry when required sections are missing.
   - Optional stricter schema validation for outputs.