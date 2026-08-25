"""Orchestrates one capture: hide Local Lens windows -> grab the monitor
under the cursor -> show the selection overlay -> crop the selection ->
emit PNG bytes for Fast OCR. Reentrancy-guarded: a second capture request
while one is already active is ignored rather than stacking overlays.
"""

from __future__ import annotations

from dataclasses import dataclass

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
# this machine and Local Lens's own window leaked into a capture during
# live verification. 80ms fixed most cases; a capture fired very soon
# after app startup (main window's very first paint still settling) still
# leaked occasionally, so this was raised to 150ms during V6.4 live
# testing. This is a short, bounded settle delay, not the "arbitrary
# multi-second sleep" item 29 explicitly rules out -- still well under
# what would read as sluggish (see docs/V6_4_RESULT_UX.md's latency
# numbers).
_HIDE_SETTLE_MS = 150


@dataclass(frozen=True)
class CaptureResult:
    png_bytes: bytes
    selection_global: PixelRect  # for result-popup positioning (global desktop coordinates)
    monitor_global: PixelRect


class CaptureController(QObject):
    captured = Signal(object)  # CaptureResult
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

        origin = overlay.screen_geometry.topLeft()
        selection_global = PixelRect(
            left=rect.left + origin.x(), top=rect.top + origin.y(), width=rect.width, height=rect.height
        )
        monitor_global = PixelRect(
            left=overlay.screen_geometry.left(),
            top=overlay.screen_geometry.top(),
            width=overlay.screen_geometry.width(),
            height=overlay.screen_geometry.height(),
        )

        self._teardown_overlay()
        self.captured.emit(
            CaptureResult(
                png_bytes=qpixmap_to_png_bytes(cropped),
                selection_global=selection_global,
                monitor_global=monitor_global,
            )
        )

    def _on_cancelled(self) -> None:
        logger.info("capture cancelled")
        self._teardown_overlay()
        self.cancelled.emit()
