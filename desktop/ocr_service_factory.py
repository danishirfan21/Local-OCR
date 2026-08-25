"""Builds the same OCRService the CLI and Streamlit app use -- no
duplicated engine-selection logic. Desktop-specific because the CLI's
_build_fast_service is a module-private helper; this keeps the desktop UI
from reaching into local_lens.cli internals."""

from __future__ import annotations

from local_lens.engines.easyocr_engine import EasyOCREngine
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
