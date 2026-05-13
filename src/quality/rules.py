"""
Rule-based fast pre-filter for lyrics quality.
Runs before the expensive LLM quality reviewer.
Each check returns a (passed, reason) tuple.
"""

from __future__ import annotations

import re

# ── Thresholds ────────────────────────────────────────────────────────
MIN_LINES = 8
MAX_LINES = 60
MIN_LINE_LENGTH = 4
MAX_REPEATED_WORD_RATIO = 0.35  # If one word is >35% of all words → reject

# Common AI filler phrases (Turkish)
_FILLER_PATTERNS = [
    r"\böyle bir\b",
    r"\bbu güzel\b",
    r"\bçok güzel\b",
    r"\bgerçekten\b",
    r"\bharika\b",
    r"\bmuhteşem\b",
]

# Required structural markers
_STRUCTURE_MARKERS = ["[verse", "[chorus", "[nakarat", "[kıta"]


def check_min_lines(lyrics: str) -> tuple[bool, str]:
    lines = [l.strip() for l in lyrics.splitlines() if l.strip() and not l.strip().startswith("[")]
    if len(lines) < MIN_LINES:
        return False, f"Too few lyric lines: {len(lines)} (min {MIN_LINES})"
    return True, ""


def check_max_lines(lyrics: str) -> tuple[bool, str]:
    lines = [l.strip() for l in lyrics.splitlines() if l.strip() and not l.strip().startswith("[")]
    if len(lines) > MAX_LINES:
        return False, f"Too many lyric lines: {len(lines)} (max {MAX_LINES})"
    return True, ""


def check_line_lengths(lyrics: str) -> tuple[bool, str]:
    short_lines = []
    for line in lyrics.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("[") and len(stripped) < MIN_LINE_LENGTH:
            short_lines.append(stripped)
    if short_lines:
        return False, f"Lines too short: {short_lines[:3]}"
    return True, ""


def check_repeated_words(lyrics: str) -> tuple[bool, str]:
    words = re.findall(r"\b\w+\b", lyrics.lower())
    if not words:
        return False, "No words found in lyrics"
    from collections import Counter
    counts = Counter(words)
    most_common_word, most_common_count = counts.most_common(1)[0]
    # Exclude common function words
    _STOP = {"ve", "bir", "bu", "o", "da", "de", "ki", "mi", "mu", "la", "le", "ben", "sen"}
    if most_common_word not in _STOP and (most_common_count / len(words)) > MAX_REPEATED_WORD_RATIO:
        return False, f"Word '{most_common_word}' repeated too much: {most_common_count}/{len(words)}"
    return True, ""


def check_no_filler_phrases(lyrics: str) -> tuple[bool, str]:
    for pattern in _FILLER_PATTERNS:
        if re.search(pattern, lyrics, re.IGNORECASE):
            return False, f"AI filler phrase detected: '{pattern}'"
    return True, ""


def check_has_structure(lyrics: str) -> tuple[bool, str]:
    lower = lyrics.lower()
    for marker in _STRUCTURE_MARKERS:
        if marker in lower:
            return True, ""
    return False, "No structural markers ([Verse]/[Chorus]) found in lyrics"


def run_all_checks(lyrics: str) -> tuple[bool, list[str]]:
    """
    Run all rule checks. Returns (passed: bool, failed_reasons: list[str]).
    All checks must pass for the result to be True.
    """
    checks = [
        check_min_lines,
        check_max_lines,
        check_line_lengths,
        check_repeated_words,
        check_no_filler_phrases,
        check_has_structure,
    ]
    issues = []
    for check in checks:
        passed, reason = check(lyrics)
        if not passed:
            issues.append(reason)
    return len(issues) == 0, issues
