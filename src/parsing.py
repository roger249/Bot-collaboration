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


def extract_revised_spec(markdown: str) -> str:
    start_pattern = re.compile(r"^#{1,6}\s+Revised Specification\s*$", re.MULTILINE)
    start_match = start_pattern.search(markdown)
    if not start_match:
        raise ValueError("Missing required section: Revised Specification")

    body_start = start_match.end()
    stop_pattern = re.compile(
        r"^#{1,6}\s+(Change Log|Issue Closure Map|Remaining Risks And Assumptions)\s*$",
        re.MULTILINE,
    )
    stop_match = stop_pattern.search(markdown, body_start)
    body_end = stop_match.start() if stop_match else len(markdown)
    return markdown[body_start:body_end].strip()