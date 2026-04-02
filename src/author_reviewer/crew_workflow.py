from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from crewai import Agent, Crew, LLM, Process, Task

from src.author_reviewer.file_ops import (
    RunPaths,
    author_filename,
    comment_filename,
    create_run_paths,
    next_version_filename,
    progress_filename,
    read_text,
    write_text,
)
from src.author_reviewer.parsing import extract_revised_spec, summarize_review
from src.author_reviewer.progress import build_progress_markdown
from src.author_reviewer.workflow import (
    _build_author_input,
    _build_reviewer_input,
    _compose_system_prompt,
    _load_prompt,
)
from src.shared.config_loader import AppConfig, BotConfig
from src.shared.llm_client import LLMRequest, PromptTimeoutError, _resolve_api_key, build_client
from src.shared.logging_utils import configure_logging


LOGGER = logging.getLogger(__name__)
_CREWAI_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "crewai" / "author_reviewer"


@dataclass
class WorkflowResult:
    run_root: Path
    log_path: Path
    final_spec_path: Path
    total_rounds: int
    stopped_reason: str


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _provider_model_name(provider_name: str, model: str) -> str:
    if provider_name == "deepseek":
        return f"deepseek/{model}"
    # openai_compatible and poe are OpenAI-compatible HTTP APIs in current config.
    return f"openai/{model}"


def _build_crew_llm(app_config: AppConfig, provider_name: str, model: str, temperature: float) -> LLM:
    provider = app_config.providers.get(provider_name)
    if provider is None:
        raise ValueError(f"Unknown provider '{provider_name}' in providers config.")

    api_key = _resolve_api_key(provider.api_key_env)
    return LLM(
        model=_provider_model_name(provider_name, model),
        base_url=provider.base_url.rstrip("/"),
        api_key=api_key,
        temperature=temperature,
        timeout=provider.timeout_seconds,
    )


def _generate_via_crew(
    app_config: AppConfig,
    role_name: str,
    provider_name: str,
    model: str,
    temperature: float,
    system_prompt: str,
    user_prompt: str,
) -> str:
    agents_cfg = _load_yaml(_CREWAI_CONFIG_DIR / "agents.yaml")
    tasks_cfg = _load_yaml(_CREWAI_CONFIG_DIR / "tasks.yaml")

    if role_name == "author":
        agent_cfg = agents_cfg["author_agent"]
        task_cfg = tasks_cfg["author_task"]
    else:
        agent_cfg = agents_cfg["reviewer_agent"]
        task_cfg = tasks_cfg["reviewer_task"]

    llm = _build_crew_llm(app_config, provider_name, model, temperature)

    backstory = agent_cfg["backstory"].strip()
    if system_prompt:
        backstory = f"{system_prompt.strip()}\n\n{backstory}"

    agent = Agent(
        role=agent_cfg["role"],
        goal=agent_cfg["goal"],
        backstory=backstory,
        llm=llm,
        allow_delegation=False,
        verbose=False,
    )

    task = Task(
        description=user_prompt,
        expected_output=task_cfg["expected_output"],
        agent=agent,
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )

    LOGGER.info("Sending %s request via CrewAI (model=%s, provider=%s)", role_name, model, provider_name)
    result = crew.kickoff()
    return str(result.raw) if hasattr(result, "raw") else str(result)


