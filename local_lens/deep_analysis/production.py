"""Production Deep Analyze configuration -- Gemini only, frozen model.

Deliberately separate from two other things that look similar but aren't:

1. `local_lens/deep_analysis/config.py`'s generic `LOCAL_LENS_DEEP_*` BYOK
   config -- that mechanism can point at any OpenAI-compatible/Anthropic/
   Paddle-vLLM endpoint and is kept as general-purpose internal
   extensibility (the `DeepAnalysisProvider` protocol isn't going away),
   but it is NOT what the production app/CLI use for their "Deep Analyze"
   feature as of V5. Only Gemini is exposed there.
2. `local_lens/deep_analysis/finalists.py`'s benchmark registry and its
   `LOCAL_LENS_BENCHMARK_GEMINI_API_KEY` -- that credential is for running
   `local-lens benchmark-deep`, a developer/CI-facing tool. Mixing it with
   production config would mean a benchmark credential silently enabling
   (or a production credential silently appearing configured for) the
   ordinary user-facing feature. They are read from different environment
   variables on purpose and never fall back to one another.

The production model is frozen to `PRODUCTION_GEMINI_MODEL`, exactly the
model measured in the Round 1 benchmark (docs/DEEP_PROVIDER_RESULTS.md:
12/12 successful, 12/12 valid structured output, 0 malformed, composite
score 0.9934) -- not "latest," not silently upgradable. Changing it is a
deliberate one-line edit here, ideally preceded by a new benchmark round,
never an automatic choice made by this code.
"""

from __future__ import annotations

import os

from local_lens.backends import BackendStatus
from local_lens.deep_analysis.gemini_provider import GeminiProvider

PRODUCTION_GEMINI_MODEL = "gemini-3.1-flash-lite"
_ENV_VAR = "LOCAL_LENS_GEMINI_API_KEY"
_PLACEHOLDER_VALUES = {"", "changeme", "change-me", "your-api-key", "your_api_key", "xxx", "placeholder", "todo"}


class GeminiDeepProvider(GeminiProvider):
    """The production Deep Analyze provider. A thin identity wrapper around
    `GeminiProvider` (the same HTTP adapter validated in the Round 1
    benchmark) with the model frozen to `PRODUCTION_GEMINI_MODEL` -- no
    behavioral difference from the benchmark adapter, just a distinct name
    and a model that can never be silently swapped by config."""

    name = "gemini_deep"

    def __init__(self, api_key: str | None, timeout: float = 60.0, max_retries: int = 1, **kwargs):
        super().__init__(api_key=api_key, model=PRODUCTION_GEMINI_MODEL, timeout=timeout, max_retries=max_retries, **kwargs)


def production_gemini_configured(env: dict | None = None) -> bool:
    """True only if LOCAL_LENS_GEMINI_API_KEY is set to something that
    isn't an obvious placeholder. Never returns or logs the value itself.
    `env` defaults to `os.environ` -- callers that want `.env` support
    (the app/CLI) resolve it once via `local_lens.env_file.load_env()` and
    pass the merged dict in explicitly, exactly like the benchmark CLI
    commands already do; this function itself never touches disk, which
    keeps it trivially testable and prevents any test from accidentally
    reading a real local `.env`."""
    env = env if env is not None else os.environ
    value = env.get(_ENV_VAR, "").strip()
    return value.lower() not in _PLACEHOLDER_VALUES


def production_gemini_status(env: dict | None = None) -> BackendStatus:
    configured = production_gemini_configured(env)
    reason = f"{PRODUCTION_GEMINI_MODEL} (BYOK)" if configured else f"not configured -- set {_ENV_VAR}"
    return BackendStatus(name="gemini_deep", available=configured, mode="remote", reason=reason)


def build_production_gemini_provider(env: dict | None = None) -> GeminiDeepProvider | None:
    """Construct the production provider, or None if unconfigured. Never
    makes a network call -- pure configuration."""
    env = env if env is not None else os.environ
    if not production_gemini_configured(env):
        return None
    api_key = env.get(_ENV_VAR, "").strip()
    return GeminiDeepProvider(api_key=api_key)
