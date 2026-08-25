"""Start Local Lens with Windows -- a user-level HKCU Run key entry
(item 4). Deliberately not HKLM and never requires Administrator: HKCU
Run entries are per-user, writable without elevation, and are the
standard mechanism Windows itself documents for this.

Platform-specific registry access is isolated behind RegistryAdapter so
the enable/disable/is_enabled policy (this module's real content) can be
unit tested with a fake in-memory adapter -- no test ever touches the
real user registry, matching the pattern already used for the global
hotkey (desktop/hotkey/win32_adapter.py).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

from desktop.runtime_context import is_frozen

_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "LocalLens"

START_HIDDEN_FLAG = "--start-hidden"


class RegistryAdapter(Protocol):
    def read(self) -> str | None: ...
    def write(self, command: str) -> None: ...
    def delete(self) -> None: ...


class Win32RunKeyAdapter:
    """Real HKCU\\...\\Run adapter. Only imports winreg lazily so this
    module stays importable (for tests) on non-Windows platforms."""

    def read(self) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
                return str(value)
        except FileNotFoundError:
            return None

    def write(self, command: str) -> None:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, command)

    def delete(self) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_WRITE) as key:
                winreg.DeleteValue(key, _VALUE_NAME)
        except FileNotFoundError:
            pass


def _pythonw_path(python_exe: str) -> str:
    """Prefer pythonw.exe over python.exe for the startup launch so no
    console window flashes on login (item 5) -- falls back to python.exe
    if a pythonw.exe sibling doesn't exist (e.g. some venvs)."""
    candidate = Path(python_exe).with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else python_exe


def launch_command() -> str:
    """The command written to the Run key. Handles both a packaged
    (frozen) executable and Python-module development launches (items
    32/33) -- never hardcodes a user-facing repo path beyond what a dev
    checkout inherently requires, and never requires Administrator."""
    if is_frozen():
        return f'"{sys.executable}" {START_HIDDEN_FLAG}'

    repo_root = Path(__file__).resolve().parent.parent
    pythonw = _pythonw_path(sys.executable)
    # `cmd /c cd /d ... &&` sets the working directory for the module
    # launch -- Run-key entries don't otherwise let you specify a start
    # directory, and `python -m desktop.main` needs repo_root on the
    # import path.
    return f'cmd /c cd /d "{repo_root}" && "{pythonw}" -m desktop.main {START_HIDDEN_FLAG}'


def is_enabled(adapter: RegistryAdapter | None = None) -> bool:
    adapter = adapter if adapter is not None else Win32RunKeyAdapter()
    return adapter.read() is not None


def set_enabled(enabled: bool, adapter: RegistryAdapter | None = None) -> None:
    adapter = adapter if adapter is not None else Win32RunKeyAdapter()
    if enabled:
        adapter.write(launch_command())
    else:
        # Only ever removes Local Lens's own value -- never touches any
        # other entry under the Run key (item 5).
        adapter.delete()
