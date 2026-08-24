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
class DocumentResult:
    """Unified output of any OCR/document-understanding engine.

    `metadata` is deliberately open-ended so future engines can attach richer
    structured output (tables, formulas, markdown, document type, ...)
    without changing this schema.
    """

    text: str
    blocks: list[TextBlock]
    language: str | None
    engine: str
    metadata: dict = field(default_factory=dict)

    @property
    def average_confidence(self) -> float | None:
        confidences = [b.confidence for b in self.blocks if b.confidence is not None]
        if not confidences:
            return None
        return sum(confidences) / len(confidences)
