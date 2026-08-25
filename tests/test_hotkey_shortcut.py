"""Pure shortcut-parsing tests -- no Windows API, no real hotkey
registration. See desktop/hotkey/shortcut.py."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from desktop.hotkey.shortcut import (  # noqa: E402
    DEFAULT_SHORTCUT,
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    is_supported,
    parse_shortcut,
)


def test_ctrl_shift_space_parses_to_expected_flags_and_vk():
    parsed = parse_shortcut("Ctrl+Shift+Space")
    assert parsed.modifiers == MOD_CONTROL | MOD_SHIFT
    assert parsed.vk == 0x20  # VK_SPACE


def test_ctrl_alt_l_parses_to_expected_flags_and_vk():
    parsed = parse_shortcut("Ctrl+Alt+L")
    assert parsed.modifiers == MOD_CONTROL | MOD_ALT
    assert parsed.vk == ord("L")


def test_alt_shift_l_parses_to_expected_flags_and_vk():
    parsed = parse_shortcut("Alt+Shift+L")
    assert parsed.modifiers == MOD_ALT | MOD_SHIFT
    assert parsed.vk == ord("L")


def test_function_key_maps_to_correct_vk():
    parsed = parse_shortcut("Ctrl+F5")
    assert parsed.vk == 0x70 + 4  # VK_F1 + 4 == VK_F5


def test_digit_key_maps_to_correct_vk():
    parsed = parse_shortcut("Ctrl+Shift+7")
    assert parsed.vk == ord("7")


def test_win_modifier_is_recognized():
    parsed = parse_shortcut("Meta+Shift+L")
    assert parsed.modifiers & MOD_WIN


def test_empty_string_is_rejected():
    with pytest.raises(ValueError):
        parse_shortcut("")


def test_bare_key_without_modifier_is_rejected():
    with pytest.raises(ValueError, match="modifier"):
        parse_shortcut("Space")


def test_unparseable_text_is_rejected():
    with pytest.raises(ValueError):
        parse_shortcut("not a real shortcut !!")


def test_multi_key_chord_is_rejected():
    with pytest.raises(ValueError, match="single key combination"):
        parse_shortcut("Ctrl+K, Ctrl+S")


def test_default_shortcut_is_itself_valid():
    assert is_supported(DEFAULT_SHORTCUT)


def test_is_supported_returns_false_for_invalid_input_without_raising():
    assert is_supported("") is False
    assert is_supported("Space") is False
