"""Runs the production Gemini Deep Analyze request off the GUI thread --
analogous to desktop/ocr_worker.py's OCRWorker. Uses the exact same
production credential path as the CLI and Streamlit app
(LOCAL_LENS_GEMINI_API_KEY via local_lens.env_file.load_env(), never the
benchmark credential)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from local_lens.deep_analysis.base import (
    DeepAnalysisAuthError,
    DeepAnalysisError,
    DeepAnalysisRateLimited,
    DeepAnalysisTimeout,
)
from local_lens.deep_analysis.production import build_production_gemini_provider
from local_lens.env_file import load_env
from local_lens.languages import DEFAULT_LANGUAGE
from local_lens.preprocessing.image import PRESET_NONE
from local_lens.services.ocr_service import OCRService


def deep_error_message(exc: Exception) -> str:
    """Maps every documented Deep Analyze failure mode to a specific,
    honest message -- never "falling back to Fast," matching the same
    rule app.py's Streamlit UI already follows (docs/V5_GEMINI_DEEP.md)."""
    if isinstance(exc, DeepAnalysisAuthError):
        return "Gemini rejected the configured API key."
    if isinstance(exc, DeepAnalysisRateLimited):
        return "Gemini rate limit reached. Fast result is still available."
    if isinstance(exc, DeepAnalysisTimeout):
        return "Deep Analyze timed out. Your local Fast result is unaffected."
    if isinstance(exc, DeepAnalysisError):
        return f"Gemini is temporarily unavailable: {exc}"
    return f"Deep Analyze failed unexpectedly: {exc}"


class DeepWorker(QThread):
    succeeded = Signal(object)  # DocumentResult
    failed = Signal(str)

    def __init__(self, image_bytes: bytes, lang: str = DEFAULT_LANGUAGE, parent=None):
        super().__init__(parent)
        self._image_bytes = image_bytes
        self._lang = lang

    def run(self) -> None:
        provider = build_production_gemini_provider(env=load_env())
        if provider is None:
            self.failed.emit("Deep Analyze requires a Gemini API key.")
            return

        service = OCRService(provider)
        try:
            result = service.process(self._image_bytes, [self._lang], PRESET_NONE)
        except Exception as exc:  # noqa: BLE001 -- any failure must reach the UI, not crash the thread
            self.failed.emit(deep_error_message(exc))
            return
        self.succeeded.emit(result)
