"""Deep Analyze bake-off scoring: reuses benchmarks/metrics.py's CER/WER/
similarity/table functions (no reinvented OCR metrics), adds code-specific
signals, and a documented, transparent weighted composite.

Named `deep_metrics.py` (not `metrics.py`) to avoid colliding with the
top-level `benchmarks/metrics.py` module in imports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from benchmarks.metrics import character_error_rate, normalized_similarity, table_structure_accuracy, word_error_rate
from local_lens.deep_analysis.benchmark import extra_content_rate

# Composite score weights. Suggested, not sacred -- documented here (and in
# docs/DEEP_PROVIDER_EVALUATION.md) so anyone can see and adjust them.
# Extraction fidelity (low CER/WER + low hallucination) is weighted
# heaviest because Deep Analyze's core job is faithful transcription, not
# general chat quality; latency and cost are weighted lowest because for a
# once-in-a-while "read this screenshot carefully" action, a few extra
# seconds/cents matters far less than getting the content right.
COMPOSITE_WEIGHTS = {
    "extraction_fidelity": 0.30,
    "tables": 0.20,
    "code": 0.15,
    "urdu_multilingual": 0.15,
    "reliability": 0.10,
    "latency": 0.05,
    "cost": 0.05,
}
assert abs(sum(COMPOSITE_WEIGHTS.values()) - 1.0) < 1e-9


@dataclass
class CaseScore:
    case_id: str
    category: str
    cer: float | None = None
    wer: float | None = None
    similarity: float | None = None
    extra_content_rate: float | None = None
    table_accuracy: dict | None = None
    code_line_count_similarity: float | None = None
    code_indentation_preservation: float | None = None
    code_punctuation_accuracy: float | None = None


def score_text_case(produced_text: str, expected_text: str) -> dict:
    return {
        "cer": round(character_error_rate(produced_text, expected_text), 4),
        "wer": round(word_error_rate(produced_text, expected_text), 4),
        "similarity": round(normalized_similarity(produced_text, expected_text), 4),
        "extra_content_rate": extra_content_rate(produced_text, expected_text),
    }


def score_table_case(produced_rows: list[list[str]], expected_rows: list[list[str]]) -> dict:
    return table_structure_accuracy(produced_rows, expected_rows)


_SEPARATOR_CELL = re.compile(r":?-{2,}:?$")


def parse_markdown_table(text: str) -> list[list[str]]:
    """Extract a markdown pipe-table from free-form text into rows, header
    included as the first row (matching this project's ground-truth
    convention -- see benchmarks/corpus.py's CORPUS entries). Returns []
    if no table-shaped lines are found.

    Deep Analyze providers are asked (prompts.py) to represent a table as
    markdown inside a block's text, not as this project's own TableResult
    structure -- DocumentResult.tables is only ever populated by the local
    PaddleOCR table pipeline, never by a remote provider adapter. Without
    this parser, every table fixture's `doc_result.tables` is empty
    regardless of extraction quality, which would silently score every
    provider as a total table failure even when the markdown reply was
    correct -- exactly the "provider was right, our parser discarded it"
    failure mode this project has already been burned by once (see
    docs/V4_DIRECTION.md's PaddleOCR-VL evaluator bug)."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not any(cells):
            continue
        if all(_SEPARATOR_CELL.fullmatch(c) for c in cells if c):
            continue  # the "|---|---|---|" header/body divider row
        rows.append(cells)
    return rows


# --- code-specific signals -------------------------------------------------


def line_count_similarity(produced: str, expected: str) -> float:
    """1.0 if line counts match exactly; degrades linearly with the
    relative difference. A cheap proxy for "did the model preserve line
    structure" without needing a real diff/AST comparison."""
    produced_lines = produced.splitlines()
    expected_lines = expected.splitlines()
    if not expected_lines:
        return 1.0 if not produced_lines else 0.0
    diff = abs(len(produced_lines) - len(expected_lines))
    return round(max(0.0, 1.0 - diff / len(expected_lines)), 4)


def indentation_preservation(produced: str, expected: str) -> float:
    """Fraction of expected lines whose leading-whitespace count is
    matched by the produced line at the same index -- a proxy for "did the
    model preserve code structure" rather than reformatting/flattening it.
    Lines beyond the shorter of the two are simply not counted (already
    penalized by line_count_similarity)."""
    produced_lines = produced.splitlines()
    expected_lines = expected.splitlines()
    if not expected_lines:
        return 1.0

    matches = 0
    n = min(len(produced_lines), len(expected_lines))
    for i in range(n):
        produced_indent = len(produced_lines[i]) - len(produced_lines[i].lstrip())
        expected_indent = len(expected_lines[i]) - len(expected_lines[i].lstrip())
        if produced_indent == expected_indent:
            matches += 1
    return round(matches / len(expected_lines), 4)


def punctuation_accuracy(produced: str, expected: str) -> float:
    """Overlap of non-alphanumeric-non-whitespace character multisets --
    a cheap proxy for "did the model preserve exact punctuation/symbols"
    (braces, semicolons, operators) rather than "helpfully" reformatting
    code. Not a syntax checker."""
    from collections import Counter

    def _symbols(text: str) -> Counter:
        return Counter(ch for ch in text if not ch.isalnum() and not ch.isspace())

    expected_symbols = _symbols(expected)
    produced_symbols = _symbols(produced)
    total_expected = sum(expected_symbols.values())
    if total_expected == 0:
        return 1.0 if sum(produced_symbols.values()) == 0 else 0.0

    matched = sum(min(expected_symbols[ch], produced_symbols.get(ch, 0)) for ch in expected_symbols)
    return round(matched / total_expected, 4)


def score_code_case(produced: str, expected: str) -> dict:
    return {
        "cer": round(character_error_rate(produced, expected), 4),
        "line_count_similarity": line_count_similarity(produced, expected),
        "indentation_preservation": indentation_preservation(produced, expected),
        "punctuation_accuracy": punctuation_accuracy(produced, expected),
    }


# --- reliability -------------------------------------------------------


@dataclass
class ReliabilitySummary:
    total: int = 0
    successes: int = 0
    structured_responses: int = 0
    empty_results: int = 0
    malformed_responses: int = 0

    @property
    def success_rate(self) -> float:
        return round(self.successes / self.total, 4) if self.total else 0.0

    @property
    def structured_response_rate(self) -> float:
        return round(self.structured_responses / self.total, 4) if self.total else 0.0


# --- composite score -----------------------------------------------------


@dataclass
class ProviderSummary:
    provider: str
    model: str
    mean_cer: float | None
    mean_similarity: float | None
    mean_extra_content_rate: float | None
    mean_table_cell_accuracy: float | None
    mean_code_indentation_preservation: float | None
    reliability: ReliabilitySummary
    median_latency_ms: float | None
    p95_latency_ms: float | None
    total_cost_usd: float | None


def composite_score(summary: ProviderSummary) -> float | None:
    """A transparent 0-1 composite using COMPOSITE_WEIGHTS. Returns None
    (not a fabricated number) if there isn't enough data for a category --
    callers should always show the individual metrics alongside this, not
    instead of them (see docs/DEEP_PROVIDER_EVALUATION.md's own warning
    against manufacturing false precision from a 12-fixture corpus)."""
    components: dict[str, float] = {}

    if summary.mean_similarity is not None and summary.mean_extra_content_rate is not None:
        components["extraction_fidelity"] = max(
            0.0, (summary.mean_similarity - summary.mean_extra_content_rate + 1.0) / 2.0
        )
    if summary.mean_table_cell_accuracy is not None:
        components["tables"] = summary.mean_table_cell_accuracy
    if summary.mean_code_indentation_preservation is not None:
        components["code"] = summary.mean_code_indentation_preservation
    # Urdu/multilingual reuses extraction fidelity on Urdu-category cases
    # specifically -- callers pass a pre-filtered summary for this slot if
    # they want it distinct; left absent here rather than double-counted.
    components["reliability"] = summary.reliability.success_rate

    if summary.median_latency_ms is not None:
        # 0s -> 1.0, 30s+ -> 0.0, linear in between. 30s chosen as a
        # generous ceiling given V3's own measured PaddleOCR-VL CPU
        # latency (8-132s) -- a remote GPU-backed API should comfortably
        # beat that, so 30s is a lenient, not aggressive, cutoff.
        components["latency"] = max(0.0, 1.0 - summary.median_latency_ms / 30_000)

    if summary.total_cost_usd is not None:
        # $0 -> 1.0, $0.01/request+ -> 0.0 -- this corpus's own token-billed
        # estimates top out around $0.01/request (Claude Sonnet 5, the most
        # expensive finalist), so that's used as the ceiling rather than an
        # arbitrary round number.
        components["cost"] = max(0.0, 1.0 - summary.total_cost_usd / 0.01)

    if not components:
        return None

    weighted_sum = sum(COMPOSITE_WEIGHTS[k] * v for k, v in components.items())
    weight_total = sum(COMPOSITE_WEIGHTS[k] for k in components)
    return round(weighted_sum / weight_total, 4) if weight_total else None
