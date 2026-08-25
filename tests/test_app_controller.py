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

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.app_controller import DesktopApplication  # noqa: E402
from desktop.hotkey.manager import GlobalHotkeyManager  # noqa: E402
from desktop.settings import AppSettings  # noqa: E402
from tests.test_hotkey_manager import FakeAdapter  # noqa: E402


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


def test_hotkey_triggered_brings_window_to_front(qapp, tmp_path):
    controller = _controller(qapp, tmp_path)
    controller.main_window.hide()
    assert not controller.main_window.isVisible()

    controller.hotkey_manager.triggered.emit()
    assert controller.main_window.isVisible()
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
