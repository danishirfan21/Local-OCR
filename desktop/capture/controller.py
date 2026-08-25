"""Orchestrates one capture: hide Local Lens windows -> grab the monitor
under the cursor -> show the selection overlay -> crop the selection ->
emit PNG bytes for Fast OCR. Reentrancy-guarded: a second capture request
while one is already active is ignored rather than stacking overlays.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from desktop.capture.geometry import PixelRect
from desktop.capture.image_convert import qpixmap_to_png_bytes
from desktop.capture.overlay import CaptureOverlay
from desktop.capture.screen_capture import grab_screen, screen_under_cursor
from desktop.logging_setup import get_logger

logger = get_logger()

# A hidden window can still be in the current desktop compositor (DWM)
# frame for a few milliseconds after Qt's hide() call returns -- a
# zero-delay timer (one bare event-loop turn) measurably wasn't enough on
# this machine and Local Lens's own window leaked into the first capture
# during live verification. This is a short, bounded settle delay, not the
# "arbitrary multi-second sleep" item 29 explicitly rules out.
_HIDE_SETTLE_MS = 80


class CaptureController(QObject):
    captured = Signal(bytes)  # PNG bytes of the cropped selection
    cancelled = Signal()

    def __init__(self, hide_windows, parent=None):
        super().__init__(parent)
        self._hide_windows = hide_windows
        self._overlay: CaptureOverlay | None = None

    @property
    def is_active(self) -> bool:
        return self._overlay is not None

    def start(self) -> None:
        if self.is_active:
            logger.info("capture requested while already active -- ignored")
            return
        logger.info("capture requested")
        self._hide_windows()
        # A short settle delay so a just-hidden window actually stops
        # being composited before the screenshot is grabbed -- see
        # _HIDE_SETTLE_MS's comment above.
        QTimer.singleShot(_HIDE_SETTLE_MS, self._begin_overlay)

    def _begin_overlay(self) -> None:
        screen = screen_under_cursor()
        logger.info("monitor selected: %s", screen.name())
        screenshot = grab_screen(screen)

        overlay = CaptureOverlay(screenshot, screen)
        overlay.selection_made.connect(self._on_selection_made)
        overlay.cancelled.connect(self._on_cancelled)
        self._overlay = overlay
        overlay.showFullScreen()
        overlay.raise_()
        overlay.activateWindow()

    def _teardown_overlay(self) -> None:
        overlay = self._overlay
        self._overlay = None
        if overlay is not None:
            overlay.close()
            overlay.deleteLater()

    def _on_selection_made(self, rect: PixelRect) -> None:
        overlay = self._overlay
        if overlay is None:
            return
        logger.info("selection size: %sx%s", rect.width, rect.height)
        cropped = overlay.crop_physical(rect)
        self._teardown_overlay()
        self.captured.emit(qpixmap_to_png_bytes(cropped))

    def _on_cancelled(self) -> None:
        logger.info("capture cancelled")
        self._teardown_overlay()
        self.cancelled.emit()
