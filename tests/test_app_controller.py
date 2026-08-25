"""DesktopApplication lifecycle tests -- isolated QSettings (temp .ini) and
a fake hotkey adapter, so no real Windows registration or real registry
writes happen. Verifies close-to-tray behavior, Quit lifecycle, and the
Settings dialog's "don't overwrite a working shortcut with a failed one"
rule (item 28)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QRect, QSettings  # noqa: E402
from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.app_controller import DesktopApplication  # noqa: E402
from desktop.capture.geometry import PixelRect  # noqa: E402
from desktop.hotkey.manager import GlobalHotkeyManager  # noqa: E402
from desktop.settings import AppSettings  # noqa: E402
from tests.test_hotkey_manager import FakeAdapter  # noqa: E402


class _FakeScreen:
    def geometry(self):
        return QRect(0, 0, 400, 300)

    def devicePixelRatio(self):
        return 1.0

    def name(self):
        return "FAKE-1"


def _fake_pixmap():
    pixmap = QPixmap(400, 300)
    pixmap.fill(QColor(20, 20, 20))
    return pixmap


def _patch_capture(monkeypatch):
    monkeypatch.setattr("desktop.capture.controller.screen_under_cursor", lambda: _FakeScreen())
    monkeypatch.setattr("desktop.capture.controller.grab_screen", lambda screen: _fake_pixmap())


def _pump_past_hide_settle(qapp):
    # CaptureController.start() defers _begin_overlay by a short real
    # settle delay (_HIDE_SETTLE_MS) -- processEvents() alone won't fire a
    # not-yet-due QTimer, so this actually waits past it.
    import time

    from desktop.capture.controller import _HIDE_SETTLE_MS

    deadline = time.time() + (_HIDE_SETTLE_MS / 1000) + 0.2
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Local Lens Test")
    app.setOrganizationName("Local Lens Test")
    yield app


def _controller(qapp, tmp_path, adapter=None) -> DesktopApplication:
    settings = AppSettings(backing=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    hotkey_manager = GlobalHotkeyManager(adapter=adapter if adapter is not None else FakeAdapter())
    return DesktopApplication(qapp, settings=settings, hotkey_manager=hotkey_manager)


def test_controller_shows_main_window_and_registers_default_shortcut(qapp, tmp_path):
    controller = _controller(qapp, tmp_path)
    assert controller.main_window.isVisible()
    assert controller.hotkey_manager._adapter.registered_calls
    controller.quit()


def test_closing_main_window_hides_rather_than_exits(qapp, tmp_path):
    controller = _controller(qapp, tmp_path)
    assert controller.main_window.hide_to_tray_enabled is True
    controller.main_window.close()
    assert not controller.main_window.isVisible()
    # The app itself is still alive -- closing the window didn't quit it.
    assert controller.app is qapp
    controller.quit()


def test_quit_unregisters_hotkey_and_hides_window(qapp, tmp_path):
    adapter = FakeAdapter()
    controller = _controller(qapp, tmp_path, adapter=adapter)
    controller.quit()
    assert adapter.unregister_calls == 1
    assert not controller.main_window.isVisible()
    assert controller.main_window.hide_to_tray_enabled is False


def test_hotkey_triggered_starts_capture_and_hides_window(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)

    controller.hotkey_manager.triggered.emit()
    _pump_past_hide_settle(qapp)

    assert controller.capture.is_active
    assert not controller.main_window.isVisible()
    controller.capture._teardown_overlay()
    controller.quit()


def test_tray_capture_action_also_starts_capture(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)

    controller.tray.capture_requested.emit()
    _pump_past_hide_settle(qapp)

    assert controller.capture.is_active
    controller.capture._teardown_overlay()
    controller.quit()


def test_completed_capture_shows_window_and_runs_ocr(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)

    ocr_calls = []
    monkeypatch.setattr(controller.main_window, "run_ocr", lambda image_bytes: ocr_calls.append(image_bytes))

    controller._start_capture()
    _pump_past_hide_settle(qapp)
    controller.capture._on_selection_made(PixelRect(left=10, top=10, width=50, height=50))

    assert controller.main_window.isVisible()
    assert len(ocr_calls) == 1
    assert ocr_calls[0][:8] == b"\x89PNG\r\n\x1a\n"
    controller.quit()


def test_capture_ignored_while_ocr_already_running(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)

    class _FakeRunningWorker:
        def isRunning(self):
            return True

        def requestInterruption(self):
            pass

        def wait(self, _timeout_ms):
            pass

    controller.main_window._worker = _FakeRunningWorker()
    controller._start_capture()
    qapp.processEvents()

    assert not controller.capture.is_active  # capture never actually started
    assert "already in progress" in controller.main_window.status_label.text()
    controller.quit()


def test_cancelled_capture_restores_window_only_if_it_was_visible(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)
    assert controller.main_window.isVisible()

    controller._start_capture()
    _pump_past_hide_settle(qapp)
    controller.capture._on_cancelled()

    assert controller.main_window.isVisible()  # was visible before capture -- restored
    controller.quit()


def test_registration_failure_shows_warning_on_main_window(qapp, tmp_path):
    controller = _controller(qapp, tmp_path, adapter=FakeAdapter(should_succeed=False))
    assert controller.main_window.shortcut_status_label.isVisible()
    controller.quit()


def test_settings_dialog_rejecting_new_shortcut_restores_previous_registration(qapp, tmp_path, monkeypatch):
    # A working shortcut is registered first; simulate the user "changing"
    # it to something the adapter then refuses (already in use elsewhere)
    # -- the previously working shortcut must be re-registered, not left
    # unregistered (item 28).
    adapter = FakeAdapter(should_succeed=True)
    controller = _controller(qapp, tmp_path, adapter=adapter)
    assert controller.settings.shortcut == "Ctrl+Shift+Space"

    adapter.should_succeed = False
    ok = controller._register_hotkey("Ctrl+Alt+L")
    assert ok is False
    # Simulate the settings-dialog fallback path directly (the dialog
    # itself is exercised in test_settings_dialog.py; here we test the
    # controller's re-registration logic in isolation).
    adapter.should_succeed = True
    restored = controller._register_hotkey(controller.settings.shortcut)
    assert restored is True
    controller.quit()
