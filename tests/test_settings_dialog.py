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


def test_restore_default_button_resets_shortcut(qapp):
    dialog = SettingsDialog("Ctrl+Alt+L", gemini_configured=False, parent=None)
    assert dialog.shortcut_text() == "Ctrl+Alt+L"
    dialog._restore_default_button.click()
    assert dialog.shortcut_text() == "Ctrl+Shift+Space"


def test_v6_5_toggles_default_and_round_trip(qapp):
    dialog = SettingsDialog(
        "Ctrl+Shift+Space",
        gemini_configured=True,
        start_with_windows=True,
        auto_copy_fast_result=True,
        show_result_popup=False,
        close_popup_after_copy=False,
        parent=None,
    )
    assert dialog.start_with_windows() is True
    assert dialog.auto_copy_fast_result() is True
    assert dialog.show_result_popup() is False


def test_disabling_show_popup_also_disables_and_clears_close_after_copy(qapp):
    dialog = SettingsDialog(
        "Ctrl+Shift+Space",
        gemini_configured=True,
        show_result_popup=True,
        close_popup_after_copy=True,
        parent=None,
    )
    assert dialog.close_popup_after_copy() is True
    dialog._show_popup_check.setChecked(False)
    assert dialog.close_popup_after_copy() is False
    assert not dialog._close_after_copy_check.isEnabled()


def test_scope_exclusions_are_not_present_as_widgets(qapp):
    # Item 3's explicit "do not add" list -- a lightweight guard against
    # scope creep re-appearing in a future edit, not a UI text scrape.
    dialog = SettingsDialog("Ctrl+Shift+Space", gemini_configured=False, parent=None)
    forbidden_attrs = ("_engine_combo", "_history_check", "_account_button", "_model_tuning_group")
    for attr in forbidden_attrs:
        assert not hasattr(dialog, attr)
