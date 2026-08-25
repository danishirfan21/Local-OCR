"""Static checks on the PyInstaller spec file -- no PyInstaller invocation
happens in this test (item 46's "no PyInstaller invocation inside unit
tests"), just source-text assertions that catch an accidental regression
(e.g. someone later adding a `datas=[('.env', '.')]` entry, or a
hardcoded personal path).
"""

from __future__ import annotations

from pathlib import Path

_SPEC_PATH = Path(__file__).resolve().parent.parent / "packaging" / "local_lens.spec"


def _spec_text() -> str:
    return _SPEC_PATH.read_text(encoding="utf-8")


def test_spec_file_exists():
    assert _SPEC_PATH.exists()


def test_spec_never_bundles_env_file():
    # The spec's own comments mention ".env" (explaining why it's NOT
    # bundled) -- what actually matters is that no `datas=` entry
    # references it, so check the datas list specifically rather than a
    # blanket substring ban that would trip on the explanatory comment.
    text = _spec_text()
    datas_start = text.index("datas=")
    datas_line_end = text.index("]", datas_start)
    datas_value = text[datas_start:datas_line_end]
    assert ".env" not in datas_value


def test_spec_excludes_paddle_family():
    text = _spec_text()
    assert '"paddle"' in text
    assert '"paddleocr"' in text
    assert '"paddlex"' in text


def test_spec_uses_windowed_mode():
    text = _spec_text()
    assert "console=False" in text


def test_spec_entry_point_is_the_desktop_app_not_streamlit():
    text = _spec_text()
    assert "desktop" in text and "main.py" in text
    assert "app.py" not in text  # the Streamlit entry point must never be packaged here


def test_spec_never_hardcodes_a_specific_users_home_directory():
    text = _spec_text()
    assert "danis" not in text.lower()
    assert "c:\\users\\" not in text.lower()
    assert "%userprofile%" not in text.lower()


def test_spec_excludes_pandas_and_pyarrow_but_keeps_scipy():
    # pandas/pyarrow: proven (not guessed) to come only from streamlit,
    # never touched by the real desktop runtime path -- see
    # docs/V6_7_PORTABLE_OPTIMIZATION.md's dependency-analysis section.
    # scipy: proven to be a genuine EasyOCR runtime dependency (160
    # submodules actually imported during real inference) -- must NEVER
    # be excluded, so this test also guards against that regression.
    text = _spec_text()
    excludes_start = text.index("excludes = [")
    excludes_end = text.index("]", excludes_start)
    excludes_value = text[excludes_start:excludes_end]
    assert '"pandas"' in excludes_value
    assert '"pyarrow"' in excludes_value
    assert '"scipy"' not in excludes_value


def test_spec_references_the_generated_icon():
    text = _spec_text()
    assert "app_icon.ico" in text
    assert "icon=ICON_PATH" in text


def test_spec_references_version_metadata():
    text = _spec_text()
    assert "version_info.txt" in text
    assert "version=VERSION_FILE" in text


def test_spec_validates_release_model_dir_before_bundling():
    # The future bundled-model seam (items 18/19/24) must fail loudly on
    # an incomplete model directory, never silently ship a partial set or
    # fall through to a download.
    text = _spec_text()
    assert "LOCAL_LENS_RELEASE_MODEL_DIR" in text
    assert "raise SystemExit" in text
    assert "craft_mlt_25k.pth" in text
    assert "english_g2.pth" in text
    assert "arabic.pth" in text


def test_icon_and_version_files_actually_exist():
    icon_path = _SPEC_PATH.parent / "assets" / "app_icon.ico"
    version_path = _SPEC_PATH.parent / "version_info.txt"
    assert icon_path.is_file()
    assert version_path.is_file()
