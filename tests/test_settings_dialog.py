"""SettingsDialog tests -- shortcut validation UX and Gemini status text,
offscreen Qt platform, no real dialog interaction needed."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from desktop.settings_dialog import SettingsDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_starts_with_current_shortcut_and_ok_enabled(qapp):
    dialog = SettingsDialog("Ctrl+Shift+Space", gemini_configured=True, parent=None)
    assert dialog.shortcut_text() == "Ctrl+Shift+Space"
    ok_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button.isEnabled()


def test_gemini_configured_status_is_shown(qapp):
    configured = SettingsDialog("Ctrl+Shift+Space", gemini_configured=True, parent=None)
    assert configured._gemini_label.text() == "Gemini configured"

    unconfigured = SettingsDialog("Ctrl+Shift+Space", gemini_configured=False, parent=None)
    assert unconfigured._gemini_label.text() == "Gemini not configured"


def test_invalid_shortcut_disables_ok(qapp):
    dialog = SettingsDialog("Ctrl+Shift+Space", gemini_configured=False, parent=None)
    dialog._shortcut_edit.setKeySequence(QKeySequence("Space"))
    ok_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok_button.isEnabled()
    assert "modifier" in dialog._shortcut_status.text()


def test_valid_new_shortcut_re_enables_ok(qapp):
    dialog = SettingsDialog("Ctrl+Shift+Space", gemini_configured=False, parent=None)
    dialog._shortcut_edit.setKeySequence(QKeySequence("Ctrl+Alt+L"))
    ok_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_button.isEnabled()
    assert dialog.shortcut_text() == "Ctrl+Alt+L"
