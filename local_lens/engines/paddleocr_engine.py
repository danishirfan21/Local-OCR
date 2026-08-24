"""PaddleOCR backend.

Uses the current (paddleocr>=3.x) pipeline API: `PaddleOCR(lang=...).predict(image)`,
not the legacy `.ocr()` tuple API from older tutorials. paddlepaddle/paddleocr
are optional, heavy dependencies (see requirements-paddle.txt) -- this module
must import cleanly even when they are not installed, so the app can disable
the PaddleOCR option in the UI instead of crashing.
"""

from __future__ import annotations

from PIL import Image

from local_lens.languages import to_engine_code
from local_lens.models import BoundingBox, DocumentResult, TextBlock

try:
    from paddleocr import PaddleOCR as _PaddleOCR

    PADDLEOCR_AVAILABLE = True
except ImportError:
    _PaddleOCR = None
    PADDLEOCR_AVAILABLE = False

_pipeline_cache: dict[str, object] = {}


def _get_pipeline(engine_lang: str):
    if not PADDLEOCR_AVAILABLE:
        raise RuntimeError(
            "PaddleOCR is not installed. Install it with:\n"
            "  pip install -r requirements-paddle.txt\n"
            "See README.md for known Windows/CPU caveats."
        )

    pipeline = _pipeline_cache.get(engine_lang)
    if pipeline is None:
        # enable_mkldnn=False works around a real bug found during testing:
        # paddlepaddle 3.3.1's oneDNN/PIR CPU executor raises
        # `NotImplementedError: ConvertPirAttribute2RuntimeAttribute not
        # support [...]` inside the text detection op on CPU-only Windows
        # inference. Disabling oneDNN avoids the broken code path; it costs
        # some CPU inference speed but the pipeline is otherwise unaffected
        # (verified: same rec_texts/rec_scores/rec_polys as with it enabled
        # on hardware where it doesn't crash). Revisit once upstream fixes
        # this -- see README.md "PaddleOCR" section.
        pipeline = _PaddleOCR(lang=engine_lang, enable_mkldnn=False)
        _pipeline_cache[engine_lang] = pipeline
    return pipeline


class PaddleOCREngine:
    name = "paddleocr"

    def extract(self, image: Image.Image, langs: list[str]) -> DocumentResult:
        import numpy as np

        engine_lang = to_engine_code(langs[0] if langs else "en", self.name)
        pipeline = _get_pipeline(engine_lang)

        image_np = np.array(image.convert("RGB"))
        raw_results = pipeline.predict(image_np)

        blocks: list[TextBlock] = []
        for page in raw_results:
            texts = page.get("rec_texts", [])
            scores = page.get("rec_scores", [])
            polys = page.get("rec_polys", page.get("dt_polys", []))
            for i, text in enumerate(texts):
                text = (text or "").strip()
                if not text:
                    continue
                confidence = float(scores[i]) if i < len(scores) else None
                bbox = None
                if i < len(polys):
                    points = [(float(p[0]), float(p[1])) for p in polys[i]]
                    bbox = BoundingBox.from_points(points)
                blocks.append(TextBlock(text=text, confidence=confidence, bbox=bbox))

        return DocumentResult(
            text="",
            blocks=blocks,
            language=langs[0] if langs else None,
            engine=self.name,
            metadata={"image_size": image.size},
        )
