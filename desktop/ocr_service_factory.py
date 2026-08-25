"""Builds the same OCRService the CLI and Streamlit app use -- no
duplicated engine-selection logic. Desktop-specific because the CLI's
_build_fast_service is a module-private helper; this keeps the desktop UI
from reaching into local_lens.cli internals."""

from __future__ import annotations

from local_lens.engines.easyocr_engine import EasyOCREngine
from local_lens.languages import DEFAULT_LANGUAGE
from local_lens.services.ocr_service import OCRService


def build_fast_service() -> OCRService:
    table_extractor = None
    try:
        from local_lens.tables.paddle_table_extractor import TABLE_EXTRACTION_AVAILABLE, PaddleTableExtractor

        if TABLE_EXTRACTION_AVAILABLE:
            table_extractor = PaddleTableExtractor()
    except ImportError:
        pass

    return OCRService(EasyOCREngine(), table_extractor=table_extractor)


def warmup_fast_engine(lang: str = DEFAULT_LANGUAGE) -> None:
    """Forces EasyOCR's expensive reader construction to happen now rather
    than on the user's first capture. Measured on this machine: ~10s cold
    construction vs ~0.25s once warm (see docs/V6_4_RESULT_UX.md) -- the
    reader is cached at module level in local_lens.engines.easyocr_engine,
    so this only needs to run once per language set per process, not once
    per capture. Uses a tiny synthetic image rather than a real fixture so
    it has no file-path dependency."""
    from PIL import Image

    from local_lens.engines.easyocr_engine import EasyOCREngine

    EasyOCREngine().extract(Image.new("RGB", (16, 16), color="white"), [lang])
