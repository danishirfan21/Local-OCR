"""Conservative Urdu/Arabic-script text normalization.

Deliberately narrow in scope. OCR output for Arabic-derived scripts can
carry two kinds of noise that are safe to clean up mechanically:

1. Non-canonical Unicode forms (e.g. presentation-form ligature codepoints
   instead of their base letter sequence) -- fixed by NFC normalization.
2. Stray bidi control characters (LRM/RLM/embedding/override/pop-directional
   marks) that some OCR engines emit spuriously -- these are invisible but
   can corrupt copy-paste and downstream text processing, so they're
   stripped.

What this deliberately does NOT do: reorder characters, "fix" RTL/LTR
ordering, transliterate, or touch Arabic-indic vs. Western digit forms --
those are either already handled correctly upstream (see
reconstruction.py's geometry-based ordering) or are legitimate content
choices this layer has no business overriding.
"""

from __future__ import annotations

import unicodedata

# LRM, RLM, LRE, RLE, PDF, LRO, RLO, ALM, LRI, RLI, FSI, PDI
_BIDI_CONTROL_CHARS = "".join(
    chr(cp)
    for cp in (
        0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
        0x061C, 0x2066, 0x2067, 0x2068, 0x2069,
    )
)
_BIDI_STRIP_TABLE = str.maketrans("", "", _BIDI_CONTROL_CHARS)


def normalize_urdu_text(text: str) -> str:
    """Apply NFC normalization and strip stray bidi control characters."""
    normalized = unicodedata.normalize("NFC", text)
    return normalized.translate(_BIDI_STRIP_TABLE)
