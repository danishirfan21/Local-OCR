"""ResultWindow/ContentPane state and content-presentation tests --
offscreen Qt platform, no real OCR or Gemini calls."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.result.window import ContentPane, ResultWindow  # noqa: E402
from local_lens.models import DocumentResult, TableResult  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _result(text: str, content_type: str, *, tables=None) -> DocumentResult:
    return DocumentResult(
        text=text,
        blocks=[],
        language="en",
        engine="easyocr",
        metadata={"content_type": content_type, "total_ms": 250.0},
        tables=tables or [],
        detected_scripts=["Latin"],
    )


# -- ContentPane -------------------------------------------------------


def test_plain_text_result_shown_in_text_view(qapp):
    pane = ContentPane()
    pane.set_result(_result("hello\nworld", "text"), allow_table_markdown_fallback=False)
    assert pane.stack.currentWidget() is pane.text_view
    assert pane.text_view.toPlainText() == "hello\nworld"
    assert not pane.copy_button.isHidden()
    assert pane.copy_code_button.isHidden()


def test_code_result_shown_in_readonly_monospace_view(qapp):
    pane = ContentPane()
    pane.set_result(_result("def f():\n    return 1", "code"), allow_table_markdown_fallback=False)
    assert pane.stack.currentWidget() is pane.code_view
    assert pane.code_view.toPlainText() == "def f():\n    return 1"
    assert pane.code_view.isReadOnly()
    assert not pane.copy_code_button.isHidden()


def test_table_hint_shown_when_fast_mode_has_no_structured_table(qapp):
    pane = ContentPane()
    pane.set_result(_result("a b c\n1 2 3", "table"), allow_table_markdown_fallback=False)
    # Fast mode never fabricates a table from a weak heuristic (item 16).
    assert pane.stack.currentWidget() is pane.text_view
    assert pane.copy_table_button.isHidden()


def test_real_table_result_is_rendered_in_table_view(qapp):
    table = TableResult(rows=[["A", "B"], ["1", "2"]], cells=[], markdown=None, confidence=None, bbox=None, has_header=True)
    pane = ContentPane()
    pane.set_result(_result("A B\n1 2", "table", tables=[table]), allow_table_markdown_fallback=False)
    assert pane.stack.currentWidget() is pane.table_view
    assert pane.table_view.columnCount() == 2
    assert pane.table_view.rowCount() == 1
    assert pane.table_view.item(0, 0).text() == "1"
    assert not pane.copy_table_button.isHidden()
    assert not pane.copy_markdown_button.isHidden()


def test_deep_markdown_table_fallback_is_parsed_when_allowed(qapp):
    markdown_table = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    pane = ContentPane()
    pane.set_result(_result(markdown_table, "table"), allow_table_markdown_fallback=True)
    assert pane.stack.currentWidget() is pane.table_view
    assert pane.table_view.item(0, 0).text() == "1"


# -- ResultWindow --------------------------------------------------------


def test_loading_state_shows_reading_message(qapp):
    window = ResultWindow()
    window.show_loading()
    assert "Reading selection" in window.status_label.text()
    assert not window.deep_button.isEnabled()


def test_fast_result_with_deep_available_enables_deep_button(qapp):
    window = ResultWindow()
    window.show_fast_result(_result("hi", "text"), deep_available=True)
    assert window.deep_button.isEnabled()
    assert "Read locally" in window.status_label.text()


def test_fast_result_without_deep_configured_disables_deep_button_with_hint(qapp):
    window = ResultWindow()
    window.show_fast_result(_result("hi", "text"), deep_available=False)
    assert not window.deep_button.isEnabled()
    assert "Settings" in window.deep_button.toolTip()


def test_fast_error_disables_deep_button(qapp):
    window = ResultWindow()
    window.show_fast_error("engine exploded")
    assert "engine exploded" in window.status_label.text()
    assert not window.deep_button.isEnabled()


def test_deep_loading_disables_button_and_shows_status(qapp):
    window = ResultWindow()
    window.show_fast_result(_result("hi", "text"), deep_available=True)
    window.show_deep_loading()
    assert not window.deep_button.isEnabled()
    assert "Analyzing remotely" in window.status_label.text()


def test_deep_result_adds_deep_tab_and_preserves_fast_tab(qapp):
    window = ResultWindow()
    window.show_fast_result(_result("fast text", "text"), deep_available=True)
    window.show_deep_result(_result("deep text", "text"))

    assert window.tabs.count() == 2
    assert window.fast_pane.text_view.toPlainText() == "fast text"  # untouched by Deep
    assert window.deep_pane.text_view.toPlainText() == "deep text"
    assert "Analyzed with Gemini" in window.status_label.text()
    assert window.deep_button.isEnabled()


def test_deep_error_preserves_fast_result_and_reenables_button(qapp):
    window = ResultWindow()
    window.show_fast_result(_result("fast text", "text"), deep_available=True)
    window.show_deep_loading()
    window.show_deep_error("Gemini rejected the configured API key.")

    assert window.fast_pane.text_view.toPlainText() == "fast text"  # Fast survives Deep failure
    assert "Gemini rejected" in window.status_label.text()
    assert window.deep_button.isEnabled()  # allows retry


def test_new_loading_state_clears_a_previous_deep_tab(qapp):
    window = ResultWindow()
    window.show_fast_result(_result("first", "text"), deep_available=True)
    window.show_deep_result(_result("first deep", "text"))
    assert window.tabs.count() == 2

    window.show_loading()  # a new capture replaced the previous result (item 38)
    assert window.tabs.count() == 1
    assert window.deep_pane is None


# -- clipboard / export --------------------------------------------------


def test_copy_button_copies_plain_text_to_clipboard(qapp):
    from PySide6.QtGui import QGuiApplication

    pane = ContentPane()
    pane.set_result(_result("copy me", "text"), allow_table_markdown_fallback=False)
    pane.copy_button.click()
    assert QGuiApplication.clipboard().text() == "copy me"


def test_copy_code_button_copies_code_to_clipboard(qapp):
    from PySide6.QtGui import QGuiApplication

    pane = ContentPane()
    pane.set_result(_result("x = 1", "code"), allow_table_markdown_fallback=False)
    pane.copy_code_button.click()
    assert QGuiApplication.clipboard().text() == "x = 1"


def test_copy_table_button_copies_tsv_and_markdown_button_copies_markdown(qapp):
    from PySide6.QtGui import QGuiApplication

    table = TableResult(rows=[["A", "B"], ["1", "2"]], cells=[], markdown=None, confidence=None, bbox=None, has_header=True)
    pane = ContentPane()
    pane.set_result(_result("A B\n1 2", "table", tables=[table]), allow_table_markdown_fallback=False)

    pane.copy_table_button.click()
    assert QGuiApplication.clipboard().text() == "A\tB\n1\t2"

    pane.copy_markdown_button.click()
    markdown = QGuiApplication.clipboard().text()
    assert markdown.startswith("| A | B |")
    assert "| 1 | 2 |" in markdown


def test_export_text_writes_chosen_content_to_disk(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    out_path = tmp_path / "out.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_path), "Text (*.txt)")))

    pane = ContentPane()
    pane.set_result(_result("export me", "text"), allow_table_markdown_fallback=False)
    pane._export()

    assert out_path.read_text(encoding="utf-8") == "export me"


def test_export_table_writes_csv_via_existing_export_logic(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    out_path = tmp_path / "out.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_path), "CSV (*.csv)")))

    table = TableResult(rows=[["A", "B"], ["1", "2"]], cells=[], markdown=None, confidence=None, bbox=None, has_header=True)
    pane = ContentPane()
    pane.set_result(_result("A B\n1 2", "table", tables=[table]), allow_table_markdown_fallback=False)
    pane._export()

    content = out_path.read_text(encoding="utf-8")
    assert "A" in content and "1" in content


# -- Urdu / mixed-script -------------------------------------------------


def test_mixed_urdu_english_text_is_preserved_exactly(qapp):
    mixed_text = "Order نمبر 12345 confirmed"
    pane = ContentPane()
    pane.set_result(_result(mixed_text, "text"), allow_table_markdown_fallback=False)
    assert pane.text_view.toPlainText() == mixed_text


def test_urdu_content_does_not_force_global_rtl_layout(qapp):
    from PySide6.QtCore import Qt

    pane = ContentPane()
    pane.set_result(_result("یہ اردو کا متن ہے", "text"), allow_table_markdown_fallback=False)
    # Qt's own text engine applies the Unicode bidi algorithm per-paragraph
    # inside the text widget automatically -- this only guards against
    # this codebase adding a global RightToLeft override (item 28).
    assert pane.layoutDirection() != Qt.LayoutDirection.RightToLeft
    assert pane.text_view.layoutDirection() != Qt.LayoutDirection.RightToLeft


def test_content_pane_emits_copied_signal_on_text_copy(qapp):
    pane = ContentPane()
    pane.set_result(_result("copy me", "text"), allow_table_markdown_fallback=False)
    received = []
    pane.copied.connect(lambda: received.append(1))
    pane.copy_button.click()
    assert received == [1]


def test_result_window_text_copied_fires_for_fast_and_deep_tabs(qapp):
    window = ResultWindow()
    window.show_fast_result(_result("fast text", "text"), deep_available=True)
    received = []
    window.text_copied.connect(lambda: received.append(1))

    window.fast_pane.copy_button.click()
    assert received == [1]

    window.show_deep_result(_result("deep text", "text"))
    window.deep_pane.copy_button.click()
    assert received == [1, 1]


def test_escape_hides_window_without_closing_app(qapp):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    window = ResultWindow()
    window.show()
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    window.keyPressEvent(event)
    assert not window.isVisible()
