"""EasyOCR backend."""

from __future__ import annotations

import numpy as np
from PIL import Image

from local_lens.languages import to_engine_code
from local_lens.models import BoundingBox, DocumentResult, TextBlock

# Reader construction (model load) is expensive, so instances are cached
# per language set. Streamlit additionally wraps the *service* in
# st.cache_resource, but caching here too keeps this module usable
# standalone (CLI, tests, future API) without depending on Streamlit.
_reader_cache: dict[tuple[str, ...], object] = {}


def _get_reader(engine_langs: list[str], *, download_enabled: bool):
    import easyocr  # imported lazily so importing this module is cheap

    # download_enabled is not part of the cache key -- a given language set
    # only ever gets constructed once per process regardless of which
    # caller asked first, matching the existing single-cache-per-language
    # design (see the class docstring above).
    key = tuple(sorted(engine_langs))
    reader = _reader_cache.get(key)
    if reader is None:
        reader = easyocr.Reader(list(key), download_enabled=download_enabled)
        _reader_cache[key] = reader
    return reader


class EasyOCREngine:
    name = "easyocr"

    def __init__(self, *, download_enabled: bool = True):
        # Desktop's Fast OCR path passes False (see
        # desktop/ocr_service_factory.py) -- Fast OCR is guaranteed
        # zero-network-calls (tested), and EasyOCR's own default of
        # silently downloading a missing model over HTTP would quietly
        # violate that guarantee the first time a model happens to be
        # absent. The CLI/Streamlit/benchmark paths keep the permissive
        # default so existing dev workflows are unaffected.
        self._download_enabled = download_enabled

    def extract(self, image: Image.Image, langs: list[str]) -> DocumentResult:
        engine_langs = [to_engine_code(lang, self.name) for lang in langs]
        reader = _get_reader(engine_langs, download_enabled=self._download_enabled)

        image_np = np.array(image.convert("RGB"))
        raw_results = reader.readtext(image_np)

        blocks: list[TextBlock] = []
        for points, text, confidence in raw_results:
            text = text.strip()
            if not text:
                continue
            blocks.append(
                TextBlock(
                    text=text,
                    confidence=float(confidence),
                    bbox=BoundingBox.from_points(points),
                )
            )

        return DocumentResult(
            text="",  # filled in by the reconstruction step in the service layer
            blocks=blocks,
            language=langs[0] if langs else None,
            engine=self.name,
            metadata={"image_size": image.size},
        )
