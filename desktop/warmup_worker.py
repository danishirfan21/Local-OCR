"""Runs EasyOCR's expensive reader construction on a background thread at
app startup, so the first real capture doesn't pay the ~10s cold-init
cost -- see desktop/ocr_service_factory.py's warmup_fast_engine() and
docs/V6_4_RESULT_UX.md's measured timings. Best-effort in the sense that a
warmup failure never crashes startup: a real capture will simply retry
the same construction (and fail the same, visible way) rather than the
app being unusable silently."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from desktop.logging_setup import get_logger
from desktop.ocr_service_factory import friendly_model_error_message, warmup_fast_engine

logger = get_logger()


class WarmupWorker(QThread):
    finished_warmup = Signal()
    failed = Signal(str)

    def run(self) -> None:
        try:
            warmup_fast_engine()
        except Exception as exc:  # noqa: BLE001 -- a capture retries this itself; startup must not crash
            message = friendly_model_error_message(exc)
            logger.warning("OCR warm-up failed: %s", message)
            self.failed.emit(message)
            return
        self.finished_warmup.emit()
