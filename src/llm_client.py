from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib import request as urllib_request

from src.config_loader import AppConfig, BotConfig


@dataclass
class LLMRequest:
    system_prompt: str
    user_prompt: str
    model: str
    temperature: float


class BaseLLMClient:
    def generate(self, request: LLMRequest) -> str:
        raise NotImplementedError


class MockLLMClient(BaseLLMClient):
    def __init__(self, bot_name: str) -> None:
        self.bot_name = bot_name

    def generate(self, request: LLMRequest) -> str:
        if self.bot_name == "reviewer":
            return """# Findings
- issue_id: R1-WORKFLOW-001
  severity: High
  area: Workflow
  problem: The spec does not clearly map each selling stage to its primary user output and expected report artifact.
  impact: Reviewers cannot verify completeness of the operational workflow or whether RM effort is truly reduced.
  required_change: Add a workflow-to-artifact mapping for each selling stage and identify the main system-generated output.
  acceptance_criteria: Each selling stage lists actors, trigger, output artifact, and related feature.

# Coverage Checklist
- item: Role coverage
  status: Pass
  rationale: RM and operations concerns are visible, though user roles are not fully formalized yet.
- item: Workflow completeness
  status: Fail
  rationale: Main stages exist but transitions, triggers, and outputs are incomplete.
- item: Reporting completeness
  status: Fail
  rationale: Several reports are listed, but ownership and usage context are inconsistent.
- item: Artifact automation coverage
  status: Fail
  rationale: Candidate artifacts are implied but not systematically identified.
- item: Traceability and auditability
  status: Pass
  rationale: The spec has section structure and version-based drafting intent.

# Review Decision
decision: Continue
summary: The draft is directionally strong but still missing workflow-output mapping and consistent report structure.

# Progress Summary
- round_goal: Establish draft structure and identify major gaps.
- issue_counts: Critical=0, High=1, Medium=0, Low=0
- completed_areas: High-level business objective and core feature areas are documented.
- remaining_risks: Workflow-output ambiguity, missing report ownership, weak artifact mapping.
- next_round_objective: Make workflow outputs explicit and connect reports to selling stages.
"""

        return """# Revised Specification
The specification has been revised to clarify workflow outputs, report ownership, and draft-level artifact identification.

# Change Log
- section: Selling cycle and product features
  change: Added clearer mapping between stages and expected outputs.
- section: Reports
  change: Clarified intended use of RM-facing and client-facing reports.

# Issue Closure Map
- issue_id: R1-WORKFLOW-001
  status: Partially Resolved
  evidence: Workflow stages now reference outputs, but artifact tables remain draft-level.

# Remaining Risks And Assumptions
- Phase 1 keeps artifact automation at draft level rather than full operational design.
- User roles will remain lightweight until later refinement.
"""


class OpenAICompatibleClient(BaseLLMClient):
    def __init__(self, base_url: str, api_key: str, timeout_seconds: int) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def generate(self, request: LLMRequest) -> str:
        payload = json.dumps(
            {
                "model": request.model,
                "temperature": request.temperature,
                "messages": [
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
            }
        ).encode("utf-8")
        http_request = urllib_request.Request(
            self.base_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib_request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = ""
            if exc.fp is not None:
                body = exc.fp.read().decode("utf-8", errors="replace")[:1000]
            raise ValueError(f"Provider HTTP error {exc.code}: {exc.reason}. {body}") from exc
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Unexpected LLM response: {json.dumps(data)[:1000]}") from exc


def _resolve_api_key(api_key_env_or_value: str) -> str:
    # Accept either an environment variable name or a direct key value.
    # For production use, prefer environment variables.
    env_value = os.getenv(api_key_env_or_value)
    if env_value:
        return env_value
    if api_key_env_or_value.startswith("sk-"):
        return api_key_env_or_value
    raise ValueError(
        f"Environment variable {api_key_env_or_value} is not set for configured provider."
    )


def _resolve_base_url(provider_name: str, base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    # DeepSeek and most OpenAI-compatible APIs expect this route.
    if provider_name in {"openai_compatible", "deepseek", "poe"}:
        return f"{normalized}/chat/completions"
    return normalized


def build_client(app_config: AppConfig, bot_name: str, bot_config: BotConfig) -> BaseLLMClient:
    if bot_config.provider == "mock":
        return MockLLMClient(bot_name=bot_name)

    provider = app_config.providers.get(bot_config.provider)
    if provider is not None:
        api_key = _resolve_api_key(provider.api_key_env)
        return OpenAICompatibleClient(
            base_url=_resolve_base_url(bot_config.provider, provider.base_url),
            api_key=api_key,
            timeout_seconds=provider.timeout_seconds,
        )

    raise ValueError(f"Unsupported provider: {bot_config.provider}")