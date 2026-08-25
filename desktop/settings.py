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


class AppSettings:
    """Thin wrapper so callers never touch raw QSettings keys directly.
    Accepts an explicit `backing` QSettings for tests -- pass one backed by
    a temp-file QSettings(path, QSettings.IniFormat) so tests never read or
    write the real user registry path."""

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
