"""Platform-abstracted global hotkey manager.

Only imports the Windows-only adapter when actually running on Windows
(sys.platform == "win32"); on any other platform, `is_supported` is False
and `register()` reports a clear, non-crashing failure instead of raising
-- item 25's "if imported on another OS: fail gracefully or disable
global hotkey." Tests inject a fake `adapter` to exercise registration/
lifecycle logic without a real Windows message loop (item 26).
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Signal

from desktop.hotkey.shortcut import parse_shortcut


class GlobalHotkeyManager(QObject):
    triggered = Signal()
    registration_failed = Signal(str)

    def __init__(self, app=None, parent=None, adapter=None):
        super().__init__(parent)
        if adapter is not None:
            self._adapter = adapter
        elif sys.platform == "win32":
            from desktop.hotkey.win32_adapter import Win32HotkeyAdapter

            self._adapter = Win32HotkeyAdapter(app, self.triggered.emit)
        else:
            self._adapter = None

    @property
    def is_supported(self) -> bool:
        return self._adapter is not None

    def register(self, shortcut_text: str) -> bool:
        if self._adapter is None:
            self.registration_failed.emit("Global shortcuts are only supported on Windows in this build.")
            return False
        try:
            parsed = parse_shortcut(shortcut_text)
        except ValueError as exc:
            self.registration_failed.emit(str(exc))
            return False

        ok = self._adapter.register(parsed.modifiers, parsed.vk)
        if not ok:
            self.registration_failed.emit(
                f"Could not register {parsed.text} -- it may already be in use by another application. "
                "Choose another shortcut in Settings."
            )
        return ok

    def unregister(self) -> None:
        if self._adapter is not None:
            self._adapter.unregister()
