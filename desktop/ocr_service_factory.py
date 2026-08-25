"""Builds the same OCRService the CLI and Streamlit app use -- no
duplicated engine-selection logic. Desktop-specific because the CLI's
_build_fast_service is a module-private helper; this keeps the desktop UI
from reaching into local_lens.cli internals."""

from __future__ import annotations

from desktop.runtime_context import resolve_easyocr_model_dir
from local_lens.engines.easyocr_engine import EasyOCREngine
from local_lens.languages import DEFAULT_LANGUAGE
from local_lens.services.ocr_service import OCRService

MODEL_UNAVAILABLE_MESSAGE = (
    "Local OCR model files are unavailable. Fast OCR needs its model files "
    "downloaded once (run the desktop app in a normal development setup, or "
    "see docs/V6_5_RELEASE_READINESS.md's model strategy)."
)


def _new_fast_engine() -> EasyOCREngine:
    # download_enabled=False: Fast OCR is guaranteed zero-network-calls
    # (tested in tests/test_no_silent_network.py and
    # tests/test_app_controller.py) -- EasyOCR's own default of silently
    # downloading a missing ~300MB model set over HTTP would quietly
    # violate that guarantee. A missing model surfaces as a clear
    # FileNotFoundError instead (see friendly_model_error_message below).
    #
    # model_storage_directory resolves via desktop.runtime_context, which
    # checks a bundled models/easyocr/ resource first (no build populates
    # it yet -- see docs/V6_7_PORTABLE_OPTIMIZATION.md) and falls back to
    # the user's own ~/.EasyOCR/model cache, which is what every V6.6/V6.7
    # build actually uses today.
    return EasyOCREngine(download_enabled=False, model_storage_directory=str(resolve_easyocr_model_dir()))


def build_fast_service() -> OCRService:
    table_extractor = None
    try:
        from local_lens.tables.paddle_table_extractor import TABLE_EXTRACTION_AVAILABLE, PaddleTableExtractor

        if TABLE_EXTRACTION_AVAILABLE:
            table_extractor = PaddleTableExtractor()
    except ImportError:
        pass

    return OCRService(_new_fast_engine(), table_extractor=table_extractor)


def warmup_fast_engine(lang: str = DEFAULT_LANGUAGE) -> None:
    """Forces EasyOCR's expensive reader construction to happen now rather
    than on the user's first capture. Measured on this machine: ~10s cold
    construction vs ~0.25s once warm (see docs/V6_4_RESULT_UX.md) -- the
    reader is cached at module level in local_lens.engines.easyocr_engine,
    so this only needs to run once per language set per process, not once
    per capture. Uses a tiny synthetic image rather than a real fixture so
    it has no file-path dependency."""
    from PIL import Image

    _new_fast_engine().extract(Image.new("RGB", (16, 16), color="white"), [lang])


def friendly_model_error_message(exc: Exception) -> str:
    """EasyOCR raises a bare FileNotFoundError (with an absolute path in
    its text) when download_enabled=False and a model file is missing --
    translated here to the same user-facing copy item 35/36 specify,
    rather than surfacing a raw path/exception string in the UI."""
    if isinstance(exc, FileNotFoundError):
        return MODEL_UNAVAILABLE_MESSAGE
    return str(exc)