def _generate_role_output(
    app_config: AppConfig,
    role_name: str,
    bot_config: BotConfig,
    system_prompt: str,
    user_prompt: str,
) -> str:
    if bot_config.provider == "mock":
        client = build_client(app_config, role_name, bot_config)
        request = LLMRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=bot_config.model,
            temperature=bot_config.temperature,
        )
        return client.generate(request)

    return _generate_via_crew(
        app_config=app_config,
        role_name=role_name,
        provider_name=bot_config.provider,
        model=bot_config.model,
        temperature=bot_config.temperature,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


def run_crew_workflow(app_config: AppConfig) -> WorkflowResult:
    run_paths: RunPaths = create_run_paths(
        app_config.workflow.output_root,
        app_config.workflow.name,
        app_config.workflow.overwrite_output_folder,
    )
    log_path = run_paths.logs_dir / "workflow.log"
    chat_history_log_path = run_paths.logs_dir / "chat_history.log"
    configure_logging(
        app_config.logging_level,
        log_path,
        chat_history_log_path,
        app_config.logging_config_file,
        chat_history_enabled=app_config.logging_chat_history_enabled,
        chat_history_max_bytes=app_config.logging_chat_history_max_bytes,
        chat_history_backup_count=app_config.logging_chat_history_backup_count,
    )

    current_spec_name = app_config.workflow.spec_file.name
    current_spec_text = read_text(app_config.workflow.spec_file)

    original_spec_output = run_paths.specs_dir / current_spec_name
    write_text(original_spec_output, current_spec_text)

    guideline_text: str | None = None
    if app_config.workflow.guideline_file is not None:
        guideline_text = read_text(app_config.workflow.guideline_file)

    author_prompt = _compose_system_prompt(_load_prompt(app_config.author.prompt_file))
    reviewer_prompt = _compose_system_prompt(_load_prompt(app_config.reviewer.prompt_file))

    previous_review: str | None = None
    previous_author: str | None = None
    last_spec_path = original_spec_output
    stopped_reason = "maximum rounds reached"
    rounds_completed = 0

    for round_number in range(1, app_config.workflow.max_rounds + 1):
        LOGGER.info("Starting round %s", round_number)
        rounds_completed = round_number

        author_user_prompt = _build_author_input(
            spec=current_spec_text,
            review=previous_review,
            previous_author=previous_author,
            guideline_text=guideline_text,
        )

        try:
            author_output = _generate_role_output(
                app_config=app_config,
                role_name="author",
                bot_config=app_config.author,
                system_prompt=author_prompt,
                user_prompt=author_user_prompt,
            )
        except PromptTimeoutError:
            stopped_reason = "prompt timeout"
            LOGGER.error("Author prompt timed out in round %s", round_number)
            return WorkflowResult(
                run_root=run_paths.root,
                log_path=log_path,
                final_spec_path=last_spec_path,
                total_rounds=rounds_completed,
                stopped_reason=stopped_reason,
            )
        except Exception:
            LOGGER.exception("Author generation failed in round %s", round_number)
            raise

        next_spec_name = next_version_filename(current_spec_name)
        author_path = run_paths.author_dir / author_filename(next_spec_name)
        write_text(author_path, author_output)

        try:
            revised_spec = extract_revised_spec(author_output)
            if not revised_spec.strip():
                LOGGER.warning(
                    "Author output had an empty Revised Specification section for %s; reusing prior spec content.",
                    current_spec_name,
                )
                revised_spec = current_spec_text
        except ValueError:
            LOGGER.warning(
                "Author output missed Revised Specification section for %s; reusing prior spec content.",
                current_spec_name,
            )
            revised_spec = current_spec_text

        next_spec_path = run_paths.specs_dir / next_spec_name
        write_text(next_spec_path, revised_spec)

        reviewer_user_prompt = _build_reviewer_input(
            spec=revised_spec,
            previous_review=previous_review,
            previous_author=author_output,
            guideline_text=guideline_text,
        )

        try:
            reviewer_output = _generate_role_output(
                app_config=app_config,
                role_name="reviewer",
                bot_config=app_config.reviewer,
                system_prompt=reviewer_prompt,
                user_prompt=reviewer_user_prompt,
            )
        except PromptTimeoutError:
            stopped_reason = "prompt timeout"
            LOGGER.error("Reviewer prompt timed out in round %s", round_number)
            return WorkflowResult(
                run_root=run_paths.root,
                log_path=log_path,
                final_spec_path=last_spec_path,
                total_rounds=rounds_completed,
                stopped_reason=stopped_reason,
            )
        except Exception:
            LOGGER.exception("Reviewer generation failed in round %s", round_number)
            raise

        review_path = run_paths.comments_dir / comment_filename(next_spec_name)
        write_text(review_path, reviewer_output)

        progress_path = run_paths.progress_dir / progress_filename(round_number)
        write_text(progress_path, build_progress_markdown(round_number, reviewer_output, next_spec_name))

        review_summary = summarize_review(reviewer_output)
        if app_config.workflow.stop_on_no_blockers and not review_summary.has_blockers:
            stopped_reason = "no critical/high issues remain"
            LOGGER.info("Stopping after reviewer round %s because no blockers remain", round_number)
            previous_review = reviewer_output
            previous_author = author_output
            current_spec_name = next_spec_name
            current_spec_text = revised_spec
            last_spec_path = next_spec_path
            break

        previous_review = reviewer_output
        previous_author = author_output
        current_spec_name = next_spec_name
        current_spec_text = revised_spec
        last_spec_path = next_spec_path

    return WorkflowResult(
        run_root=run_paths.root,
        log_path=log_path,
        final_spec_path=last_spec_path,
        total_rounds=rounds_completed,
        stopped_reason=stopped_reason,
    )
