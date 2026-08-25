"""Fullscreen translucent region-selection overlay for one monitor.

Emits signals only -- CaptureController (controller.py) owns showing,
closing, and what happens with a selection. No toolbar, no settings, no
animation: this is a snip-and-go interaction, not a mini application.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QScreen
from PySide6.QtWidgets import QWidget

from desktop.capture.geometry import PixelRect, clamp_to_bounds, is_too_small, logical_to_physical, normalize_rect

_MIN_SELECTION_PX = 10
_DIM_ALPHA = 120  # out of 255 -- reads as "dimmed", not opaque
_SELECTION_COLOR = "#2f6fed"


class CaptureOverlay(QWidget):
    selection_made = Signal(object)  # PixelRect, in overlay-local logical pixels
    cancelled = Signal()

    def __init__(self, screenshot: QPixmap, screen: QScreen, parent=None):
        super().__init__(parent)
        self.screenshot = screenshot
        self.device_pixel_ratio = screen.devicePixelRatio()
        # Global (virtual-desktop) geometry of the monitor this overlay
        # covers -- needed by result popup positioning, which (unlike
        # cropping) genuinely needs the monitor's real desktop offset,
        # including a negative one. See desktop/result/positioning.py.
        self.screen_geometry = screen.geometry()
        self._drag_start: QPoint | None = None
        self._drag_current: QPoint | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())
        self.setMouseTracking(True)

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.screenshot)

        dim_color = QColor(0, 0, 0, _DIM_ALPHA)
        if self._drag_start is None or self._drag_current is None:
            painter.fillRect(self.rect(), dim_color)
            return

        selection = QRect(self._drag_start, self._drag_current).normalized()
        # Dim everything outside the selection via four fill rects around
        # it (top/bottom/left/right strips) -- simplest correct approach
        # for an axis-aligned rectangle, no clip-region punch-out needed.
        painter.fillRect(0, 0, self.width(), selection.top(), dim_color)
        painter.fillRect(0, selection.bottom(), self.width(), self.height() - selection.bottom(), dim_color)
        painter.fillRect(0, selection.top(), selection.left(), selection.height(), dim_color)
        painter.fillRect(
            selection.right(), selection.top(), self.width() - selection.right(), selection.height(), dim_color
        )

        pen = QPen(QColor(_SELECTION_COLOR))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRect(selection)

        painter.setPen(QColor("white"))
        painter.drawText(selection.left(), max(12, selection.top() - 6), f"{selection.width()} x {selection.height()}")

    def mousePressEvent(self, event) -> None:
        self._drag_start = event.position().toPoint()
        self._drag_current = self._drag_start
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is not None:
            self._drag_current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_start is None:
            return
        end = event.position().toPoint()
        rect = normalize_rect(self._drag_start.x(), self._drag_start.y(), end.x(), end.y())
        rect = clamp_to_bounds(rect, self.width(), self.height())
        self._drag_start = None
        self._drag_current = None

        if is_too_small(rect, _MIN_SELECTION_PX):
            self.update()  # ignore accidental tiny drags/clicks -- stay open for another attempt
            return

        self.selection_made.emit(rect)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)

    def crop_physical(self, logical_rect: PixelRect) -> QPixmap:
        """Crops the stored screenshot using a logical-pixel rect (overlay
        mouse-event coordinates), converting to physical pixels first --
        see geometry.py's module docstring for why this conversion exists."""
        physical = logical_to_physical(logical_rect, self.device_pixel_ratio)
        physical = clamp_to_bounds(physical, self.screenshot.width(), self.screenshot.height())
        return self.screenshot.copy(physical.left, physical.top, physical.width, physical.height)
