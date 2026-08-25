"""Runs EasyOCR's expensive reader construction on a background thread at
app startup, so the first real capture doesn't pay the ~10s cold-init
cost -- see desktop/ocr_service_factory.py's warmup_fast_engine() and
docs/V6_4_RESULT_UX.md's measured timings. Best-effort: a warmup failure
is swallowed here since a real capture will simply retry the same
construction naturally (worse latency, not broken behavior)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from desktop.ocr_service_factory import warmup_fast_engine


class WarmupWorker(QThread):
    finished_warmup = Signal()

    def run(self) -> None:
        try:
            warmup_fast_engine()
        except Exception:  # noqa: BLE001 -- best-effort; a real capture retries this itself
            pass
        self.finished_warmup.emit()
