"""PaddleOCR-VL production adapter (Deep Analyze mode only).

Wraps `paddleocr.PaddleOCRVL`, the ~0.9B-parameter local vision-language
document-parsing pipeline validated in `experiments/paddleocr_vl/` during
V3. This module implements the same `OCREngine` protocol as
`easyocr_engine.py`/`paddleocr_engine.py` so it slots into `OCRService`
without special-casing -- but it is deliberately never imported by the
Fast-mode code path (see app.py's mode switch and
routing/engine_router.py, which only ever returns "easyocr"/"paddleocr").

Result field names (`page["parsing_res_list"]`, each item's `.content`/
`.label`/`.bbox`) were confirmed empirically against real runs during the
V3 audit and V4 implementation, not assumed from documentation.

Extreme-aspect-ratio mitigation: the V3 audit root-caused a real
PaddleOCR-VL recognition-stage failure -- it returns empty `.content` for
extremely elongated single-line crops (~31:1 aspect ratio) even though
layout detection correctly finds the region. `experiments/paddleocr_vl/
aspect_ratio_experiment.py` measured where this begins. Rather than
inventing tiling/stitching logic, this module falls back to a fast OCR
engine (EasyOCR by default) for any block that comes back empty despite
having a plausible bbox -- the task's own guidance calls this "the safest
V4 implementation," and it reuses the existing engine abstraction instead
of adding a new recognition strategy.
"""

from __future__ import annotations

from PIL import Image

from local_lens.engines.base import OCREngine
from local_lens.models import BoundingBox, DocumentBlock, DocumentResult, TableResult, TextBlock
from local_lens.tables.paddle_table_extractor import _cells_to_rows, _parse_html_table

try:
    from paddleocr import PaddleOCRVL as _PaddleOCRVL

    PADDLEOCR_VL_AVAILABLE = True
except ImportError:
    _PaddleOCRVL = None
    PADDLEOCR_VL_AVAILABLE = False

_pipeline_cache: dict[str, object] = {}

# Minimum bbox area (px^2) below which an "empty content" block is treated
# as genuinely empty (e.g. whitespace/decoration) rather than a failed
# recognition worth falling back on -- avoids wastefully re-OCRing tiny
# specks. Not the aspect-ratio threshold itself (empty-content is the
# primary, more robust trigger; see module docstring).
_MIN_FALLBACK_BBOX_AREA = 200


def _get_pipeline():
    if not PADDLEOCR_VL_AVAILABLE:
        raise RuntimeError(
            "PaddleOCR-VL is not installed. Install optional deep-analysis "
            "dependencies with:\n"
            "  pip install -r requirements-paddle.txt\n"
            '  pip install "paddlex[ocr]==<paddlex version>"\n'
            "See README.md 'Deep Analyze' section for details."
        )

    pipeline = _pipeline_cache.get("default")
    if pipeline is None:
        pipeline = _PaddleOCRVL(pipeline_version="v1.6")
        _pipeline_cache["default"] = pipeline
    return pipeline


def _bbox_from_coords(coords) -> BoundingBox | None:
    if not coords or len(coords) < 4:
        return None
    x1, y1, x2, y2 = coords[0], coords[1], coords[2], coords[3]
    return BoundingBox(
        left=int(round(x1)), top=int(round(y1)),
        width=int(round(x2 - x1)), height=int(round(y2 - y1)),
    )


class PaddleOCRVLEngine:
    name = "paddleocr_vl"

    def __init__(self, fallback_engine: OCREngine | None = None):
        # Lazily constructed on first actual fallback use, not at __init__
        # time, so simply selecting Deep Analyze doesn't also pay EasyOCR's
        # ~60s cold-load cost up front.
        self._fallback_engine = fallback_engine
        self._fallback_default_built = False

    def _fallback(self) -> OCREngine:
        if self._fallback_engine is None and not self._fallback_default_built:
            from local_lens.engines.easyocr_engine import EasyOCREngine

            self._fallback_engine = EasyOCREngine()
            self._fallback_default_built = True
        return self._fallback_engine

    def extract(self, image: Image.Image, langs: list[str]) -> DocumentResult:
        import numpy as np

        pipeline = _get_pipeline()
        rgb_image = image.convert("RGB")
        image_np = np.array(rgb_image)
        raw_results = pipeline.predict(image_np)

        blocks: list[TextBlock] = []
        document_blocks: list[DocumentBlock] = []
        tables: list[TableResult] = []
        fallback_used_for: list[str] = []

        for page in raw_results:
            for item in page.get("parsing_res_list") or []:
                label = getattr(item, "label", "text") or "text"
                content = (getattr(item, "content", "") or "").strip()
                bbox = _bbox_from_coords(getattr(item, "bbox", None))

                if not content and bbox is not None and bbox.width * bbox.height >= _MIN_FALLBACK_BBOX_AREA:
                    content = self._fallback_ocr_region(rgb_image, bbox)
                    if content:
                        fallback_used_for.append(label)

                block_type = _label_to_block_type(label)
                document_blocks.append(
                    DocumentBlock(type=block_type, text=content, bbox=bbox, metadata={"label": label})
                )

                if content:
                    blocks.append(TextBlock(text=content, confidence=None, bbox=bbox))

                if block_type == "table" and "<table" in content.lower():
                    cells, header_detected = _parse_html_table(content)
                    if cells:
                        tables.append(
                            TableResult(
                                rows=_cells_to_rows(cells),
                                cells=cells,
                                markdown=None,
                                confidence=None,
                                bbox=bbox,
                                has_header=header_detected,
                            )
                        )

        return DocumentResult(
            text="",
            blocks=blocks,
            language=langs[0] if langs else None,
            engine=self.name,
            metadata={
                "image_size": image.size,
                "fallback_used_for_blocks": fallback_used_for,
            },
            tables=tables,
            document_blocks=document_blocks,
        )

    def _fallback_ocr_region(self, image: Image.Image, bbox: BoundingBox) -> str:
        crop = image.crop((bbox.left, bbox.top, bbox.right, bbox.bottom))
        if crop.width < 2 or crop.height < 2:
            return ""
        try:
            result = self._fallback().extract(crop, ["en"])
        except Exception:
            return ""
        from local_lens.reconstruction import reconstruct_text

        return reconstruct_text(result.blocks)


def _label_to_block_type(label: str) -> str:
    label = label.lower()
    if label in ("table",):
        return "table"
    if label in ("title", "heading", "header"):
        return "title"
    if label in ("formula", "equation"):
        return "formula"
    if label in ("image", "figure", "chart"):
        return "image"
    if label in ("text", "paragraph"):
        return "text"
    return "unknown"
