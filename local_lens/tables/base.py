"""Table extraction interface, mirroring engines/base.py's OCREngine.

Kept as a separate concern from OCREngine on purpose (see
local_lens/services/ocr_service.py): table extraction is more expensive
than plain OCR and should only run when content analysis already suspects
a table, not on every image.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from PIL import Image

from local_lens.models import TableResult


@runtime_checkable
class TableExtractor(Protocol):
    name: str

    def extract(self, image: Image.Image) -> list[TableResult]:
        """Return zero or more tables found in `image`.

        Implementations should raise a clear, actionable exception if the
        backend isn't available, matching OCREngine's convention -- callers
        are expected to catch failures and degrade gracefully rather than
        losing the whole OCR result.
        """
        ...
