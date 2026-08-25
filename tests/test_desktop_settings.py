"""AppSettings tests -- always backed by a temp-file QSettings, never the
real user registry path (item 28's "do not touch the user's real settings
registry path during tests")."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402

from desktop.hotkey.shortcut import DEFAULT_SHORTCUT  # noqa: E402
from desktop.settings import AppSettings  # noqa: E402


def _isolated_settings(tmp_path) -> AppSettings:
    ini_path = str(tmp_path / "settings.ini")
    return AppSettings(backing=QSettings(ini_path, QSettings.Format.IniFormat))


def test_default_shortcut_is_returned_when_nothing_stored(tmp_path):
    settings = _isolated_settings(tmp_path)
    assert settings.shortcut == DEFAULT_SHORTCUT


def test_shortcut_persists_across_instances_backed_by_the_same_file(tmp_path):
    ini_path = str(tmp_path / "settings.ini")
    first = AppSettings(backing=QSettings(ini_path, QSettings.Format.IniFormat))
    first.shortcut = "Ctrl+Alt+L"

    second = AppSettings(backing=QSettings(ini_path, QSettings.Format.IniFormat))
    assert second.shortcut == "Ctrl+Alt+L"


def test_setting_writes_to_the_backing_ini_file_not_elsewhere(tmp_path):
    ini_path = tmp_path / "settings.ini"
    settings = AppSettings(backing=QSettings(str(ini_path), QSettings.Format.IniFormat))
    settings.shortcut = "Ctrl+Alt+L"
    assert ini_path.exists()
    assert "Ctrl+Alt+L" in ini_path.read_text(encoding="utf-8")


def test_v6_5_preference_defaults(tmp_path):
    settings = _isolated_settings(tmp_path)
    assert settings.start_with_windows is False
    assert settings.auto_copy_fast_result is False
    assert settings.show_result_popup is True
    assert settings.close_popup_after_copy is False


def test_v6_5_preferences_persist_across_instances_backed_by_the_same_file(tmp_path):
    ini_path = str(tmp_path / "settings.ini")
    first = AppSettings(backing=QSettings(ini_path, QSettings.Format.IniFormat))
    first.start_with_windows = True
    first.auto_copy_fast_result = True
    first.show_result_popup = False
    first.close_popup_after_copy = True

    second = AppSettings(backing=QSettings(ini_path, QSettings.Format.IniFormat))
    assert second.start_with_windows is True
    assert second.auto_copy_fast_result is True
    assert second.show_result_popup is False
    assert second.close_popup_after_copy is True
