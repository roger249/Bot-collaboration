from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from json import JSONDecodeError
from urllib.error import HTTPError
from urllib.error import URLError
from urllib import request as urllib_request

from src.config_loader import AppConfig, BotConfig


LOGGER = logging.getLogger(__name__)
CHAT_HISTORY_TRANSPORT_LOGGER = logging.getLogger("chat_history.transport")


@dataclass
class LLMRequest:
    system_prompt: str
    user_prompt: str
    model: str
    temperature: float


class BaseLLMClient:
    def generate(self, request: LLMRequest) -> str:
        raise NotImplementedError


class PromptTimeoutError(TimeoutError):
    pass


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
        payload_text = json.dumps(
            {
                "model": request.model,
                "temperature": request.temperature,
                "messages": [
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
            }
        )
        CHAT_HISTORY_TRANSPORT_LOGGER.info(
            "transport request\n=== url ===\n%s\n=== body ===\n%s",
            self.base_url,
            payload_text,
        )
        payload = payload_text.encode("utf-8")
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
                response_text = response.read().decode("utf-8")
                CHAT_HISTORY_TRANSPORT_LOGGER.info(
                    "transport response\n=== status ===\n%s\n=== body ===\n%s",
                    getattr(response, "status", "unknown"),
                    response_text,
                )
                data = json.loads(response_text)
        except (TimeoutError, socket.timeout) as exc:
            LOGGER.error(
                "Prompt timed out for model '%s' after %s seconds against %s",
                request.model,
                self.timeout_seconds,
                self.base_url,
            )
            raise PromptTimeoutError(
                f"Prompt timed out for model '{request.model}' after {self.timeout_seconds} seconds."
            ) from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError | socket.timeout):
                LOGGER.error(
                    "Prompt timed out for model '%s' after %s seconds against %s",
                    request.model,
                    self.timeout_seconds,
                    self.base_url,
                )
                raise PromptTimeoutError(
                    f"Prompt timed out for model '{request.model}' after {self.timeout_seconds} seconds."
                ) from exc
            LOGGER.error(
                "Provider connection error for model '%s' against %s: %s",
                request.model,
                self.base_url,
                exc.reason,
            )
            raise ValueError(f"Provider connection error for model '{request.model}': {exc.reason}") from exc
        except HTTPError as exc:
            body = ""
            if exc.fp is not None:
                body = exc.fp.read().decode("utf-8", errors="replace")[:1000]
            CHAT_HISTORY_TRANSPORT_LOGGER.info(
                "transport response\n=== status ===\n%s\n=== body ===\n%s",
                exc.code,
                body,
            )
            LOGGER.error(
                "Provider HTTP error for model '%s' against %s: %s %s %s",
                request.model,
                self.base_url,
                exc.code,
                exc.reason,
                body,
            )
            raise ValueError(f"Provider HTTP error {exc.code}: {exc.reason}. {body}") from exc
        except JSONDecodeError as exc:
            LOGGER.error(
                "Provider returned invalid JSON for model '%s' against %s: %s",
                request.model,
                self.base_url,
                exc,
            )
            raise ValueError(f"Provider returned invalid JSON for model '{request.model}'.") from exc
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            LOGGER.error(
                "Unexpected LLM response shape for model '%s': %s",
                request.model,
                json.dumps(data)[:1000],
            )
            raise ValueError(f"Unexpected LLM response: {json.dumps(data)[:1000]}") from exc

        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(str(part.get("text", "")))
            content = "\n".join(text_parts)

        if not isinstance(content, str) or not content.strip():
            LOGGER.error(
                "Provider returned empty content for model '%s': %s",
                request.model,
                json.dumps(data)[:1000],
            )
            raise ValueError(
                f"Provider returned empty content for model '{request.model}'. "
                f"Response snippet: {json.dumps(data)[:1000]}"
            )

        return content


def _resolve_api_key(api_key_env_or_value: str) -> str:
    # Accept either an environment variable name or a direct key value.
    # For production use, prefer environment variables.
    env_value = os.getenv(api_key_env_or_value)
    if env_value:
        return env_value
    if api_key_env_or_value.startswith("sk-"):
        LOGGER.warning("Using direct API key value from config. Prefer environment variables instead.")
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

    LOGGER.error("Unsupported provider configured for bot '%s': %s", bot_name, bot_config.provider)
    raise ValueError(f"Unsupported provider: {bot_config.provider}")