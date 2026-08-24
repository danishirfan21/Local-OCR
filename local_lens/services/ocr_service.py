"""Top-level orchestration: preprocess -> engine -> reading order -> classify.

This is the single entry point the UI (or a future CLI/API) should call.
It has no Streamlit dependency, so it works the same way in a notebook, a
test, or a web server.
"""

from __future__ import annotations

import io

from PIL import Image

from local_lens.classification import classify
from local_lens.engines.base import OCREngine
from local_lens.models import DocumentResult
from local_lens.preprocessing.image import PRESET_NONE, apply_preset
from local_lens.reconstruction import reconstruct_text


class OCRService:
    def __init__(self, engine: OCREngine):
        self.engine = engine

    def process(
        self,
        image_bytes: bytes,
        langs: list[str],
        preprocessing: str = PRESET_NONE,
    ) -> DocumentResult:
        original = Image.open(io.BytesIO(image_bytes))
        processed = apply_preset(original, preprocessing)

        result = self.engine.extract(processed, langs)
        result.text = reconstruct_text(result.blocks)

        content_type, confidence = classify(result.text)
        result.metadata.update(
            {
                "preprocessing": preprocessing,
                "content_type": content_type.value,
                "content_type_confidence": confidence,
                "block_count": len(result.blocks),
            }
        )
        return result
