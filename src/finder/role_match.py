"""
Role matching for the Cold Email Pipeline finder waterfall.

Identifies the highest-priority technical leader from a text block
given a list of candidate names.  The search is **name-first**:
for each name, extract ~100 chars of surrounding context and check
for role keywords in priority order.

Conforms to:
 - active_context.md  (ROLE_PRIORITY list, name-first search)
 - contracts.md 3.6   (email_source / email_confidence enums)
 - build_plan.md Module 4
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Highest-priority first.  Order matters — first match wins.
ROLE_PRIORITY: list[str] = [
    "CTO",
    "Chief Technolog",        # matches Chief Technology Officer / Chief Technologist
    "VP Eng",                 # matches VP Engineering / VP Eng
    "Head of Eng",            # matches Head of Engineering
    "Director of Eng",
    "Engineering Manager",
    "Founding Engineer",
    "Technical Co-founder",
    "Co-founder",
    "Founder",
    "Staff Engineer",
    "Senior Engineer",
    "Software Engineer",
    "Product Engineer",
    "Platform Engineer",
    "Full Stack Engineer",
    "Tech Lead",
    "Technical Recruiter",
    "Talent Acquisition",
    "Talent Partner",
    "People Ops",
    "Recruiter",
    "Hiring Manager",
]

_WINDOW = 50  # chars each side; ~100 chars total around a name mention
_ROLE_RANK = {role: idx for idx, role in enumerate(ROLE_PRIORITY)}


def find_technical_lead(
    text: str, names: list[str]
) -> Optional[tuple[str, str]]:
    """Return *(name, title)* for the best technical-role match, or *None*.

    **Algorithm (name-first):**
    For each *name* in *names*:
      1. Find every occurrence of the name in *text* (case-insensitive).
      2. For each occurrence, extract a window of *_WINDOW* chars on
         each side.
      3. Walk *ROLE_PRIORITY* top-down.  The first keyword found in
         that window wins → return (name, matched_role).

    Chooses the globally highest-priority role across all name matches.
    If two matches have the same role priority, the earlier text
    occurrence wins.
    """
    if not text or not names:
        return None

    text_lower = text.lower()
    best_match: Optional[tuple[int, int, str, str]] = None
    # (priority_idx, text_idx, name, role)

    for name in names:
        if not name:
            continue
        # Find all start positions of this name (case-insensitive)
        name_lower = name.lower()
        start = 0
        while True:
            idx = text_lower.find(name_lower, start)
            if idx == -1:
                break
            # Extract surrounding window
            # Keep context local to this name mention (~100 chars total).
            win_start = max(0, idx - _WINDOW)
            win_end = min(len(text), idx + len(name) + _WINDOW)
            window = text[win_start:win_end]

            # Check role keywords in priority order
            matched_priority: Optional[int] = None
            matched_role: Optional[str] = None
            for role in ROLE_PRIORITY:
                if role.lower() in window.lower():
                    matched_priority = _ROLE_RANK[role]
                    matched_role = role
                    break

            if matched_priority is not None and matched_role is not None:
                candidate = (matched_priority, idx, name, matched_role)
                if best_match is None or candidate[:2] < best_match[:2]:
                    best_match = candidate

            start = idx + 1  # advance past this occurrence

    if best_match is None:
        return None

    _, _, best_name, best_role = best_match
    logger.info("Role match: name=%r  role=%r", best_name, best_role)
    return (best_name, best_role)
