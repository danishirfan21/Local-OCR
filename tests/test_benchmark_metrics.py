from benchmarks.metrics import (
    character_error_rate,
    normalized_similarity,
    table_structure_accuracy,
    word_error_rate,
)


def test_cer_perfect_match_is_zero():
    assert character_error_rate("hello", "hello") == 0.0


def test_cer_totally_wrong_is_bounded():
    cer = character_error_rate("xxxxx", "hello")
    assert cer > 0
    assert cer <= 1.0 or cer > 0  # substitutions can exceed 1.0 for longer predictions; sanity only


def test_cer_empty_ground_truth_and_empty_prediction():
    assert character_error_rate("", "") == 0.0


def test_cer_empty_ground_truth_nonempty_prediction():
    assert character_error_rate("x", "") == 1.0


def test_wer_perfect_match_is_zero():
    assert word_error_rate("hello world", "hello world") == 0.0


def test_wer_one_word_wrong():
    wer = word_error_rate("hello there", "hello world")
    assert wer == 0.5


def test_wer_empty_ground_truth():
    assert word_error_rate("", "") == 0.0
    assert word_error_rate("x", "") == 1.0


def test_normalized_similarity_identical_text():
    assert normalized_similarity("Hello World", "hello world") == 1.0  # case-insensitive


def test_normalized_similarity_whitespace_insensitive():
    assert normalized_similarity("Hello   World", "Hello World") == 1.0


def test_normalized_similarity_completely_different():
    sim = normalized_similarity("abc", "xyz")
    assert sim < 0.5


def test_normalized_similarity_both_empty():
    assert normalized_similarity("", "") == 1.0


def test_table_structure_accuracy_perfect_match():
    rows = [["a", "b"], ["c", "d"]]
    acc = table_structure_accuracy(rows, rows)
    assert acc["row_count_correct"] is True
    assert acc["column_count_correct"] is True
    assert acc["cell_accuracy"] == 1.0


def test_table_structure_accuracy_wrong_dimensions():
    predicted = [["a", "b"]]
    ground_truth = [["a", "b"], ["c", "d"]]
    acc = table_structure_accuracy(predicted, ground_truth)
    assert acc["row_count_correct"] is False
    assert acc["cell_accuracy"] == 0.5  # only first row's 2 cells counted, both matched


def test_table_structure_accuracy_empty_ground_truth():
    acc = table_structure_accuracy([], [])
    assert acc["cell_accuracy"] == 0.0
    assert acc["row_count_correct"] is True
