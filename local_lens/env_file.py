"""Minimal, dependency-free `.env` loader.

Deliberately not `python-dotenv`: it isn't currently installed, and a
correct minimal parser is ~20 lines -- not enough win to add a new
dependency for, matching this project's established preference for
stdlib over small SDKs (see local_lens/deep_analysis/http_client.py's own
"stdlib over requests/httpx" reasoning).

Precedence is fixed and tested: a real process/OS environment variable
always wins over a `.env` value -- `.env` only fills in whatever isn't
already set. Nothing in this module ever prints, logs, or returns a value
through any channel other than the merged dict itself; callers (see
local_lens/deep_analysis/finalists.py's `credential_configured()`) are
responsible for never surfacing what they read from it.
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env(dotenv_path: str | Path = ".env", env: dict | None = None) -> dict:
    """Returns a new dict: `env` (default `os.environ`) with `.env` values
    filled in only where a key isn't already present. Never mutates
    `os.environ` or the passed-in `env` -- callers thread the result
    through explicitly (e.g. as the `env=` argument to
    `run_preflight`/`execute_benchmark`), which keeps this side-effect-free
    and trivially testable with a fake dict instead of real files/env."""
    base = dict(env if env is not None else os.environ)
    for key, value in _parse_env_file(Path(dotenv_path)).items():
        base.setdefault(key, value)
    return base
