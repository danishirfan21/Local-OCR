"""Provider-independent Deep Analyze benchmark contract.

Defines the input (`DeepBenchmarkCase`) and output (`DeepBenchmarkResult`)
shape for comparing Deep Analyze providers/models against each other and
against ground truth, plus cost estimation and an extraction-fidelity
("hallucination") signal. Nothing here depends on any one vendor's SDK or
response format -- a case is just an image + expected ground truth, and a
result is what any `DeepAnalysisProvider` produced for it, whatever the
underlying API looked like.

This module defines the CONTRACT and lightweight, dependency-free scoring
only. It deliberately does not make any network call -- see
local_lens/cli.py's `benchmark-deep` command for the (currently dry-run-only)
runner built on top of this.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from local_lens.models import DocumentResult


@dataclass
class DeepBenchmarkCase:
    """One fixture to send to every candidate provider, plus what a
    faithful extraction should produce. `expected_table` is a plain
    list-of-rows (not a full TableResult) since ground truth is authored by
    hand/generated, not extracted."""

    id: str
    category: str
    image_path: Path
    expected_text: str | None = None
    expected_content_type: str | None = None
    expected_table: list[list[str]] | None = None
    languages: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class DeepBenchmarkResult:
    """What one provider produced for one case. `success=False` means the
    provider raised (see local_lens/deep_analysis/base.py's exception
    hierarchy) -- `error` carries the sanitized message, `text`/
    `parsed_result` stay empty/None rather than partially populated."""

    case_id: str
    provider: str
    model: str
    latency_ms: float
    success: bool
    text: str = ""
    parsed_result: DocumentResult | None = None
    error: str | None = None
    estimated_cost_usd: float | None = None
    http_status: int | None = None


# --- cost estimation --------------------------------------------------------


@dataclass(frozen=True)
class TokenPricing:
    """Per-1M-token USD pricing. `basis` documents where the number came
    from -- this module never invents a number, only applies one that was
    supplied by the caller (typically sourced from a provider's published
    pricing page and recorded in docs/DEEP_PROVIDER_EVALUATION.md)."""

    input_per_million: float
    output_per_million: float
    basis: str = "provider published pricing, approximate"


def estimate_request_cost(
    pricing: TokenPricing,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
) -> float:
    """Rough per-request cost estimate. Deliberately approximate: actual
    image tokenization depends on provider-specific tiling/patch formulas
    (see docs/DEEP_PROVIDER_EVALUATION.md for each provider's documented
    formula) that this function does not attempt to replicate exactly --
    callers should treat the result as an upper-bound planning number, not
    a bill prediction."""
    input_cost = (estimated_input_tokens / 1_000_000) * pricing.input_per_million
    output_cost = (estimated_output_tokens / 1_000_000) * pricing.output_per_million
    return round(input_cost + output_cost, 6)


# --- extraction-fidelity ("hallucination") signal ---------------------------


def extra_content_rate(produced_text: str, expected_text: str) -> float:
    """Fraction of words in `produced_text` that don't appear in
    `expected_text`'s word multiset -- a simple extraction-fidelity signal,
    NOT a semantic hallucination detector. High values suggest the model
    added content (commentary, invented values, autocorrected/expanded
    text) beyond what's actually in the source image; it will also flag
    genuine recognition errors as "extra" (a misread word is technically
    not in the ground truth either), so this is a coarse, conservative
    signal meant to be read alongside CER/WER, not in isolation.

    Returns 0.0 for an empty produced_text (nothing extra was added) and
    1.0 if expected_text is empty but produced_text is not (everything
    produced is "extra" when nothing was expected).
    """
    produced_words = _words(produced_text)
    if not produced_words:
        return 0.0

    expected_words = _words(expected_text)
    if not expected_words:
        return 1.0

    from collections import Counter

    expected_counts = Counter(expected_words)
    extra = 0
    for word in produced_words:
        if expected_counts[word] > 0:
            expected_counts[word] -= 1
        else:
            extra += 1

    return round(extra / len(produced_words), 3)


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())
