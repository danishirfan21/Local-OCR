"""Canonical language codes and per-engine translation.

Different OCR engines represent language selections differently (EasyOCR
uses ISO 639-1-ish codes like "en"/"ur"; PaddleOCR uses its own model-family
codes, e.g. "en"/"ur" but is not guaranteed to line up with EasyOCR for every
language). The UI should only ever deal with the canonical codes/names
below; engines translate at the boundary.
"""

from __future__ import annotations

# canonical_code -> (display name, {engine_name: engine_specific_code})
#
# Verified against the actually-installed paddleocr==3.7.0 during V3 (see
# the implementation report): PaddleOCR(lang="urdu") raises "No models are
# available for lang='urdu'" -- the real code is "ur", identical to
# EasyOCR's. An earlier, unverified V2 assumption had this wrong.
_LANGUAGES: dict[str, tuple[str, dict[str, str]]] = {
    "en": ("English", {"easyocr": "en", "paddleocr": "en"}),
    "ur": ("Urdu", {"easyocr": "ur", "paddleocr": "ur"}),
}

DEFAULT_LANGUAGE = "en"


def available_languages() -> list[tuple[str, str]]:
    """Return [(canonical_code, display_name), ...] for UI selection."""
    return [(code, name) for code, (name, _) in _LANGUAGES.items()]


def to_engine_code(canonical_code: str, engine_name: str) -> str:
    """Translate a canonical language code to the code a given engine expects.

    Falls back to the canonical code itself if the engine has no explicit
    mapping, since most engines do use plain ISO-ish codes.
    """
    entry = _LANGUAGES.get(canonical_code)
    if entry is None:
        return canonical_code
    _, engine_codes = entry
    return engine_codes.get(engine_name, canonical_code)


def display_name(canonical_code: str) -> str:
    entry = _LANGUAGES.get(canonical_code)
    return entry[0] if entry else canonical_code
