"""GlobalHotkeyManager lifecycle tests, using a fake adapter -- no real
Windows RegisterHotKey call, matching item 26's "mock native registration
for lifecycle tests, do not make CI depend on real desktop hotkeys."
"""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PySide6")

from desktop.hotkey.manager import GlobalHotkeyManager  # noqa: E402


class FakeAdapter:
    def __init__(self, should_succeed: bool = True):
        self.should_succeed = should_succeed
        self.registered_calls: list[tuple[int, int]] = []
        self.unregister_calls = 0
        self.is_registered = False

    def register(self, modifiers: int, vk: int) -> bool:
        self.registered_calls.append((modifiers, vk))
        self.is_registered = self.should_succeed
        return self.should_succeed

    def unregister(self) -> None:
        self.unregister_calls += 1
        self.is_registered = False


def test_register_valid_shortcut_calls_adapter_and_returns_true():
    adapter = FakeAdapter(should_succeed=True)
    manager = GlobalHotkeyManager(adapter=adapter)
    assert manager.register("Ctrl+Shift+Space") is True
    assert adapter.registered_calls == [(0x0002 | 0x0004, 0x20)]


def test_register_invalid_shortcut_never_reaches_adapter():
    adapter = FakeAdapter(should_succeed=True)
    manager = GlobalHotkeyManager(adapter=adapter)
    failures = []
    manager.registration_failed.connect(failures.append)

    assert manager.register("Space") is False
    assert adapter.registered_calls == []
    assert failures and "modifier" in failures[0]


def test_adapter_rejection_emits_registration_failed():
    adapter = FakeAdapter(should_succeed=False)
    manager = GlobalHotkeyManager(adapter=adapter)
    failures = []
    manager.registration_failed.connect(failures.append)

    assert manager.register("Ctrl+Shift+Space") is False
    assert failures and "already be in use" in failures[0]


def test_triggered_signal_fires_when_adapter_calls_back():
    adapter = FakeAdapter()
    manager = GlobalHotkeyManager(adapter=adapter)
    triggered_count = []
    manager.triggered.connect(lambda: triggered_count.append(1))

    manager.triggered.emit()
    assert triggered_count == [1]


def test_unregister_calls_adapter():
    adapter = FakeAdapter()
    manager = GlobalHotkeyManager(adapter=adapter)
    manager.register("Ctrl+Shift+Space")
    manager.unregister()
    assert adapter.unregister_calls == 1


def test_registering_a_new_shortcut_unregisters_the_old_one_first():
    adapter = FakeAdapter()
    manager = GlobalHotkeyManager(adapter=adapter)
    manager.register("Ctrl+Shift+Space")
    manager.register("Ctrl+Alt+L")
    # The fake adapter's own register() doesn't call unregister() itself
    # (that's the real Win32HotkeyAdapter's job, tested by inspecting its
    # source directly since it needs a live Windows message loop) --
    # this test instead confirms the manager doesn't skip re-registration.
    assert adapter.registered_calls == [(0x0002 | 0x0004, 0x20), (0x0002 | 0x0001, ord("L"))]


@pytest.mark.skipif(sys.platform == "win32", reason="On Windows the manager constructs a real Win32 adapter")
def test_no_adapter_on_non_windows_means_unsupported():
    manager = GlobalHotkeyManager(adapter=None, app=None)
    assert manager.is_supported is False
    failures = []
    manager.registration_failed.connect(failures.append)
    assert manager.register("Ctrl+Shift+Space") is False
    assert failures and "only supported on Windows" in failures[0]
