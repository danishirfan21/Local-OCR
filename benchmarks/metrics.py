"""Benchmark metrics: CER, WER, normalized similarity, and table accuracy.

Pure functions, no dependencies beyond the standard library, so they can be
unit-tested without any OCR engine or model.
"""

from __future__ import annotations

from difflib import SequenceMatcher


def _levenshtein(a: list, b: list) -> int:
    """Standard O(len(a)*len(b)) edit distance over arbitrary sequences."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, y in enumerate(b, start=1):
            cost = 0 if x == y else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def character_error_rate(predicted: str, ground_truth: str) -> float:
    """CER = edit_distance(chars) / len(ground_truth chars). 0.0 = perfect."""
    if not ground_truth:
        return 0.0 if not predicted else 1.0
    distance = _levenshtein(list(predicted), list(ground_truth))
    return distance / len(ground_truth)


def word_error_rate(predicted: str, ground_truth: str) -> float:
    """WER = edit_distance(words) / len(ground_truth words). 0.0 = perfect."""
    gt_words = ground_truth.split()
    pred_words = predicted.split()
    if not gt_words:
        return 0.0 if not pred_words else 1.0
    distance = _levenshtein(pred_words, gt_words)
    return distance / len(gt_words)


def normalized_similarity(predicted: str, ground_truth: str) -> float:
    """SequenceMatcher ratio in [0, 1], 1.0 = identical. Case/whitespace-insensitive."""
    a = " ".join(predicted.lower().split())
    b = " ".join(ground_truth.lower().split())
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def table_structure_accuracy(predicted_rows: list[list[str]], ground_truth_rows: list[list[str]]) -> dict:
    """Row/column count accuracy and cell-text accuracy for a table result."""
    gt_row_count = len(ground_truth_rows)
    gt_col_count = len(ground_truth_rows[0]) if ground_truth_rows else 0
    pred_row_count = len(predicted_rows)
    pred_col_count = len(predicted_rows[0]) if predicted_rows else 0

    row_count_correct = pred_row_count == gt_row_count
    col_count_correct = pred_col_count == gt_col_count

    cell_matches = 0
    total_cells = gt_row_count * gt_col_count
    for r in range(min(pred_row_count, gt_row_count)):
        for c in range(min(pred_col_count, gt_col_count)):
            if predicted_rows[r][c].strip().lower() == ground_truth_rows[r][c].strip().lower():
                cell_matches += 1
    cell_accuracy = cell_matches / total_cells if total_cells else 0.0

    return {
        "row_count_correct": row_count_correct,
        "column_count_correct": col_count_correct,
        "predicted_rows": pred_row_count,
        "ground_truth_rows": gt_row_count,
        "predicted_columns": pred_col_count,
        "ground_truth_columns": gt_col_count,
        "cell_accuracy": cell_accuracy,
    }
