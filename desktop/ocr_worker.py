"""Runs OCRService.process() off the GUI thread.

EasyOCR's model construction (expensive, first call only -- see
local_lens.engines.easyocr_engine's module-level _reader_cache) happens
lazily inside process(), on this worker thread, so the GUI thread never
blocks on model load. PyTorch's own native tensor ops release the GIL
during the actual inference, so this QThread does not stall Qt's event
loop while OCR runs -- see docs/V6_DESKTOP_FRAMEWORK_DECISION.md's
"single process vs. worker process" section for the reasoning.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from desktop.ocr_service_factory import build_fast_service, friendly_model_error_message
from local_lens.languages import DEFAULT_LANGUAGE
from local_lens.preprocessing.image import PRESET_NONE


class OCRWorker(QThread):
    # `object` rather than the DocumentResult dataclass -- Qt signal type
    # registration expects Qt-known types or the generic `object` marshal
    # for arbitrary Python objects, not an arbitrary dataclass.
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, image_bytes: bytes, lang: str = DEFAULT_LANGUAGE, parent=None):
        super().__init__(parent)
        self._image_bytes = image_bytes
        self._lang = lang

    def run(self) -> None:
        try:
            service = build_fast_service()
            result = service.process(self._image_bytes, [self._lang], PRESET_NONE)
        except Exception as exc:  # noqa: BLE001 -- any engine failure must reach the UI, not crash the thread
            self.failed.emit(friendly_model_error_message(exc))
            return
        self.succeeded.emit(result)
