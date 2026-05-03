# Introduction to PlanBot

The idea is to let a selected AI engine compose a proposal for a specific decision-making prompt. This should be a general framework, with prompts and parameters externalized in YAML and prompt files.

This is completely separated from the existing author-reviewer workflow.

# Workflow

Workflow is as follows:

- AI will consider information from Markdown files in various folders, plus external website URLs. Support for PDF, Word, and Excel is expected in the next sprint.
- For URLs, pass them directly to the model. For models that cannot retrieve web content, include a prompt instruction requiring the model to explicitly indicate that external web sources were not consulted.
- Markdown files are stored under `data/planbot/reference/*.md` by default, and this can be overridden in shared YAML config: `config/config.yaml`.
- An external prompt defines how to perform the task and the required output.
- Prompts will vary by task and include task-specific output templates.
- A boilerplate output structure with required sections is provided to guide content.
- Local/bot interaction is logged at transport level as `DEBUG`; this can be turned off in `config/logging_config.ini`. This may have security implications in production, but that is deferred for now.
- Generation is one-off, meaning the bot is invoked once only. No review loop is required.
- Final output defaults to `runs/planbot/<run>/output.md`, and can be overridden in shared YAML config.
- The default folder for external prompts is `config/prompts/planbot`.
- A shared prompt folder is `config/prompts/shared` for common prompts used by both author-reviewer and planbot.
- This should be implemented under a new Python module `planbot`. Any shared logic should be placed under `src/shared/`.

This workflow can be used for tasks ranging from news summaries and travel planning to company buyout decisions.

# Initial test

## Input

The initial test is an investment advice proposal with inputs:
- Client profile
- Existing holding
- Universe to new/alternative asset under consideration

## Output

Output is as follows:

- Pros and cons of current holding
- Suggestion of portfolio change, if any
- Pros and cons of the new portfolio
- Scenario analysis of the new portfolio

# Outstandings

- How should PDF and Excel files be sent for model interpretation?
- Which prebuilt models can accept these files via an OpenAI-compatible API?

