"""desktop.runtime_context tests -- frozen/dev detection and path
resolution, no PyInstaller invocation involved (item 46)."""

from __future__ import annotations

from pathlib import Path

import desktop.runtime_context as runtime_context


def test_is_frozen_false_in_normal_test_run():
    assert runtime_context.is_frozen() is False


def test_is_frozen_true_when_sys_frozen_is_set(monkeypatch):
    monkeypatch.setattr(runtime_context.sys, "frozen", True, raising=False)
    assert runtime_context.is_frozen() is True


def test_app_base_dir_is_repo_root_in_dev_mode():
    base = runtime_context.app_base_dir()
    assert (base / "desktop" / "main.py").exists()


def test_app_base_dir_is_executable_directory_when_frozen(monkeypatch, tmp_path):
    fake_exe = tmp_path / "LocalLens.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.setattr(runtime_context.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_context.sys, "executable", str(fake_exe))
    assert runtime_context.app_base_dir() == tmp_path


def test_resource_path_uses_meipass_when_present(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_context.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert runtime_context.resource_path("icons", "tray.png") == tmp_path / "icons" / "tray.png"


def test_resource_path_falls_back_to_app_base_dir_when_not_frozen():
    result = runtime_context.resource_path("some_asset.txt")
    assert result == runtime_context.app_base_dir() / "some_asset.txt"


def test_easyocr_model_directory_never_hardcodes_a_specific_users_home():
    result = runtime_context.easyocr_model_directory()
    assert result == Path.home() / ".EasyOCR" / "model"


def test_resolve_easyocr_model_dir_falls_back_to_external_cache_when_no_bundle_exists():
    # No build has ever populated a bundled models/easyocr/ directory --
    # this is the real, current behavior of every V6.6/V6.7 build.
    result = runtime_context.resolve_easyocr_model_dir()
    assert result == runtime_context.easyocr_model_directory()


def test_resolve_easyocr_model_dir_prefers_a_bundled_directory_when_present(monkeypatch, tmp_path):
    bundled = tmp_path / "models" / "easyocr"
    bundled.mkdir(parents=True)
    monkeypatch.setattr(runtime_context, "resource_path", lambda *parts: tmp_path.joinpath(*parts))
    result = runtime_context.resolve_easyocr_model_dir()
    assert result == bundled


def test_easyocr_model_source_label_is_external_cache_when_no_bundle_exists():
    assert runtime_context.easyocr_model_source_label() == "external-cache"


def test_easyocr_model_source_label_is_bundled_when_bundle_dir_exists(monkeypatch, tmp_path):
    bundled = tmp_path / "models" / "easyocr"
    bundled.mkdir(parents=True)
    monkeypatch.setattr(runtime_context, "resource_path", lambda *parts: tmp_path.joinpath(*parts))
    assert runtime_context.easyocr_model_source_label() == "bundled"
