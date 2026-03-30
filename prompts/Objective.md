# Objective: Two-Bot Author-Reviewer Workflow for Software Spec

# Introduction

I'd like to draft a program for two bots that has author-reviewer relationship。

The program or mechansim shall be more generic that it accepts prompt for the task of author-reviewer.  This could be an idea for algorithmic trading, or a full specification for a financial system.

We will use it to draft a specificaiton for a private banking system as an initial test of the author-reviewer idea.

The approach of this author-reviewer workflow will use a agile approach.  First, we put up a workable system in the phase 1 before fine tune anything further.

# Ideas

TWO COOPERATING AI BOTS with one as author and another as reviewer/suggion.

### Author BOT
Role: Senior Private Banking Product Manager

Responsibilities:
1. Draft complete feature specification.
2. Revise spec based on Reviewer findings.
3. Provide change log and closure mapping for each review issue.
4. Keep structure, terminology, and traceability consistent.

### Reviewer BOT

Role: Composite reviewer representing:
1. Private Banking senior managers
2. Relationship Managers
3. Operations users

Responsibilities:
1. Identify gaps, ambiguity, workflow inefficiency, missing features, and missing reports.
2. Provide specific and actionable changes, not generic comments.
3. Validate that each issue is fully closed in later rounds.
4. Confirm readiness against a formal Definition of Done.

## Configuration
1. All prompt shall be put in configuration
2. Configuration like model choices, max iter number shall also put in configuration file
3. Trace output shall use python logutil

## 3. Required Spec Coverage
The specification is divided into two phases.

The first phase include all sections below:

1. Business goals and scope
2. User roles and permissions (last phase)
3. End-to-end workflows by persona.  Identify the required artefact from these workflows - which most of this artefact shall be automate as much as possible to output from the system with the proper feature.
4. Core features and detailed behavior
5. Feature outputs and user-visible outcomes
6. Data model essentials (key entities, critical fields, ownership)
7. Regulatory and management reports:
   - report name
   - owner
   - audience/regulator
8. Open questions, assumptions, and out-of-scope items

## 4. Iteration Process

Current spec file: data/PB system spec.v1.md

Loop:

1. Reviewer reviews current spec (data/PB system spec.v1.md) and returns:
   - Findings list with severity and issue IDs
   - Required Changes list
   - The list outputed as md file is have filename "comment_<spec name>.md"
   
2. Author revises spec and returns:
   - Updated spec
   - Issue closure notes mapped by issue ID
   - Explicit list of unresolved or deferred items.  
   - Output of the spec filename will be same as before except increasing the version number by 1.   PB system spec.v1.md -> PB system spec.v2.md
3. Reviewer re-checks only after closure mapping is provided.
4. Repeat until Definition of Done is met or round limit is reached.

Round control:
1. Maximum rounds: 3 (default), and this is a parameter in the configuration
2. Escalation rule: unresolved Critical issues after round 2 require human review.

## 5. Reviewer Output Format (Mandatory)

### A. Findings
For each issue include:
1. Issue ID (example: R2-COMP-003)
2. Severity: Critical / High / Medium / Low
3. Area: Workflow / Reporting / Data / UX
4. Problem description
5. Risk or impact
6. Required change (specific)
7. Acceptance criteria (testable)

### B. Coverage Checklist
Pass/Fail with short rationale for:
1. Role coverage
2. Workflow completeness, in particular if those artefacts are identified.
3. Reporting completeness.  
4. Is all artefact identified that subject to automation has spec in.  This is required to reduce the time the involved party (RM, and others) for medicore tasks so that RM can spend more time in other areas.
5. Traceability and auditability

### C. Review Decision
1. Continue (with blocking issues), or
2. Ready for finalization (no Critical/High issues)

## 6. Author Output Format (Mandatory)

1. Revised specification content
2. Change log by section
3. Issue closure map:
   - Issue ID
   - Resolution status: Resolved / Partially Resolved / Deferred
   - Evidence of fix (section reference)
4. Remaining risks and assumptions

## 7. Definition of Done
The loop ends only when all conditions are true:

1. No Critical issues remain
2. No High issues remain
3. Required reports are complete and traceable to workflows
4. Reviewer confirms specification is implementation-ready

## 8. Model Selection Guidance

For phase 1 testing, we will choose model that are free for the moment.  

1. Author Bot: cost-efficient drafting model
2. Reviewer Bot: stronger reasoning model for strict review and compliance challenge
3. Optional final pass: strongest model for final QA before sign-off

# Phase 2 to-do

Please ignore anything below until we build up the author-review loop to a satisfactory level

Phase 2 spec may cover below.  Let's put this aside for the moment.

- Compliance and controls:
   - AML
   - KYC
   - MiFID II
   - GDPR
- Non-functional requirements:
   - security and access control
   - audit trail and traceability
   - reliability and resilience
   - performance expectations
   - backup and recovery

- Compliance and risk stakeholders


Multi-model optimization
MCP integration
report-generation logic beyond draft text