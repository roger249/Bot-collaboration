# Objective

We would like to migrate the infrastructure to use CrewAI, which have the following benefit in minds.

- Standardize agent creation
- Leverage tool to better organize passing information between agent.
- Easy to introduce new agents
- Able to leverage agent templates to have head start for agent of common roles
- Available of large pre-build tool

The migration is to use crewai infrastructure to achieve above benefit.  Anything not related to above benefit is non-goal.

Change to logging/config or other minor areas could be accepted as long as the major functionality is preserved and it provides better TCO or smaller code base.

Success means preserving current artifact and decision behavior while reducing orchestration complexity and enabling schema-validated inter-agent state updates.  No need for a exact match against the version before crewai.

# Plan
The migration is divided into two phase.

## Phase 1 
- Move plan_bot agent/orchestration layer to CrewAI
- Change without modify the done criteria could be accepted as long as it provides better TCO or smaller code base.
-- No need to maintain 100% compatible config.yaml.  
-- Similar exception and logging mechanism as now 
- no need rollback

- Exit criteria: Able to execute plan_bot without error and have output.md in the correct output format and no section is empty.

## Phase 2
Review exception mechanism, and refine it if needed.
- Exit criteria as Phase 1

## Phase 3
Author-reviewer migration - Crew wrapper with same loop semantics.  Any failure just need to log to error and stop.
- Exit criteria: Able to execute without error and have output.md in the correct output format and no section is empty.

## Phase 4: Author-reviewer migration - tool-based state store, and more elegant exception handling.

# Key changes
- Agent to be defined in yaml file
- Data passing between agent will mostly rely on two new tools - write/update spec, write/update comment.
- Consider using CrewAI Flows @persist() Decorator to implement this.

# New tools (for Phase 3 onwards)
Read tools: get_current_spec, get_latest_comments, get_open_issues.
Write tools: update_spec_section, append_review_finding, close_issue_with_evidence.

## spec_store tool
Purpose: single source of truth for the evolving specification.

Schema (v1):
- run_id: string
- spec_version: string (example: PB system spec.v2)
- spec_revision: integer (monotonic, increment on every write)
- updated_at_utc: string (ISO 8601)
- updated_by: string (author | orchestrator)
- sections: object
	- key: section_id (string)
	- value:
		- title: string
		- body_markdown: string
		- source_round: integer
- metadata: object
	- baseline_spec_file: string
	- guideline_file: string | null

Get/Set functions (v1):
- get_current_spec(run_id) -> full spec object
- get_spec_section(run_id, section_id) -> section object | null
- list_spec_sections(run_id) -> list[section_id]
- update_spec_section(run_id, expected_spec_revision, section_id, title, body_markdown, source_round, updated_by) -> updated section
- create_next_spec_version(run_id, expected_spec_revision, from_version, to_version, updated_by) -> spec header metadata

Write conflict handling (v1):
- All write APIs must include expected_spec_revision.
- If current spec_revision != expected_spec_revision, reject with ConflictError and do not write.
- Caller must re-read latest state and retry with merged content.

Agent visibility (v1):
- Author: read all, write only through update_spec_section
- Reviewer: read all, no write access
- Orchestrator/Flow: read all, version management (create_next_spec_version)
- Audit/Observer (optional future): read only

## issue_store tool
Purpose: structured reviewer findings and issue lifecycle tracking.

Schema (v1):
- run_id: string
- spec_version: string
- issue_store_revision: integer (monotonic, increment on every write)
- issues: list[issue]
	- issue:
		- issue_id: string (stable id, example: R2-WORKFLOW-003)
		- status: string enum (open | in_progress | closed)
		- severity: string enum (Critical | High | Medium | Low)
		- area: string
		- problem: string
		- impact: string
		- required_change: string
		- acceptance_criteria: string
		- created_round: integer
		- updated_round: integer
		- closed_round: integer | null
		- close_evidence: string | null
		- owner: string (author | reviewer | orchestrator)

Get/Set functions (v1):
- get_latest_comments(run_id) -> reviewer comment markdown
- get_open_issues(run_id, min_severity=None) -> list[issue]
- get_issue_by_id(run_id, issue_id) -> issue | null
- append_review_finding(run_id, expected_issue_store_revision, spec_version, issue_payload, created_by) -> issue_id
- mark_issue_in_progress(run_id, expected_issue_store_revision, issue_id, updated_round, owner) -> updated issue
- close_issue_with_evidence(run_id, expected_issue_store_revision, issue_id, close_evidence, closed_round, closed_by) -> updated issue

Write conflict handling (v1):
- All write APIs must include expected_issue_store_revision.
- If current issue_store_revision != expected_issue_store_revision, reject with ConflictError and do not write.
- Caller must re-read latest state and retry.

Agent visibility (v1):
- Reviewer: read all, create findings via append_review_finding, can close issues with evidence after validation
- Author: read all, can set in_progress only (cannot close)
- Orchestrator/Flow: read all, can close issues with evidence after validation
- Validation rule: close requires non-empty close_evidence and matching spec_version context

