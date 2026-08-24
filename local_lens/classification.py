"""Heuristic content-type classification.

Deliberately not ML-based. This is a placeholder service boundary: a future
VLM/LLM-based classifier can replace `classify()` without changing callers,
since it already returns (ContentType, confidence).
"""

from __future__ import annotations

import re

from local_lens.models import ContentType, TextBlock

_CODE_CHARS = set("{}[]();=<>+-*/&|!:")
_CODE_KEYWORDS = re.compile(
    r"\b(def|function|class|import|return|const|let|var|if|else|for|while|"
    r"public|private|static|void|int|struct|SELECT|FROM|WHERE)\b"
)


def classify(text: str, blocks: list[TextBlock] | None = None) -> tuple[ContentType, float]:
    """Return a best-effort (content_type, confidence) for `text`.

    Confidence is intentionally coarse (0.5 = weak heuristic signal, 0.0 =
    no signal) -- this is not a calibrated probability.

    `blocks` is optional: when OCR bounding boxes are available, they add a
    geometry-based table signal (consistent column x-positions across
    lines) on top of the existing text-only heuristic, which is stronger
    evidence than punctuation/whitespace patterns alone. Omitting it falls
    back to the original text-only behavior, so existing callers are
    unaffected.
    """
    stripped = text.strip()
    if not stripped:
        return ContentType.UNKNOWN, 0.0

    lines = [line for line in stripped.splitlines() if line.strip()]
    if not lines:
        return ContentType.UNKNOWN, 0.0

    code_score = _code_score(stripped, lines)
    table_score = _table_score(lines)
    if blocks:
        table_score = max(table_score, _geometry_table_score(blocks))

    if code_score >= 0.5 and code_score >= table_score:
        return ContentType.CODE, min(code_score, 0.9)
    if table_score >= 0.5 and table_score > code_score:
        return ContentType.TABLE, min(table_score, 0.9)
    return ContentType.TEXT, 0.5


def _code_score(text: str, lines: list[str]) -> float:
    symbol_count = sum(1 for ch in text if ch in _CODE_CHARS)
    symbol_density = symbol_count / max(len(text), 1)

    indented_lines = sum(1 for line in lines if line.startswith((" ", "\t")))
    indent_ratio = indented_lines / len(lines)

    keyword_hits = len(_CODE_KEYWORDS.findall(text))

    score = 0.0
    score += min(symbol_density * 6, 0.5)
    score += min(indent_ratio * 0.4, 0.3)
    score += min(keyword_hits * 0.1, 0.3)
    return min(score, 1.0)


def _table_score(lines: list[str]) -> float:
    if len(lines) < 2:
        return 0.0

    # A table-like layout tends to have multiple lines with a similar
    # number of whitespace-separated columns, or explicit delimiters.
    column_counts = [len(re.split(r"\s{2,}|\t|\|", line.strip())) for line in lines]
    multi_column = [c for c in column_counts if c >= 2]
    multi_column_ratio = len(multi_column) / len(lines)

    if not multi_column:
        return 0.0

    from statistics import pstdev

    consistency = 1.0 - min(pstdev(multi_column) / max(max(multi_column), 1), 1.0)

    return min(multi_column_ratio * 0.6 + consistency * 0.4, 1.0)


def _geometry_table_score(blocks: list[TextBlock], x_bucket_px: int = 15) -> float:
    """Table evidence from OCR geometry: repeated aligned column x-positions.

    Groups blocks into lines by vertical center proximity, then checks how
    many lines share left-edge x-position "buckets" with at least one other
    line -- a hallmark of tabular/columnar layout that plain text rarely
    produces by coincidence.
    """
    positioned = [b for b in blocks if b.bbox is not None]
    if len(positioned) < 4:
        return 0.0

    positioned.sort(key=lambda b: b.bbox.center_y)
    lines: list[list[TextBlock]] = []
    for block in positioned:
        placed = False
        for line in lines:
            ref = line[0]
            half_height = max(ref.bbox.height, block.bbox.height) / 2
            if abs(block.bbox.center_y - ref.bbox.center_y) <= half_height:
                line.append(block)
                placed = True
                break
        if not placed:
            lines.append([block])

    if len(lines) < 2:
        return 0.0

    bucket_to_lines: dict[int, set[int]] = {}
    for line_idx, line in enumerate(lines):
        for block in line:
            bucket = round(block.bbox.left / x_bucket_px)
            bucket_to_lines.setdefault(bucket, set()).add(line_idx)

    shared_buckets = [lines_set for lines_set in bucket_to_lines.values() if len(lines_set) >= 2]
    if not shared_buckets:
        return 0.0

    lines_in_shared_columns = set().union(*shared_buckets)
    alignment_ratio = len(lines_in_shared_columns) / len(lines)
    column_richness = min(len(shared_buckets) / 3, 1.0)

    return min(alignment_ratio * 0.7 + column_richness * 0.3, 1.0)
