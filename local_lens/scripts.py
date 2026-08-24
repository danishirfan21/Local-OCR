"""Unicode script detection and best-effort language inference.

Deliberately simple: Unicode codepoint block membership, no ICU/fontconfig
dependency. This can distinguish *scripts* reliably (a character either is
or isn't in the Arabic block) but cannot distinguish *languages* that share
a script -- Urdu, Arabic, and Persian all use Arabic-derived script, so
script detection alone cannot tell them apart. `infer_languages` is
explicit about that limitation rather than pretending otherwise.
"""

from __future__ import annotations

SCRIPT_LATIN = "latin"
SCRIPT_ARABIC = "arabic"

_LATIN_RANGES = ((0x0041, 0x024F), (0x1E00, 0x1EFF))
# Covers Arabic, Arabic Supplement, and Arabic Presentation Forms -- the
# ranges Urdu text actually uses (Urdu adds a handful of extra letters
# within these blocks, e.g. retroflex consonants, rather than a separate
# Unicode block of its own).
_ARABIC_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def _in_ranges(codepoint: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(lo <= codepoint <= hi for lo, hi in ranges)


def detect_scripts(text: str) -> list[str]:
    """Return the scripts present in `text`, in first-seen order.

    Whitespace, digits, and punctuation are script-neutral and ignored.
    Returns an empty list for text with no recognized-script letters at all
    (e.g. pure digits/punctuation) -- that's a legitimate outcome, not an
    error.
    """
    found: list[str] = []
    for ch in text:
        cp = ord(ch)
        if _in_ranges(cp, _LATIN_RANGES):
            script = SCRIPT_LATIN
        elif _in_ranges(cp, _ARABIC_RANGES):
            script = SCRIPT_ARABIC
        else:
            continue
        if script not in found:
            found.append(script)
    return found


_SCRIPT_TO_CANDIDATE_LANGUAGES = {
    SCRIPT_LATIN: ["en"],
    SCRIPT_ARABIC: ["ur"],
}


def infer_languages(scripts: list[str], configured_langs: list[str]) -> list[str]:
    """Best-effort language guess from detected scripts + what the user selected.

    This is intentionally conservative: it only returns a language if (a) its
    script was actually detected in the text AND (b) the user had that
    language selected/available. Script detection alone cannot disambiguate
    Urdu from Arabic/Persian, so we never claim a language purely from
    script -- the user's own language selection resolves the ambiguity.
    """
    inferred: list[str] = []
    for script in scripts:
        for candidate in _SCRIPT_TO_CANDIDATE_LANGUAGES.get(script, []):
            if candidate in configured_langs and candidate not in inferred:
                inferred.append(candidate)
    return inferred
