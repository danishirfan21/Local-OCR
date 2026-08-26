"""MainWindow V6.5 additions -- Capture Now signal, readiness/shortcut/Deep
status display. Offscreen Qt platform, no real OCR."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_capture_button_emits_capture_requested(qapp):
    window = MainWindow()
    received = []
    window.capture_requested.connect(lambda: received.append(1))
    window.capture_button.click()
    assert received == [1]


def test_set_shortcut_display_shows_the_shortcut_text(qapp):
    window = MainWindow()
    window.set_shortcut_display("Ctrl+Shift+Space")
    assert "Ctrl+Shift+Space" in window.shortcut_label.text()


def test_set_readiness_updates_label(qapp):
    window = MainWindow()
    assert "Starting" in window.readiness_label.text()
    window.set_readiness("Fast OCR ready")
    assert window.readiness_label.text() == "Fast OCR ready"


def test_set_deep_status_reflects_configuration(qapp):
    window = MainWindow()
    window.set_deep_status(True)
    assert "configured" in window.deep_status_label.text().lower()
    assert "not configured" not in window.deep_status_label.text().lower()


def test_window_icon_is_not_the_generic_qt_default(qapp):
    # V6.9 RC QA finding: the frozen EXE/Explorer/taskbar icon was correct,
    # but neither window ever called setWindowIcon(), so Qt's own default
    # (a null/empty QIcon) showed in the title bar instead of the branded
    # icon. Guards against the fix regressing silently.
    window = MainWindow()
    assert not window.windowIcon().isNull()

    window.set_deep_status(False)
    assert "not configured" in window.deep_status_label.text().lower()
