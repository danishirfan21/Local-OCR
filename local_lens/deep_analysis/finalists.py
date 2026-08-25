"""The proposed bake-off finalists (research-stage only -- none of these
have been called over the network from this repository).

Pricing is sourced from each provider's published pricing page as of the
research pass documented in docs/DEEP_PROVIDER_EVALUATION.md, recorded
here so `local-lens benchmark-deep --dry-run` can show the same maximum-
cost estimate the docs report -- one source of truth, not two numbers that
can drift apart. All figures are approximate/upper-bound planning numbers,
not bills (see benchmark.py's `estimate_request_cost` docstring for why).
"""

from __future__ import annotations

from dataclasses import dataclass

from local_lens.deep_analysis.benchmark import TokenPricing


@dataclass(frozen=True)
class ProposedFinalist:
    label: str
    provider: str  # matches LOCAL_LENS_DEEP_PROVIDER values
    model: str
    pricing: TokenPricing
    role: str


# Rough per-request token budget for THIS benchmark's images (small,
# synthetic, mostly short text): ~1,000 input tokens (image + prompt),
# ~500 output tokens (structured JSON reply). Deliberately conservative
# (an upper bound) -- real usage will likely be lower for the short_ui/
# code fixtures and could be higher for the photographed-document fixture.
ESTIMATED_INPUT_TOKENS_PER_REQUEST = 1000
ESTIMATED_OUTPUT_TOKENS_PER_REQUEST = 500

PROPOSED_FINALISTS: list[ProposedFinalist] = [
    ProposedFinalist(
        label="OpenAI GPT-5",
        provider="openai-compatible",
        model="gpt-5",
        pricing=TokenPricing(1.25, 10.00, "developers.openai.com/api/docs/pricing, Aug 2026"),
        role="strong proprietary general VLM -- works against the existing generic adapter unmodified",
    ),
    ProposedFinalist(
        label="Gemini 2.5 Flash-Lite",
        provider="openai-compatible",
        model="gemini-2.5-flash-lite",
        pricing=TokenPricing(0.10, 0.40, "ai.google.dev/gemini-api/docs/pricing, Aug 2026"),
        role="cheapest proprietary option -- via Gemini's OpenAI-compatible beta endpoint",
    ),
    ProposedFinalist(
        label="PaddleOCR-VL-1.6 (self-hosted vLLM)",
        provider="paddle-vllm",
        model="PaddleOCR-VL-1.6",
        pricing=TokenPricing(0.0, 0.0, "GPU-second billing, not token billing -- see docs for compute cost basis"),
        role="the original candidate -- must stay in the comparison to answer whether it's still worth self-hosting",
    ),
    ProposedFinalist(
        label="Qwen2.5-VL-72B-Instruct (Fireworks AI)",
        provider="openai-compatible",
        model="accounts/fireworks/models/qwen2p5-vl-72b-instruct",
        pricing=TokenPricing(0.9, 0.9, "docs.fireworks.ai/serverless/pricing, Aug 2026, approximate"),
        role="strongest hosted open VLM with a named OCR/document-VLM catalog -- generic adapter, no new code",
    ),
    ProposedFinalist(
        label="Claude Sonnet 5",
        provider="anthropic",
        model="claude-sonnet-5",
        pricing=TokenPricing(3.00, 15.00, "platform.claude.com pricing, Aug 2026"),
        role="tests whether Anthropic's explicit anti-hallucination/low-confidence guidance in its own vision "
        "docs translates into a measurably lower extra_content_rate -- the one finalist needing a dedicated adapter",
    ),
]
