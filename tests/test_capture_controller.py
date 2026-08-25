"""CaptureController tests -- mocked screen grab, no real screen capture
in CI (item 34/35). Verifies the hide -> overlay -> crop -> captured-bytes
flow and reentrancy guarding without touching QScreen.grabWindow."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.capture.controller import CaptureController  # noqa: E402
from desktop.capture.geometry import PixelRect  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class _FakeScreen:
    def __init__(self):
        self._geometry = QRect(0, 0, 400, 300)

    def geometry(self):
        return self._geometry

    def devicePixelRatio(self):
        return 1.0

    def name(self):
        return "FAKE-1"


def _fake_pixmap():
    pixmap = QPixmap(400, 300)
    pixmap.fill(QColor(20, 20, 20))
    return pixmap


def _pump(qapp, times=5):
    # CaptureController.start() schedules _begin_overlay after a short
    # real settle delay (desktop/capture/controller.py's _HIDE_SETTLE_MS)
    # -- processEvents() alone won't fire a not-yet-due QTimer, so this
    # actually waits past it rather than just draining the pending queue.
    import time

    from desktop.capture.controller import _HIDE_SETTLE_MS

    deadline = time.time() + (_HIDE_SETTLE_MS / 1000) + 0.2
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)


def test_start_hides_windows_and_creates_overlay(qapp, monkeypatch):
    monkeypatch.setattr("desktop.capture.controller.screen_under_cursor", lambda: _FakeScreen())
    monkeypatch.setattr("desktop.capture.controller.grab_screen", lambda screen: _fake_pixmap())

    hide_calls = []
    controller = CaptureController(hide_windows=lambda: hide_calls.append(1))
    controller.start()
    _pump(qapp)

    assert hide_calls == [1]
    assert controller.is_active


def test_second_start_while_active_is_ignored(qapp, monkeypatch):
    monkeypatch.setattr("desktop.capture.controller.screen_under_cursor", lambda: _FakeScreen())
    monkeypatch.setattr("desktop.capture.controller.grab_screen", lambda screen: _fake_pixmap())

    hide_calls = []
    controller = CaptureController(hide_windows=lambda: hide_calls.append(1))
    controller.start()
    _pump(qapp)
    controller.start()  # should be a no-op -- overlay already active
    _pump(qapp)

    assert hide_calls == [1]  # not called a second time
    controller._teardown_overlay()


def test_selection_emits_captured_png_bytes(qapp, monkeypatch):
    monkeypatch.setattr("desktop.capture.controller.screen_under_cursor", lambda: _FakeScreen())
    monkeypatch.setattr("desktop.capture.controller.grab_screen", lambda screen: _fake_pixmap())

    controller = CaptureController(hide_windows=lambda: None)
    controller.start()
    _pump(qapp)

    captured = []
    controller.captured.connect(captured.append)
    controller._on_selection_made(PixelRect(left=10, top=10, width=50, height=50))

    assert len(captured) == 1
    assert captured[0].png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert captured[0].selection_global == PixelRect(left=10, top=10, width=50, height=50)
    assert captured[0].monitor_global == PixelRect(left=0, top=0, width=400, height=300)
    assert not controller.is_active  # overlay torn down after a successful selection


def test_cancel_emits_cancelled_and_tears_down_overlay(qapp, monkeypatch):
    monkeypatch.setattr("desktop.capture.controller.screen_under_cursor", lambda: _FakeScreen())
    monkeypatch.setattr("desktop.capture.controller.grab_screen", lambda screen: _fake_pixmap())

    controller = CaptureController(hide_windows=lambda: None)
    controller.start()
    _pump(qapp)

    cancels = []
    controller.cancelled.connect(lambda: cancels.append(1))
    controller._on_cancelled()

    assert cancels == [1]
    assert not controller.is_active
