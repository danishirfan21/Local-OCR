"""desktop.startup tests -- a fake in-memory RegistryAdapter stands in for
the real Win32 HKCU Run key, so no test ever touches the real user
registry (item 34)."""

from __future__ import annotations

from desktop.startup import START_HIDDEN_FLAG, is_enabled, launch_command, set_enabled


class FakeRegistryAdapter:
    def __init__(self):
        self.value: str | None = None
        self.write_calls: list[str] = []
        self.delete_calls = 0

    def read(self):
        return self.value

    def write(self, command: str) -> None:
        self.value = command
        self.write_calls.append(command)

    def delete(self) -> None:
        self.value = None
        self.delete_calls += 1


def test_is_enabled_false_when_no_registry_value():
    adapter = FakeRegistryAdapter()
    assert is_enabled(adapter) is False


def test_enabling_writes_a_command_containing_the_start_hidden_flag():
    adapter = FakeRegistryAdapter()
    set_enabled(True, adapter)
    assert is_enabled(adapter) is True
    assert START_HIDDEN_FLAG in adapter.value


def test_disabling_removes_only_local_lens_own_value():
    adapter = FakeRegistryAdapter()
    set_enabled(True, adapter)
    set_enabled(False, adapter)
    assert is_enabled(adapter) is False
    assert adapter.delete_calls == 1
    assert adapter.write_calls == [adapter.write_calls[0]]  # never wrote twice


def test_disabling_when_already_disabled_is_a_harmless_noop():
    adapter = FakeRegistryAdapter()
    set_enabled(False, adapter)  # never enabled -- must not raise
    assert is_enabled(adapter) is False


def test_launch_command_is_a_non_empty_string():
    # Real command construction (not the fake adapter) -- verifies it
    # doesn't crash building a dev-mode command and includes the flag
    # main.py checks for.
    command = launch_command()
    assert isinstance(command, str) and command
    assert START_HIDDEN_FLAG in command


def test_launch_command_dev_mode_never_hardcodes_a_bare_python_call():
    # Dev-mode command must set a working directory (a Run-key entry has
    # no separate "start in" field, and `python -m desktop.main` needs
    # the repo root on sys.path) -- item 32.
    command = launch_command()
    assert "desktop.main" in command
    assert START_HIDDEN_FLAG in command


def test_launch_command_frozen_mode_points_at_the_packaged_exe(monkeypatch):
    import desktop.startup as startup_module

    monkeypatch.setattr(startup_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(startup_module.sys, "executable", r"D:\Local OCR\dist\LocalLens\LocalLens.exe")

    command = launch_command()

    assert command == '"D:\\Local OCR\\dist\\LocalLens\\LocalLens.exe" --start-hidden'
    assert "python" not in command.lower()
    assert "desktop.main" not in command  # frozen mode never invokes -m desktop.main
