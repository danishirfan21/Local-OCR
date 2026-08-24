"""OCR/document engine interface.

Every backend (EasyOCR, PaddleOCR, future VLM-based engines) implements this
protocol so the rest of Local Lens -- the service layer, the UI, and later a
CLI/API -- can treat engines interchangeably.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from PIL import Image

from local_lens.models import DocumentResult


@runtime_checkable
class OCREngine(Protocol):
    """A document/OCR backend that turns an image into a DocumentResult."""

    name: str

    def extract(self, image: Image.Image, langs: list[str]) -> DocumentResult:
        """Run recognition on `image` for the given canonical language codes.

        Implementations should raise a clear, actionable exception (e.g. a
        RuntimeError explaining what to install) rather than failing with an
        opaque ImportError if the backend isn't available.
        """
        ...
