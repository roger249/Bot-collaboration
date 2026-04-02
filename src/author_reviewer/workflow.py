from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.shared.config_loader import AppConfig
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
from src.shared.llm_client import LLMRequest, PromptTimeoutError, build_client
from src.shared.logging_utils import configure_logging
from src.author_reviewer.parsing import extract_revised_spec, summarize_review
from src.author_reviewer.progress import build_progress_markdown


LOGGER = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    run_root: Path
    log_path: Path
    final_spec_path: Path
    total_rounds: int
    stopped_reason: str


def _load_prompt(path: Path) -> str:
    return read_text(path)


def _compose_system_prompt(base_prompt: str) -> str:
    return base_prompt


def _append_guideline(parts: list[str], guideline_text: str | None) -> None:
    if not guideline_text or not guideline_text.strip():
        return
    parts.extend([
        "",
        "Specification guideline:",
        guideline_text.strip(),
    ])


def _build_reviewer_input(
    spec: str,
    previous_review: str | None,
    previous_author: str | None,
    guideline_text: str | None,
) -> str:
    parts = [
        "Current specification:",
        spec,
    ]
    _append_guideline(parts, guideline_text)
    if previous_review:
        parts.extend(["", "Previous reviewer output:", previous_review])
    if previous_author:
        parts.extend(["", "Previous author output:", previous_author])
    return "\n".join(parts)


def _build_author_input(
    spec: str,
    review: str | None,
    previous_author: str | None,
    guideline_text: str | None,
) -> str:
    parts = [
        "Current specification:",
        spec,
    ]
    _append_guideline(parts, guideline_text)
    if review:
        parts.extend(["", "Latest reviewer comments:", review])
    if previous_author:
        parts.extend(["", "Previous author output:", previous_author])
    return "\n".join(parts)


def run_workflow(app_config: AppConfig) -> WorkflowResult:
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

    author_client = build_client(app_config, "author", app_config.author)
    reviewer_client = build_client(app_config, "reviewer", app_config.reviewer)

    previous_review: str | None = None
    previous_author: str | None = None
    last_spec_path = original_spec_output
    stopped_reason = "maximum rounds reached"
    rounds_completed = 0

    for round_number in range(1, app_config.workflow.max_rounds + 1):
        LOGGER.info("Starting round %s", round_number)
        rounds_completed = round_number

        author_request = LLMRequest(
            system_prompt=author_prompt,
            user_prompt=_build_author_input(
                spec=current_spec_text,
                review=previous_review,
                previous_author=previous_author,
                guideline_text=guideline_text,
            ),
            model=app_config.author.model,
            temperature=app_config.author.temperature,
        )

        try:
            author_output = author_client.generate(author_request)
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

        reviewer_request = LLMRequest(
            system_prompt=reviewer_prompt,
            user_prompt=_build_reviewer_input(
                spec=revised_spec,
                previous_review=previous_review,
                previous_author=author_output,
                guideline_text=guideline_text,
            ),
            model=app_config.reviewer.model,
            temperature=app_config.reviewer.temperature,
        )

        try:
            reviewer_output = reviewer_client.generate(reviewer_request)
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