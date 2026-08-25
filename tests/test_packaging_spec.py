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
