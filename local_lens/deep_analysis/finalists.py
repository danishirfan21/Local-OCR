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

## Free-first strategy (docs/DEEP_PROVIDER_EVALUATION.md "Free-first
strategy" section has the full research)

Every finalist now carries a `round` ("free" | "paid") and a
`cost_classification`:

- `"zero_cost_eligible"` -- verified: the provider's free tier requires no
  payment method on file, and there is no documented mechanism for usage
  to silently become billable (Gemini goes further: billing requires
  manually linking an account and prepaying a minimum; Groq requires no
  payment method for the free tier and simply rate-limits with HTTP 429
  once exceeded, with no auto-upgrade language found in its docs).
- `"likely_free"` -- probably free but with a real caveat (not used by any
  current finalist; reserved for a future candidate where the "never
  charged" guarantee is weaker than Groq's/Gemini's).
- `"paid"` -- normal per-token billing from the first request.
- `"unknown"` -- not used; a finalist with unverified billing behavior does
  not belong in the registry at all until that's resolved.

Round "free" finalists' nominal `pricing` (their real published per-token
rate, in case someone ever runs them on a paid-tier account) is recorded
for transparency but is deliberately NOT what gates `--max-cost-usd` when
`--free-tier-only` is set -- see runner.py's `execute_benchmark`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from local_lens.deep_analysis.benchmark import TokenPricing

# Deliberately not a "real" secret value -- these are the strings treated
# as "configured in name only," e.g. from a copy-pasted .env.example that
# was never actually filled in. Conservative and short on purpose: better
# to occasionally ask the user to confirm a genuinely unusual key than to
# silently treat an obvious placeholder as configured.
_PLACEHOLDER_VALUES = {"", "changeme", "change-me", "your-api-key", "your_api_key", "xxx", "placeholder", "todo"}


@dataclass(frozen=True)
class FreeTierLimits:
    """Documented free-tier rate limits for one finalist's model.
    `source` distinguishes an official static doc page from a third-party
    aggregator estimate (used for Gemini, whose own rate-limit page no
    longer publishes static numbers) -- never presented as equally
    authoritative."""

    rpm: int | None
    rpd: int | None
    tpm: int | None
    tpd: int | None
    source: str
    official: bool  # False if figures are third-party-reported, not from the provider's own static docs


