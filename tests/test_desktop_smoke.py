"""Lightweight PySide6 smoke coverage for the desktop shell (V6.1).

Runs under Qt's offscreen platform plugin (no real window surface needed,
works in headless CI/dev environments). Deliberately never starts a real
OCRWorker thread -- that would run real EasyOCR (slow, matches the
project's existing "no heavy local inference in unit tests" convention
already used for tests/test_app_smoke.py). Instead this exercises the
Qt shell and the succeeded/failed signal handlers directly with fake
DocumentResult data.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

# PySide6 is an optional `desktop` extra (pyproject.toml), deliberately not
# in requirements.txt -- CI installs only the lightweight stack, matching
# this project's "no heavyweight deps in default CI" convention. Skip
# cleanly rather than failing collection when it isn't installed.
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.main_window import MainWindow, format_result_summary  # noqa: E402
from local_lens.models import DocumentResult  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _fake_result(text: str = "hello world") -> DocumentResult:
    return DocumentResult(
        text=text,
        blocks=[],
        language="en",
        engine="easyocr",
        metadata={"content_type": "text", "total_ms": 123.4},
        detected_scripts=["Latin"],
    )


def test_main_window_constructs_without_error(qapp):
    window = MainWindow()
    assert window.windowTitle() == "Local Lens"
    assert not window.copy_button.isEnabled()


def test_ocr_succeeded_populates_result_and_enables_copy(qapp):
    window = MainWindow()
    window._on_ocr_succeeded(_fake_result("extracted text"))
    assert window.result_view.toPlainText() == "extracted text"
    assert window.copy_button.isEnabled()
    assert "easyocr" in window.status_label.text()


def test_ocr_succeeded_with_empty_text_keeps_copy_disabled(qapp):
    window = MainWindow()
    window._on_ocr_succeeded(_fake_result(""))
    assert not window.copy_button.isEnabled()


def test_ocr_failed_shows_error_and_does_not_crash(qapp):
    window = MainWindow()
    window._on_ocr_failed("engine exploded")
    assert "engine exploded" in window.status_label.text()
    assert not window.copy_button.isEnabled()


def test_copy_with_no_result_is_a_no_op(qapp):
    window = MainWindow()
    window.copy_result_text()  # must not raise despite no result yet


def test_format_result_summary_includes_engine_content_type_and_scripts():
    summary = format_result_summary(_fake_result())
    assert "easyocr" in summary
    assert "text" in summary
    assert "Latin" in summary
