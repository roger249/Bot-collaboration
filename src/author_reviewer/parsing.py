from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ReviewSummary:
    has_blockers: bool
    critical_count: int
    high_count: int
    decision: str


def count_severity(markdown: str, severity: str) -> int:
    pattern = re.compile(rf"severity:\s*{re.escape(severity)}\b", re.IGNORECASE)
    return len(pattern.findall(markdown))


def extract_decision(markdown: str) -> str:
    match = re.search(r"decision:\s*(.+)", markdown, re.IGNORECASE)
    if not match:
        return "Continue"
    return match.group(1).strip()


def summarize_review(markdown: str) -> ReviewSummary:
    critical_count = count_severity(markdown, "Critical")
    high_count = count_severity(markdown, "High")
    decision = extract_decision(markdown)
    has_blockers = critical_count > 0 or high_count > 0
    return ReviewSummary(
        has_blockers=has_blockers,
        critical_count=critical_count,
        high_count=high_count,
        decision=decision,
    )


def extract_section(markdown: str, heading: str) -> str:
    pattern = re.compile(
        rf"^#{{1,6}}\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^#{{1,6}}\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(markdown)
    if not match:
        raise ValueError(f"Missing required section: {heading}")
    return match.group(1).strip()


def _strip_leading_reasoning(text: str) -> str:
    """Remove common model reasoning blocks that can leak into final sections."""
    cleaned = text.lstrip()

    # Remove XML-like thinking tags if present at the beginning.
    cleaned = re.sub(
        r"^<think>[\s\S]*?</think>\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove fenced reasoning blocks (```thinking ... ``` / ```reasoning ... ```).
    cleaned = re.sub(
        r"^```(?:thinking|reasoning|analysis)?\s*[\s\S]*?```\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove markdown-style "Thinking..." preambles and quoted reasoning lines at the top.
    lines = cleaned.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue

        lower_line = line.lower()
        is_reasoning_line = (
            lower_line.startswith("*thinking")
            or lower_line.startswith("thinking")
            or lower_line.startswith("> thinking")
            or lower_line.startswith("analysis:")
            or lower_line.startswith("reasoning:")
            or line.startswith(">")
        )
        if is_reasoning_line:
            index += 1
            continue
        break

    return "\n".join(lines[index:]).lstrip()


def extract_revised_spec(markdown: str) -> str:
    # Case-insensitive search for "Revised Specification" heading
    start_pattern = re.compile(
        r"^#{1,6}\s+Revised\s+Specification\s*$",
        re.MULTILINE | re.IGNORECASE
    )
    start_match = start_pattern.search(markdown)
    if not start_match:
        raise ValueError("Missing required section: Revised Specification")

    body_start = start_match.end()
    # Look for any of the stopping headings (case-insensitive)
    stop_pattern = re.compile(
        r"^#{1,6}\s+(Change\s+Log|Issue\s+Closure\s+Map|Remaining\s+Risks\s+And\s+Assumptions)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    stop_match = stop_pattern.search(markdown, body_start)
    body_end = stop_match.start() if stop_match else len(markdown)
    section = markdown[body_start:body_end].strip()
    return _strip_leading_reasoning(section).strip()