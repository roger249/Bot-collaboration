from __future__ import annotations

from src.author_reviewer.parsing import summarize_review


def build_progress_markdown(round_number: int, review_markdown: str, current_spec_name: str) -> str:
    summary = summarize_review(review_markdown)
    return f"""# Round Progress Summary

- round_number: {round_number}
- spec_version: {current_spec_name}
- critical_issues: {summary.critical_count}
- high_issues: {summary.high_count}
- blocking_issues_present: {'yes' if summary.has_blockers else 'no'}
- reviewer_decision: {summary.decision}
"""