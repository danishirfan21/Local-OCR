"""TrayController tests -- no requirement for real system tray integration
in headless CI (item 29); constructing it and firing its actions must
never crash even when QSystemTrayIcon.isSystemTrayAvailable() is False
under the offscreen Qt platform."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.icon import default_icon  # noqa: E402
from desktop.tray import TrayController  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_tray_constructs_without_error(qapp):
    tray = TrayController(default_icon())
    assert tray.tray_icon is not None


def test_show_returns_false_when_no_system_tray_available(qapp):
    tray = TrayController(default_icon())
    # Under the offscreen platform there is never a real tray -- this
    # proves show() reports that rather than raising.
    result = tray.show()
    assert result is False


def test_capture_open_settings_quit_actions_are_connectable(qapp):
    tray = TrayController(default_icon())
    fired = {"capture": 0, "open": 0, "settings": 0, "quit": 0}
    tray.capture_requested.connect(lambda: fired.__setitem__("capture", fired["capture"] + 1))
    tray.open_requested.connect(lambda: fired.__setitem__("open", fired["open"] + 1))
    tray.settings_requested.connect(lambda: fired.__setitem__("settings", fired["settings"] + 1))
    tray.quit_requested.connect(lambda: fired.__setitem__("quit", fired["quit"] + 1))

    tray.capture_action.trigger()
    tray.open_action.trigger()
    tray.settings_action.trigger()
    tray.quit_action.trigger()

    assert fired == {"capture": 1, "open": 1, "settings": 1, "quit": 1}


def test_menu_contains_expected_actions_in_order(qapp):
    tray = TrayController(default_icon())
    menu = tray.tray_icon.contextMenu()
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels == ["Capture", "Open Local Lens", "Settings", "Quit"]
