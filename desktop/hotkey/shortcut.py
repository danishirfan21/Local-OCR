"""Pure shortcut-text <-> Win32 RegisterHotKey parameter mapping.

No ctypes, no platform check -- this module is plain parsing logic and is
unit-tested directly (see tests/test_hotkey_shortcut.py). The only
PySide6 dependency is QKeySequence/Qt, used purely for parsing a shortcut
string like "Ctrl+Shift+Space" into a key + modifier set; it does not
touch any native Windows API.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

# Win32 RegisterHotKey modifier flags (winuser.h) -- plain integers, not
# ctypes constants, so this module has no Windows-only import.
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

DEFAULT_SHORTCUT = "Ctrl+Shift+Space"

_MAX_F_KEY = 24  # VK_F1..VK_F24 is the full range Windows defines


@dataclass(frozen=True)
class ParsedShortcut:
    modifiers: int
    vk: int
    text: str  # canonical (QKeySequence-normalized) representation


def _key_to_vk(key: int) -> int | None:
    """Maps a Qt.Key to the Win32 virtual-key code RegisterHotKey expects.
    Only covers letters, digits, Space, and F1-F24 -- deliberately not a
    speculative full keyboard map; anything else is rejected rather than
    guessed at."""
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return key  # Qt.Key_A..Z and VK_A..Z both equal ord('A')..ord('Z')
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return key  # same coincidence for digits
    if key == Qt.Key.Key_Space:
        return 0x20  # VK_SPACE
    if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F1 + (_MAX_F_KEY - 1):
        return 0x70 + (key - Qt.Key.Key_F1)  # VK_F1 == 0x70, sequential
    return None


def parse_shortcut(text: str) -> ParsedShortcut:
    """Raises ValueError with a user-facing message on anything unsupported:
    empty input, unparseable text, a multi-key chord (RegisterHotKey only
    supports a single combination), no modifier (required so a global
    hotkey can never silently steal plain typing), or a key outside the
    supported set."""
    text = (text or "").strip()
    if not text:
        raise ValueError("No shortcut given.")

    seq = QKeySequence(text)
    if seq.count() == 0:
        raise ValueError(f"'{text}' is not a recognized key sequence.")
    if seq.count() > 1:
        raise ValueError("Only a single key combination is supported (no multi-key chords).")

    combo = seq[0]
    key = combo.key().value if hasattr(combo.key(), "value") else int(combo.key())
    qt_mods = combo.keyboardModifiers()

    modifiers = 0
    if qt_mods & Qt.KeyboardModifier.ControlModifier:
        modifiers |= MOD_CONTROL
    if qt_mods & Qt.KeyboardModifier.AltModifier:
        modifiers |= MOD_ALT
    if qt_mods & Qt.KeyboardModifier.ShiftModifier:
        modifiers |= MOD_SHIFT
    if qt_mods & Qt.KeyboardModifier.MetaModifier:
        modifiers |= MOD_WIN

    if modifiers == 0:
        raise ValueError("A global shortcut needs at least one modifier key (Ctrl, Alt, Shift, or Win).")

    vk = _key_to_vk(key)
    if vk is None:
        raise ValueError(f"'{text}' uses a key that isn't supported for global shortcuts yet.")

    return ParsedShortcut(modifiers=modifiers, vk=vk, text=seq.toString(QKeySequence.SequenceFormat.PortableText))


def is_supported(text: str) -> bool:
    try:
        parse_shortcut(text)
    except ValueError:
        return False
    return True
