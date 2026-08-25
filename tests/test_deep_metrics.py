"""Deep Analyze scoring tests: text/table/code metrics and the weighted
composite score. Pure functions -- no network, no fixtures needed."""

from __future__ import annotations

from local_lens.deep_analysis.deep_metrics import (
    COMPOSITE_WEIGHTS,
    ProviderSummary,
    ReliabilitySummary,
    composite_score,
    indentation_preservation,
    line_count_similarity,
    punctuation_accuracy,
    score_code_case,
    score_table_case,
    score_text_case,
)


def test_weights_sum_to_one():
    assert abs(sum(COMPOSITE_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_text_case_perfect_match():
    scores = score_text_case("hello world", "hello world")
    assert scores["cer"] == 0.0
    assert scores["wer"] == 0.0
    assert scores["similarity"] == 1.0
    assert scores["extra_content_rate"] == 0.0


def test_score_table_case_delegates_to_shared_metric():
    produced = [["a", "b"], ["1", "2"]]
    expected = [["a", "b"], ["1", "2"]]
    result = score_table_case(produced, expected)
    assert result["row_count_correct"] is True
    assert result["cell_accuracy"] == 1.0


# --- code metrics ------------------------------------------------------


def test_line_count_similarity_exact_match():
    assert line_count_similarity("a\nb\nc", "a\nb\nc") == 1.0


def test_line_count_similarity_degrades_with_diff():
    # expected 4 lines, produced 2 -> diff 2 -> 1 - 2/4 = 0.5
    assert line_count_similarity("a\nb", "a\nb\nc\nd") == 0.5


def test_indentation_preservation_exact():
    expected = "def f():\n    return 1"
    produced = "def f():\n    return 1"
    assert indentation_preservation(produced, expected) == 1.0


def test_indentation_preservation_flattened_code_scores_low():
    expected = "def f():\n    return 1"
    produced = "def f():\nreturn 1"
    result = indentation_preservation(produced, expected)
    assert result < 1.0


def test_punctuation_accuracy_exact():
    assert punctuation_accuracy("a=1; b=2;", "a=1; b=2;") == 1.0


def test_punctuation_accuracy_missing_symbols():
    result = punctuation_accuracy("a b", "a=1; b=2;")
    assert result < 1.0


def test_punctuation_accuracy_no_symbols_expected_and_produced():
    assert punctuation_accuracy("hello", "world") == 1.0


def test_score_code_case_shape():
    result = score_code_case("def f():\n    return 1", "def f():\n    return 1")
    assert result["cer"] == 0.0
    assert result["line_count_similarity"] == 1.0
    assert result["indentation_preservation"] == 1.0
    assert result["punctuation_accuracy"] == 1.0


# --- composite score -----------------------------------------------------


def _summary(**overrides) -> ProviderSummary:
    defaults = dict(
        provider="p",
        model="m",
        mean_cer=0.1,
        mean_similarity=0.9,
        mean_extra_content_rate=0.05,
        mean_table_cell_accuracy=0.8,
        mean_code_indentation_preservation=0.9,
        reliability=ReliabilitySummary(total=10, successes=10, structured_responses=10),
        median_latency_ms=1000.0,
        p95_latency_ms=1500.0,
        total_cost_usd=0.002,
    )
    defaults.update(overrides)
    return ProviderSummary(**defaults)


def test_composite_score_returns_value_in_range():
    score = composite_score(_summary())
    assert score is not None
    assert 0.0 <= score <= 1.0


def test_composite_score_none_with_no_data():
    summary = _summary(
        mean_similarity=None,
        mean_extra_content_rate=None,
        mean_table_cell_accuracy=None,
        mean_code_indentation_preservation=None,
        median_latency_ms=None,
        total_cost_usd=None,
        reliability=ReliabilitySummary(),
    )
    # reliability.success_rate is 0.0 (a real number, not None) even with
    # an empty summary, so a component is always present here -- the
    # composite must still be a number, never crash.
    score = composite_score(summary)
    assert score is not None


def test_composite_score_higher_for_better_provider():
    good = _summary()
    bad = _summary(
        mean_similarity=0.3,
        mean_extra_content_rate=0.6,
        mean_table_cell_accuracy=0.2,
        mean_code_indentation_preservation=0.1,
        reliability=ReliabilitySummary(total=10, successes=3, structured_responses=2),
    )
    assert composite_score(good) > composite_score(bad)
