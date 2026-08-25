"""Desktop UI preferences only -- QSettings-backed (Windows registry under
HKEY_CURRENT_USER\\Software\\Local Lens\\Local Lens by default). Must never
hold LOCAL_LENS_GEMINI_API_KEY or any other secret -- production Gemini
credential handling stays exactly as local_lens/deep_analysis/production.py
and local_lens/env_file.py already implement it (real env -> .env -> not
configured). This module only ever stores UI preferences: the global
shortcut today, window geometry later.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from desktop.hotkey.shortcut import DEFAULT_SHORTCUT

ORGANIZATION_NAME = "Local Lens"
APPLICATION_NAME = "Local Lens"

_SHORTCUT_KEY = "shortcut"
_START_WITH_WINDOWS_KEY = "start_with_windows"
_AUTO_COPY_KEY = "auto_copy_fast_result"
_SHOW_RESULT_POPUP_KEY = "show_result_popup"
_CLOSE_POPUP_AFTER_COPY_KEY = "close_popup_after_copy"


def _bool(value, default: bool) -> bool:
    """QSettings round-trips bools as the string 'true'/'false' on the INI
    backing used by tests, and as native bool on the real Windows registry
    backing -- normalize both here rather than at each call site."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


class AppSettings:
    """Thin wrapper so callers never touch raw QSettings keys directly.
    Accepts an explicit `backing` QSettings for tests -- pass one backed by
    a temp-file QSettings(path, QSettings.IniFormat) so tests never read or
    write the real user registry path. UI preferences only -- see module
    docstring for what must never live here."""

    def __init__(self, backing: QSettings | None = None):
        self._settings = backing if backing is not None else QSettings(ORGANIZATION_NAME, APPLICATION_NAME)

    @property
    def shortcut(self) -> str:
        value = self._settings.value(_SHORTCUT_KEY, DEFAULT_SHORTCUT)
        return str(value) if value else DEFAULT_SHORTCUT

    @shortcut.setter
    def shortcut(self, value: str) -> None:
        self._settings.setValue(_SHORTCUT_KEY, value)
        self._settings.sync()

    @property
    def start_with_windows(self) -> bool:
        return _bool(self._settings.value(_START_WITH_WINDOWS_KEY), False)

    @start_with_windows.setter
    def start_with_windows(self, value: bool) -> None:
        self._settings.setValue(_START_WITH_WINDOWS_KEY, bool(value))
        self._settings.sync()

    @property
    def auto_copy_fast_result(self) -> bool:
        return _bool(self._settings.value(_AUTO_COPY_KEY), False)

    @auto_copy_fast_result.setter
    def auto_copy_fast_result(self, value: bool) -> None:
        self._settings.setValue(_AUTO_COPY_KEY, bool(value))
        self._settings.sync()

    @property
    def show_result_popup(self) -> bool:
        return _bool(self._settings.value(_SHOW_RESULT_POPUP_KEY), True)

    @show_result_popup.setter
    def show_result_popup(self, value: bool) -> None:
        self._settings.setValue(_SHOW_RESULT_POPUP_KEY, bool(value))
        self._settings.sync()

    @property
    def close_popup_after_copy(self) -> bool:
        return _bool(self._settings.value(_CLOSE_POPUP_AFTER_COPY_KEY), False)

    @close_popup_after_copy.setter
    def close_popup_after_copy(self, value: bool) -> None:
        self._settings.setValue(_CLOSE_POPUP_AFTER_COPY_KEY, bool(value))
        self._settings.sync()
