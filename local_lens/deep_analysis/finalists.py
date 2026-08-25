"""The canonical Deep Analyze bake-off finalist registry.

Each `FinalistConfig` fixes provider/model/endpoint/pricing in one place so
`--dry-run`, `--preflight`, and a real `--run` all agree on exactly what
would be called -- there is no separate "maybe I'll use a different model"
path. Model names and endpoints come from the research in
docs/DEEP_PROVIDER_EVALUATION.md; none have been confirmed by an actual
live API call (that would itself be a network request), so if a provider
renames/retires a model between the research pass and execution, the
credential-and-availability preflight will surface that as a request
failure, not silently substitute a different model.

Credentials are read from dedicated `LOCAL_LENS_BENCHMARK_*` environment
variables -- deliberately NOT the single `LOCAL_LENS_DEEP_*` variables used
by the app's one-configured-provider Deep Analyze mode, and deliberately
NOT bare `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`-style names other tools on
this machine might already have set. A benchmark that runs against 4+
providers at once needs 4+ credentials simultaneously, which the app's
single-provider config was never designed for; reusing ambient env vars
that happen to share a name with something else on the machine would risk
silently picking up a credential nobody meant to use for this.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from local_lens.deep_analysis.benchmark import TokenPricing

# Deliberately not a "real" secret value -- these are the strings treated
# as "configured in name only," e.g. from a copy-pasted .env.example that
# was never actually filled in. Conservative and short on purpose: better
# to occasionally ask the user to confirm a genuinely unusual key than to
# silently treat an obvious placeholder as configured.
_PLACEHOLDER_VALUES = {"", "changeme", "change-me", "your-api-key", "your_api_key", "xxx", "placeholder", "todo"}


@dataclass(frozen=True)
class FinalistConfig:
    label: str
    provider_kind: str  # "openai-compatible" | "anthropic" | "gemini" | "paddle-vllm"
    model: str
    base_url: str | None  # None only for paddle-vllm (no endpoint provisioned yet)
    credential_env_var: str | None  # None for candidates that don't need one to be *listed* (still excluded from execution)
    pricing: TokenPricing
    role: str
    executable_in_first_run: bool = True


# Rough per-request token budget for THIS benchmark's images (small,
# synthetic, mostly short text): ~1,000 input tokens (image + prompt),
# ~500 output tokens (structured JSON reply). A deliberately conservative
# upper bound, not a real usage measurement -- see benchmark.py's
# `estimate_request_cost` docstring. Once real requests report actual
# usage (see gemini/anthropic/openai_compatible providers' `usage` in
# result metadata), the runner uses that instead for the recorded cost.
ESTIMATED_INPUT_TOKENS_PER_REQUEST = 1000
ESTIMATED_OUTPUT_TOKENS_PER_REQUEST = 500

FINALISTS: list[FinalistConfig] = [
    FinalistConfig(
        label="OpenAI GPT-5",
        provider_kind="openai-compatible",
        model="gpt-5",
        base_url="https://api.openai.com/v1",
        credential_env_var="LOCAL_LENS_BENCHMARK_OPENAI_API_KEY",
        pricing=TokenPricing(1.25, 10.00, "developers.openai.com/api/docs/pricing, Aug 2026"),
        role="strong proprietary general VLM -- generic OpenAI-compatible adapter, no new code",
    ),
    FinalistConfig(
        label="Gemini 2.5 Flash-Lite",
        provider_kind="gemini",
        model="gemini-2.5-flash-lite",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        credential_env_var="LOCAL_LENS_BENCHMARK_GEMINI_API_KEY",
        pricing=TokenPricing(0.10, 0.40, "ai.google.dev/gemini-api/docs/pricing, Aug 2026"),
        role="cheapest proprietary option -- native adapter (gemini_provider.py), not the OpenAI-compat beta layer",
    ),
    FinalistConfig(
        label="PaddleOCR-VL-1.6 (remote vLLM)",
        provider_kind="paddle-vllm",
        model="PaddleOCR-VL-1.6",
        base_url=None,
        credential_env_var=None,
        pricing=TokenPricing(0.0, 0.0, "GPU-second billing, not token billing -- no endpoint provisioned"),
        role="excluded from the first paid bake-off: no GPU endpoint has been provisioned, and provisioning one "
        "requires separate approval. Prior local measurements (docs/V4_DIRECTION.md) remain valid reference "
        "evidence; this row exists so the comparison isn't silently missing PaddleOCR-VL, just marked unexecutable.",
        executable_in_first_run=False,
    ),
    FinalistConfig(
        label="Qwen2.5-VL-72B-Instruct (Fireworks AI)",
        provider_kind="openai-compatible",
        model="accounts/fireworks/models/qwen2p5-vl-72b-instruct",
        base_url="https://api.fireworks.ai/inference/v1",
        credential_env_var="LOCAL_LENS_BENCHMARK_FIREWORKS_API_KEY",
        pricing=TokenPricing(0.9, 0.9, "docs.fireworks.ai/serverless/pricing, Aug 2026, approximate"),
        role="strongest hosted open VLM with a named OCR/document-VLM catalog -- generic adapter, no new code",
    ),
    FinalistConfig(
        label="Claude Sonnet 5",
        provider_kind="anthropic",
        model="claude-sonnet-5",
        base_url="https://api.anthropic.com/v1",
        credential_env_var="LOCAL_LENS_BENCHMARK_ANTHROPIC_API_KEY",
        pricing=TokenPricing(3.00, 15.00, "platform.claude.com pricing, Aug 2026"),
        role="tests whether Anthropic's explicit anti-hallucination/low-confidence vision guidance translates into "
        "a measurably lower extra_content_rate -- the one finalist needing a dedicated adapter",
    ),
]

# Backward-compat alias for the pre-existing dry-run code path.
PROPOSED_FINALISTS = FINALISTS


def credential_configured(finalist: FinalistConfig, env: dict | None = None) -> bool:
    """True only if the finalist's dedicated env var is set to something
    that isn't an obvious placeholder. Never returns or logs the value
    itself -- callers must only ever report this boolean."""
    if finalist.credential_env_var is None:
        return False
    env = env if env is not None else os.environ
    value = env.get(finalist.credential_env_var, "").strip()
    return value.lower() not in _PLACEHOLDER_VALUES


def build_provider_for_finalist(finalist: FinalistConfig, env: dict | None = None):
    """Construct the DeepAnalysisProvider for one finalist. Never makes a
    network call -- pure configuration, same guarantee as
    local_lens.deep_analysis.config.build_deep_provider."""
    env = env if env is not None else os.environ
    api_key = env.get(finalist.credential_env_var, "").strip() if finalist.credential_env_var else None

    if finalist.provider_kind == "gemini":
        from local_lens.deep_analysis.gemini_provider import GeminiProvider

        return GeminiProvider(api_key=api_key, base_url=finalist.base_url, model=finalist.model)

    if finalist.provider_kind == "anthropic":
        from local_lens.deep_analysis.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=api_key, base_url=finalist.base_url, model=finalist.model)

    if finalist.provider_kind == "openai-compatible":
        from local_lens.deep_analysis.openai_compatible_provider import OpenAICompatibleVisionProvider

        return OpenAICompatibleVisionProvider(base_url=finalist.base_url, api_key=api_key, model=finalist.model)

    raise ValueError(f"'{finalist.provider_kind}' has no executable provider (paddle-vllm has no endpoint yet)")
