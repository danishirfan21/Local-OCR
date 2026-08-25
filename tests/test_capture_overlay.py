"""CaptureOverlay behavior tests -- offscreen Qt platform, no real screen
capture. Mouse events are synthesized directly against the widget's
event handlers rather than through a full window-manager-driven event
loop, which is reliable under the offscreen platform and doesn't depend
on a real display."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QMouseEvent, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.capture.overlay import CaptureOverlay  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class _FakeScreen:
    def __init__(self, x=0, y=0, w=800, h=600, dpr=1.0):
        from PySide6.QtCore import QRect

        self._geometry = QRect(x, y, w, h)
        self._dpr = dpr

    def geometry(self):
        return self._geometry

    def devicePixelRatio(self):
        return self._dpr


def _screenshot(width=800, height=600, color=QColor(50, 50, 50)) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(color)
    return pixmap


def _mouse_event(event_type, pos, widget) -> QMouseEvent:
    return QMouseEvent(
        event_type,
        QPointF(pos),
        widget.mapToGlobal(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_overlay_is_frameless_translucent_and_fullscreen_on_target_monitor(qapp):
    screen = _FakeScreen(w=800, h=600)
    overlay = CaptureOverlay(_screenshot(), screen)
    assert overlay.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert overlay.geometry().width() == 800
    assert overlay.geometry().height() == 600


def test_overlay_uses_crosshair_cursor(qapp):
    overlay = CaptureOverlay(_screenshot(), _FakeScreen())
    assert overlay.cursor().shape() == Qt.CursorShape.CrossCursor


def test_drag_and_release_emits_selection_made(qapp):
    overlay = CaptureOverlay(_screenshot(), _FakeScreen())
    selections = []
    overlay.selection_made.connect(selections.append)

    overlay.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress, QPoint(10, 10), overlay))
    overlay.mouseMoveEvent(_mouse_event(QEvent.Type.MouseMove, QPoint(110, 210), overlay))
    overlay.mouseReleaseEvent(_mouse_event(QEvent.Type.MouseButtonRelease, QPoint(110, 210), overlay))

    assert len(selections) == 1
    rect = selections[0]
    assert (rect.left, rect.top, rect.width, rect.height) == (10, 10, 100, 200)


def test_reversed_drag_direction_still_normalizes_correctly(qapp):
    overlay = CaptureOverlay(_screenshot(), _FakeScreen())
    selections = []
    overlay.selection_made.connect(selections.append)

    overlay.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress, QPoint(110, 210), overlay))
    overlay.mouseReleaseEvent(_mouse_event(QEvent.Type.MouseButtonRelease, QPoint(10, 10), overlay))

    assert len(selections) == 1
    rect = selections[0]
    assert (rect.left, rect.top, rect.width, rect.height) == (10, 10, 100, 200)


def test_tiny_accidental_click_does_not_emit_selection(qapp):
    overlay = CaptureOverlay(_screenshot(), _FakeScreen())
    selections = []
    overlay.selection_made.connect(selections.append)

    overlay.mousePressEvent(_mouse_event(QEvent.Type.MouseButtonPress, QPoint(400, 300), overlay))
    overlay.mouseReleaseEvent(_mouse_event(QEvent.Type.MouseButtonRelease, QPoint(402, 301), overlay))

    assert selections == []


def test_escape_emits_cancelled(qapp):
    from PySide6.QtGui import QKeyEvent

    overlay = CaptureOverlay(_screenshot(), _FakeScreen())
    cancels = []
    overlay.cancelled.connect(lambda: cancels.append(1))

    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    overlay.keyPressEvent(event)

    assert cancels == [1]


def test_crop_physical_scales_by_device_pixel_ratio(qapp):
    from desktop.capture.geometry import PixelRect

    screen = _FakeScreen(w=800, h=600, dpr=1.25)
    screenshot = _screenshot(width=1000, height=750)  # 800*1.25, 600*1.25
    overlay = CaptureOverlay(screenshot, screen)

    cropped = overlay.crop_physical(PixelRect(left=8, top=16, width=80, height=160))
    assert cropped.width() == 100  # 80 * 1.25
    assert cropped.height() == 200  # 160 * 1.25
