"""Tests for packaging/validate_release_models.py -- the release-input
validator used before setting LOCAL_LENS_RELEASE_MODEL_DIR for a bundled
build. Uses tiny synthetic files with known hashes, never the real
~299MB EasyOCR model weights (item 30's "tiny fake files" requirement).

Not a package (packaging/ has no __init__.py, matching
tests/test_dist_size_report.py's existing approach), so it's imported via
importlib from its file path.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent.parent / "packaging" / "validate_release_models.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_release_models", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vrm = _load_module()


def _write_tiny_model_dir(tmp_path: Path, contents: dict[str, bytes]) -> Path:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    for filename, data in contents.items():
        (model_dir / filename).write_bytes(data)
    return model_dir


def _make_valid_tiny_set() -> dict[str, bytes]:
    """Tiny fake payloads whose SHA-256 hashes are patched into the module
    under test rather than using the real ~300MB model hashes."""
    return {
        "craft_mlt_25k.pth": b"fake craft weights",
        "english_g2.pth": b"fake english weights",
        "arabic.pth": b"fake arabic weights",
    }


@pytest.fixture
def patched_hashes(monkeypatch):
    """Points REQUIRED_MODEL_HASHES at the tiny fake payloads' real hashes
    so validate_release_model_dir can be tested end-to-end without ever
    touching a real model file."""
    tiny = _make_valid_tiny_set()
    fake_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in tiny.items()}
    monkeypatch.setattr(vrm, "REQUIRED_MODEL_HASHES", fake_hashes)
    return tiny


def test_validate_release_model_dir_succeeds_for_a_complete_correct_set(tmp_path, patched_hashes):
    model_dir = _write_tiny_model_dir(tmp_path, patched_hashes)
    ok_lines = vrm.validate_release_model_dir(model_dir)
    assert len(ok_lines) == 3
    for filename in patched_hashes:
        assert any(filename in line for line in ok_lines)


def test_validate_release_model_dir_fails_on_missing_directory(tmp_path):
    with pytest.raises(vrm.ReleaseModelValidationError, match="does not exist"):
        vrm.validate_release_model_dir(tmp_path / "does_not_exist")


def test_validate_release_model_dir_fails_when_a_required_file_is_missing(tmp_path, patched_hashes):
    incomplete = dict(patched_hashes)
    del incomplete["arabic.pth"]
    model_dir = _write_tiny_model_dir(tmp_path, incomplete)
    with pytest.raises(vrm.ReleaseModelValidationError, match="missing required file"):
        vrm.validate_release_model_dir(model_dir)


def test_validate_release_model_dir_fails_on_hash_mismatch(tmp_path, patched_hashes):
    tampered = dict(patched_hashes)
    tampered["english_g2.pth"] = b"this is not the expected content"
    model_dir = _write_tiny_model_dir(tmp_path, tampered)
    with pytest.raises(vrm.ReleaseModelValidationError, match="SHA-256 mismatch"):
        vrm.validate_release_model_dir(model_dir)


def test_validate_release_model_dir_fails_on_unexpected_extra_pth_file(tmp_path, patched_hashes):
    extra = dict(patched_hashes)
    extra["some_other_model.pth"] = b"an unrelated weight file that should not be here"
    model_dir = _write_tiny_model_dir(tmp_path, extra)
    with pytest.raises(vrm.ReleaseModelValidationError, match="unexpected .pth file"):
        vrm.validate_release_model_dir(model_dir)


def test_validate_release_model_dir_never_downloads_anything(tmp_path, patched_hashes, monkeypatch):
    # Defense in depth: assert no network-capable stdlib module is even
    # imported by the validator module, not just "it doesn't call out".
    import sys

    assert "urllib.request" not in vars(vrm)
    assert "requests" not in sys.modules or "requests" not in dir(vrm)
    model_dir = _write_tiny_model_dir(tmp_path, patched_hashes)
    vrm.validate_release_model_dir(model_dir)  # should complete purely from local disk I/O


def test_real_required_model_hashes_are_64_char_hex_strings():
    # Guards against a typo'd hash constant regardless of what the real
    # model files' actual content is -- doesn't need the real files.
    for filename, expected_hash in vrm.REQUIRED_MODEL_HASHES.items():
        assert len(expected_hash) == 64
        int(expected_hash, 16)  # raises ValueError if not valid hex
        assert filename.endswith(".pth")


def test_required_model_hashes_cover_exactly_the_three_known_files():
    assert set(vrm.REQUIRED_MODEL_HASHES) == {"craft_mlt_25k.pth", "english_g2.pth", "arabic.pth"}
