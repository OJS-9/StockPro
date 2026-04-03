"""
Lightweight report structure checks (Phase 1.7 roadmap — quality signal).

When the model emits Markdown headings, we expect core sections so users see
Summary / Risk / Recommendation-style coverage. No headings → skip (plain text).
"""

from __future__ import annotations

import re
from typing import List, Tuple

# Heading text (## ...) should mention these substrings (case-insensitive match on title).
_REQUIRED_IN_HEADINGS = (
    "summary",
    "risk",
    "recommendation",
)


def _markdown_heading_bodies(text: str) -> List[str]:
    bodies: List[str] = []
    for line in (text or "").splitlines():
        m = re.match(r"^#{1,3}\s+(.+)$", line.strip())
        if m:
            bodies.append(m.group(1).strip().lower())
    return bodies


def assess_report_structure(report_text: str) -> Tuple[bool, List[str]]:
    """
    Return (passed, missing_topic_ids).

    Uses Markdown #-### titles only. If there are no such headings, returns
    (True, []) — nothing to validate (legacy or non-Markdown output).
    """
    bodies = _markdown_heading_bodies(report_text)
    if not bodies:
        return True, []

    missing: List[str] = []
    for topic in _REQUIRED_IN_HEADINGS:
        if not any(topic in h for h in bodies):
            missing.append(topic)
    return len(missing) == 0, missing
