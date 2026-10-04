"""Pattern syntax helpers shared by rule validation and categorization."""

import re


def pattern_to_regex(pattern: str) -> re.Pattern:
    """Compile one user-facing literal or regular-expression pattern."""
    raw_mode = False
    case_sensitive = False

    if pattern.startswith("re:"):
        raw_mode = True
        pattern = pattern[3:]

    if pattern.startswith("case:"):
        case_sensitive = True
        pattern = pattern[5:]

    if pattern.startswith("re:case:"):
        raw_mode = True
        case_sensitive = True
        pattern = pattern[8:]

    flags = 0 if case_sensitive else re.IGNORECASE
    if not raw_mode:
        pattern = re.escape(pattern)

    return re.compile(pattern, flags)
