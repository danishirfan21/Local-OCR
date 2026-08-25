"""Unified result models shared by every OCR/document-understanding engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ContentType(str, Enum):
    """Coarse heuristic classification of extracted content."""

    TEXT = "text"
    CODE = "code"
    TABLE = "table"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned box in pixel coordinates of the (preprocessed) input image."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2

    @classmethod
    def from_points(cls, points: list[tuple[float, float]]) -> "BoundingBox":
        """Build an axis-aligned box from an arbitrary polygon (e.g. a 4-point quad)."""
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        left, top = min(xs), min(ys)
        return cls(
            left=int(round(left)),
            top=int(round(top)),
            width=int(round(max(xs) - left)),
            height=int(round(max(ys) - top)),
        )


@dataclass
class TextBlock:
    """A single recognized unit of text (word or line, engine-dependent)."""

    text: str
    confidence: float | None
    bbox: BoundingBox | None


@dataclass
class TableCell:
    """A single cell within a recognized table."""

    row: int
    column: int
    text: str
    confidence: float | None = None
    bbox: BoundingBox | None = None


@dataclass
class TableResult:
    """A single recognized table.

    `has_header` is only True when the extractor actually distinguished a
    header row -- callers must not assume rows[0] is a header unless this is
    set, since fabricating a header the model didn't identify would be
    misleading in exports.

    `metadata` carries deterministic, computable quality indicators (row/
    column counts, empty-cell ratio, whether cleanup removed anything) --
    never a fabricated confidence score the backend didn't actually provide.
    """

    rows: list[list[str]]
    cells: list[TableCell]
    markdown: str | None
    confidence: float | None
    bbox: BoundingBox | None
    has_header: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class DocumentBlock:
    """A structured content block, for engines that expose more than flat text.

    Populated only by engines with real layout/structure awareness (e.g.
    PaddleOCR-VL's parsing_res_list) -- engines that only return flat
    word/line-level text (EasyOCR, plain PaddleOCR) leave
    DocumentResult.document_blocks empty rather than fabricating structure.
    `type` values are only ever ones an engine actually returned and this
    codebase has validated, not a speculative full taxonomy.
    """

    type: str
    text: str
    bbox: BoundingBox | None
    metadata: dict = field(default_factory=dict)


@dataclass
class DocumentResult:
    """Unified output of any OCR/document-understanding engine.

    `metadata` is deliberately open-ended so future engines can attach richer
    structured output (formulas, document type, timings, routing rationale,
    ...) without changing this schema. `tables`, `detected_scripts`, and
    `detected_languages` are promoted to real fields (rather than living in
    metadata like `content_type` does) because they are structural results
    other code needs to branch on, not free-form annotations.
    """

    text: str
    blocks: list[TextBlock]
    language: str | None
    engine: str
    metadata: dict = field(default_factory=dict)
    tables: list[TableResult] = field(default_factory=list)
    detected_scripts: list[str] = field(default_factory=list)
    detected_languages: list[str] = field(default_factory=list)
    document_blocks: list[DocumentBlock] = field(default_factory=list)

    @property
    def average_confidence(self) -> float | None:
        confidences = [b.confidence for b in self.blocks if b.confidence is not None]
        if not confidences:
            return None
        return sum(confidences) / len(confidences)
