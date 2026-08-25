"""Secret redaction for anything the benchmark runner writes to disk.

Every result artifact and raw-response record goes through this module
before being serialized. It never trusts a caller to have already
stripped secrets -- it actively strips known-sensitive keys/patterns
itself, so a forgotten field somewhere doesn't leak a credential into
`benchmarks_remote/results/`.
"""

from __future__ import annotations

import re

_REDACTED = "***REDACTED***"

# Header names (case-insensitive) that must never appear with their real
# value in a stored artifact.
_SENSITIVE_HEADER_NAMES = {"authorization", "x-api-key", "x-goog-api-key", "api-key"}

# Query-param names that commonly carry a credential (e.g. a hypothetical
# `?key=...`-style Gemini call, even though this codebase's own Gemini
# adapter deliberately avoids that pattern -- this guards third-party/
# future code paths too).
_SENSITIVE_QUERY_PARAM_PATTERN = re.compile(r"([?&](?:key|api_key|apikey|token|access_token)=)[^&\s]+", re.IGNORECASE)


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redact known-sensitive header values. Never mutates the input."""
    return {
        k: (_REDACTED if k.lower() in _SENSITIVE_HEADER_NAMES else v)
        for k, v in headers.items()
    }


def sanitize_url(url: str) -> str:
    """Strip any credential-shaped query parameter from a URL before it's
    stored or printed."""
    return _SENSITIVE_QUERY_PARAM_PATTERN.sub(lambda m: m.group(1) + _REDACTED, url)


def sanitize_error_message(message: str) -> str:
    """Best-effort scrub of a free-text error message: redact anything
    shaped like a bearer token or API key that might have been echoed back
    by a provider's error body."""
    message = _SENSITIVE_QUERY_PARAM_PATTERN.sub(lambda m: m.group(1) + _REDACTED, message)
    message = re.sub(r"Bearer\s+[A-Za-z0-9\-_.]{8,}", f"Bearer {_REDACTED}", message)
    return message


def sanitize_result_record(record: dict) -> dict:
    """Sanitize a single per-request result dict before it's written to
    `benchmarks_remote/results/`. Explicitly drops (not just redacts) any
    key that should never have been put there in the first place -- an
    allowlist-adjacent belt-and-suspenders check on top of the individual
    provider adapters never including these fields to begin with."""
    forbidden_keys = {"api_key", "authorization", "headers", "env", "credential", "raw_headers"}
    sanitized = {k: v for k, v in record.items() if k.lower() not in forbidden_keys}

    if isinstance(sanitized.get("error"), str):
        sanitized["error"] = sanitize_error_message(sanitized["error"])

    return sanitized
