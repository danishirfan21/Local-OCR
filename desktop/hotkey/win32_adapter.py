"""Windows-only RegisterHotKey/UnregisterHotKey + native message bridge.

Only ever imported when sys.platform == "win32" (see manager.py) -- CI
runs on ubuntu-latest, and importing this module there would fail at
`ctypes.windll` access, so nothing outside a Windows-guarded import path
may reference it.

Registers a single hotkey (id=1) with hwnd=None, which registers it
against the *calling thread's* message queue rather than any specific
window. Qt's Windows event dispatcher (QEventDispatcherWin32) pumps the
full thread message queue, so a QAbstractNativeEventFilter still sees the
resulting WM_HOTKEY message even though it isn't tied to a window handle
-- this is the standard approach for a borderless/tray-style app that
doesn't want to dedicate a window purely to catch one message.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter

_user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000  # prevents WM_HOTKEY from repeating while the key is held


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
    ]


class _HotkeyNativeEventFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id: int, on_trigger: Callable[[], None]):
        super().__init__()
        self._hotkey_id = hotkey_id
        self._on_trigger = on_trigger

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = _MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                self._on_trigger()
        return False, 0


class Win32HotkeyAdapter:
    _HOTKEY_ID = 1

    def __init__(self, app, on_trigger: Callable[[], None]):
        # The filter must be kept alive for as long as it's installed --
        # Qt does not take ownership of a QAbstractNativeEventFilter.
        self._filter = _HotkeyNativeEventFilter(self._HOTKEY_ID, on_trigger)
        app.installNativeEventFilter(self._filter)
        self._registered = False

    def register(self, modifiers: int, vk: int) -> bool:
        self.unregister()
        ok = bool(_user32.RegisterHotKey(None, self._HOTKEY_ID, modifiers | MOD_NOREPEAT, vk))
        self._registered = ok
        return ok

    def unregister(self) -> None:
        if self._registered:
            _user32.UnregisterHotKey(None, self._HOTKEY_ID)
            self._registered = False