@dataclass(frozen=True)
class FinalistConfig:
    label: str
    provider_kind: str  # "openai-compatible" | "anthropic" | "gemini" | "paddle-vllm"
    model: str
    base_url: str | None  # None only for paddle-vllm (no endpoint provisioned yet)
    credential_env_var: str | None  # None for candidates that don't need one to be *listed* (still excluded from execution)
    pricing: TokenPricing
    role: str
    round: str = "paid"  # "free" | "paid"
    cost_classification: str = "paid"  # "zero_cost_eligible" | "likely_free" | "paid" | "unknown"
    payment_method_required: bool | None = None  # None = unknown/not verified
    billing_spillover_possible: bool | None = None  # None = unknown/not verified
    free_tier_limits: FreeTierLimits | None = None
    privacy_note: str = ""
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
    # --- Round 1: free -----------------------------------------------------
    FinalistConfig(
        label="Groq Qwen3.6-27B",
        provider_kind="openai-compatible",
        model="qwen/qwen3.6-27b",
        base_url="https://api.groq.com/openai/v1",
        credential_env_var="LOCAL_LENS_BENCHMARK_GROQ_API_KEY",
        pricing=TokenPricing(0.0, 0.0, "Groq free tier -- no per-token charge without an explicit account upgrade"),
        role="Hypothesis (not yet confirmed by benchmark data): Groq-hosted Qwen vision may be particularly "
        "attractive for Local Lens because it combines vision/OCR, JSON mode, multilingual support, and very "
        "high hosted inference speed with a developer-friendly free tier and an exact-match OpenAI-compatible "
        "API -- generic adapter, no new code. Model confirmed via console.groq.com/docs/model/qwen/qwen3.6-27b "
        "(status: Preview) to support image input, OCR, document/chart understanding, multilingual input, and "
        "JSON Object Mode.",
        round="free",
        cost_classification="zero_cost_eligible",
        payment_method_required=False,
        billing_spillover_possible=False,
        free_tier_limits=FreeTierLimits(
            rpm=30, rpd=1000, tpm=8000, tpd=200_000,
            source="console.groq.com/docs/rate-limits, Aug 2026", official=True,
        ),
        privacy_note="Groq does not retain customer data for inference requests by default (30-day retention "
        "applies only to batch/fine-tuning or abuse-investigation logging). Groq's Services Agreement states "
        "it is not permitted to use inputs/outputs for training without explicit permission. No payment method "
        "is required for the free tier; upgrading to a billed tier is a separate, explicit account action -- no "
        "auto-upgrade language was found in Groq's billing docs, though an explicit 'exceeding the free tier "
        "never charges you' guarantee is also not stated verbatim (inferred from the absence of any auto-"
        "billing mechanism and free tier requiring no payment method).",
    ),
    FinalistConfig(
        label="Gemini 3.1 Flash-Lite",
        provider_kind="gemini",
        model="gemini-3.1-flash-lite",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        credential_env_var="LOCAL_LENS_BENCHMARK_GEMINI_API_KEY",
        pricing=TokenPricing(0.0, 0.0, "Gemini free Developer API tier -- billing requires a separate, explicit account action"),
        role="Current-generation free-tier vision candidate (gemini-2.5-flash-lite, the original pick, is "
        "scheduled to retire no earlier than 2026-10-16 -- gemini-3.1-flash-lite is Google's Stable, "
        "non-deprecated 3.5-generation successor: image/PDF input, structured JSON via response_mime_type + "
        "response_json_schema, positioned by Google as its fastest/most cost-effective high-throughput model).",
        round="free",
        cost_classification="zero_cost_eligible",
        payment_method_required=False,
        billing_spillover_possible=False,
        free_tier_limits=FreeTierLimits(
            rpm=15, rpd=1000, tpm=250_000, tpd=None,
            source="third-party aggregator estimate (aifreeapi.com/pecollective.com) -- ai.google.dev/gemini-api/"
            "docs/rate-limits no longer publishes static per-model numbers, directs to the live "
            "aistudio.google.com/rate-limit dashboard instead. Confirm live figures before executing.",
            official=False,
        ),
        privacy_note="CONFIRMED: ai.google.dev/gemini-api/docs/billing states the Free Tier 'does not require a "
        "billing account' and upgrading requires explicitly linking billing and prepaying a $10 minimum -- no "
        "silent/automatic charge is possible. However, ai.google.dev/gemini-api/terms confirms free-tier "
        "content 'may be used to improve... Google products' and 'human reviewers may read, annotate, and "
        "process' API input/output -- materially weaker privacy than the paid tier. Acceptable for this "
        "benchmark ONLY because every fixture is synthetic/rights-safe -- see runner.py's preflight warning.",
    ),
    # --- Round 2: paid (not executed without separate approval) -----------
    FinalistConfig(
        label="OpenAI GPT-5",
        provider_kind="openai-compatible",
        model="gpt-5",
        base_url="https://api.openai.com/v1",
        credential_env_var="LOCAL_LENS_BENCHMARK_OPENAI_API_KEY",
        pricing=TokenPricing(1.25, 10.00, "developers.openai.com/api/docs/pricing, Aug 2026"),
        role="strong proprietary general VLM -- generic OpenAI-compatible adapter, no new code",
        round="paid",
        cost_classification="paid",
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
        round="paid",
        cost_classification="paid",
    ),
    FinalistConfig(
        label="Qwen2.5-VL-72B-Instruct (Fireworks AI)",
        provider_kind="openai-compatible",
        model="accounts/fireworks/models/qwen2p5-vl-72b-instruct",
        base_url="https://api.fireworks.ai/inference/v1",
        credential_env_var="LOCAL_LENS_BENCHMARK_FIREWORKS_API_KEY",
        pricing=TokenPricing(0.9, 0.9, "docs.fireworks.ai/serverless/pricing, Aug 2026, approximate"),
        role="strongest hosted open VLM with a named OCR/document-VLM catalog -- generic adapter, no new code",
        round="paid",
        cost_classification="paid",
    ),
    FinalistConfig(
        label="PaddleOCR-VL-1.6 (remote vLLM)",
        provider_kind="paddle-vllm",
        model="PaddleOCR-VL-1.6",
        base_url=None,
        credential_env_var=None,
        pricing=TokenPricing(0.0, 0.0, "GPU-second billing, not token billing -- no endpoint provisioned"),
        role="excluded from execution in every round: no GPU endpoint has been provisioned, and provisioning one "
        "requires separate approval. Prior local measurements (docs/V4_DIRECTION.md) remain valid reference "
        "evidence; this row exists so the comparison isn't silently missing PaddleOCR-VL, just marked unexecutable. "
        "Confirmed NOT routable through Hugging Face Inference Providers either (its own HF model page states "
        "'This model isn't deployed by any Inference Provider').",
        round="paid",
        cost_classification="unknown",
        executable_in_first_run=False,
    ),
]

# Backward-compat alias for the pre-existing dry-run code path.
PROPOSED_FINALISTS = FINALISTS


def finalists_for_round(round_name: str) -> list[FinalistConfig]:
    return [fc for fc in FINALISTS if fc.round == round_name]


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
