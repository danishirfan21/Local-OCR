"""Compact result popup shown after a capture (V6.4) -- the flagship
capture -> result path no longer routes through MainWindow at all.

Content-aware but not content-type-specialized into separate windows:
ContentPane is one reusable widget that renders text, code, or a table
(with content-appropriate Copy/Save actions), used for both the Fast and
Deep tabs of ResultWindow. No engine jargon in user-visible text -- "Read
locally" / "Analyzed with Gemini", never "EasyOCR"/model names.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from local_lens.deep_analysis.deep_metrics import parse_markdown_table
from local_lens.export import export_table_csv, export_table_markdown, to_markdown
from local_lens.models import DocumentResult, TableResult


def _format_timing_suffix(result: DocumentResult) -> str:
    total_ms = result.metadata.get("total_ms")
    if not isinstance(total_ms, (int, float)):
        return ""
    return f"  ·  {total_ms / 1000:.1f}s"


class ContentPane(QWidget):
    """One content-aware view: plain text (editable/selectable), code
    (read-only, monospace, no reformatting), or a table (Qt table view +
    Copy Table/Markdown/Save CSV) -- picked from the result's classified
    content_type, never a separate widget tree per type."""

    copied = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: DocumentResult | None = None
        self._table_result: TableResult | None = None

        self.text_view = QPlainTextEdit()
        self.text_view.setPlaceholderText("Extracted text will appear here.")

        self.code_view = QPlainTextEdit()
        self.code_view.setReadOnly(True)
        self.code_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.code_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        self.table_view = QTableWidget()
        self.table_view.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.table_hint_label = QLabel()
        self.table_hint_label.setWordWrap(True)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.text_view)
        self.stack.addWidget(self.code_view)
        self.stack.addWidget(self.table_view)
        self.stack.addWidget(self.table_hint_label)

        self.copy_button = QPushButton("Copy")
        self.copy_code_button = QPushButton("Copy Code")
        self.copy_table_button = QPushButton("Copy Table")
        self.copy_markdown_button = QPushButton("Copy Markdown")
        self.export_button = QPushButton("Save")

        self.copy_button.clicked.connect(lambda: self._copy_to_clipboard(self.text_view.toPlainText()))
        self.copy_code_button.clicked.connect(lambda: self._copy_to_clipboard(self.code_view.toPlainText()))
        self.copy_table_button.clicked.connect(self._copy_table_as_tsv)
        self.copy_markdown_button.clicked.connect(self._copy_table_as_markdown)
        self.export_button.clicked.connect(self._export)

        button_row = QHBoxLayout()
        for button in (
            self.copy_button,
            self.copy_code_button,
            self.copy_table_button,
            self.copy_markdown_button,
            self.export_button,
        ):
            button_row.addWidget(button)
        button_row.addStretch(1)

        layout = QVBoxLayout()
        layout.addWidget(self.stack, stretch=1)
        layout.addLayout(button_row)
        self.setLayout(layout)

        self.show_placeholder()

    def show_placeholder(self) -> None:
        self._result = None
        self._table_result = None
        self.text_view.setPlainText("")
        self.stack.setCurrentWidget(self.text_view)
        self._set_visible_buttons(text=True)

    def set_result(self, result: DocumentResult, *, allow_table_markdown_fallback: bool) -> None:
        self._result = result
        content_type = result.metadata.get("content_type", "text")

        if content_type == "code":
            self.code_view.setPlainText(result.text)
            self.stack.setCurrentWidget(self.code_view)
            self._set_visible_buttons(code=True)
            return

        if content_type == "table":
            table = self._resolve_table(result, allow_table_markdown_fallback)
            if table is not None:
                self._table_result = table
                self._populate_table(table)
                self.stack.setCurrentWidget(self.table_view)
                self._set_visible_buttons(table=True)
                return
            # No reliable structured table -- never fabricate rows from a
            # weak heuristic (item 16). Show the plain text with a hint.
            self.table_hint_label.setText(
                "Table-like content detected. Deep Analyze can often "
                "preserve rows and columns better than Fast OCR."
            )
            self.text_view.setPlainText(result.text)
            self.stack.setCurrentWidget(self.text_view)
            self._set_visible_buttons(text=True)
            return

        self.text_view.setPlainText(result.text)
        self.stack.setCurrentWidget(self.text_view)
        self._set_visible_buttons(text=True)

    @staticmethod
    def _resolve_table(result: DocumentResult, allow_markdown_fallback: bool) -> TableResult | None:
        if result.tables:
            return result.tables[0]
        if not allow_markdown_fallback:
            return None
        rows = parse_markdown_table(result.text)
        if not rows:
            return None
        return TableResult(rows=rows, cells=[], markdown=None, confidence=None, bbox=None, has_header=True)

    def _populate_table(self, table: TableResult) -> None:
        self.table_view.clear()
        rows = table.rows
        if not rows:
            self.table_view.setRowCount(0)
            self.table_view.setColumnCount(0)
            return
        header = rows[0] if table.has_header else [f"Column {i + 1}" for i in range(len(rows[0]))]
        body = rows[1:] if table.has_header else rows
        self.table_view.setColumnCount(len(header))
        self.table_view.setHorizontalHeaderLabels(header)
        self.table_view.setRowCount(len(body))
        for r, row in enumerate(body):
            for c, cell in enumerate(row):
                self.table_view.setItem(r, c, QTableWidgetItem(cell))

    def _set_visible_buttons(self, *, text: bool = False, code: bool = False, table: bool = False) -> None:
        self.copy_button.setVisible(text)
        self.copy_code_button.setVisible(code)
        self.copy_table_button.setVisible(table)
        self.copy_markdown_button.setVisible(table)
        self.export_button.setVisible(text or code or table)

    def _copy_to_clipboard(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.copied.emit()

    def _copy_table_as_tsv(self) -> None:
        if self._table_result is None:
            return
        self._copy_to_clipboard("\n".join("\t".join(row) for row in self._table_result.rows))

    def _copy_table_as_markdown(self) -> None:
        if self._table_result is None:
            return
        self._copy_to_clipboard(export_table_markdown(self._table_result))

    def _export(self) -> None:
        if self._result is None:
            return
        if self.stack.currentWidget() is self.table_view and self._table_result is not None:
            path, chosen_filter = QFileDialog.getSaveFileName(self, "Save Table", "", "CSV (*.csv);;Markdown (*.md)")
            if not path:
                return
            content = export_table_csv(self._table_result) if chosen_filter.startswith("CSV") else export_table_markdown(self._table_result)
        else:
            path, chosen_filter = QFileDialog.getSaveFileName(self, "Save Text", "", "Text (*.txt);;Markdown (*.md)")
            if not path:
                return
            content = self._result.text if chosen_filter.startswith("Text") else to_markdown(self._result)
        Path(path).write_text(content, encoding="utf-8")


class ResultWindow(QWidget):
    """The primary post-capture surface -- compact, keyboard-friendly,
    reused across captures (item 38: one active popup, not a stack of
    windows). Deep Analyze consent/request policy lives in the app
    controller, not here -- this widget only emits deep_requested and
    exposes show_* state transitions."""

    deep_requested = Signal()
    text_copied = Signal()  # any Copy/Copy Code/Copy Table/Copy Markdown click, either tab

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Local Lens")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(440, 320)

        self.status_label = QLabel("Reading selection…")
        self.status_label.setWordWrap(True)

        self.tabs = QTabWidget()
        self.fast_pane = ContentPane()
        self.fast_pane.copied.connect(self.text_copied)
        self.tabs.addTab(self.fast_pane, "Fast")
        self.deep_pane: ContentPane | None = None

        self.deep_button = QPushButton("Deep Analyze ✨")
        self.deep_button.clicked.connect(self.deep_requested)
        self.deep_button.setEnabled(False)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        bottom_row.addWidget(self.deep_button)

        layout = QVBoxLayout()
        layout.addWidget(self.status_label)
        layout.addWidget(self.tabs, stretch=1)
        layout.addLayout(bottom_row)
        self.setLayout(layout)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        # A result popup close is always a dismissal, never an app quit --
        # unlike MainWindow, this window has no tray-vs-quit distinction
        # to make since it isn't the app's tray-anchored primary window.
        event.accept()

    # -- state transitions --------------------------------------------

    def show_loading(self) -> None:
        self.status_label.setText("Reading selection…")
        self.fast_pane.show_placeholder()
        self.tabs.setCurrentWidget(self.fast_pane)
        self._remove_deep_tab()
        self.deep_button.setEnabled(False)
        self.deep_button.setToolTip("")

    def show_fast_result(self, result: DocumentResult, *, deep_available: bool) -> None:
        self.status_label.setText(f"✓ Read locally{_format_timing_suffix(result)}")
        self.fast_pane.set_result(result, allow_table_markdown_fallback=False)
        self.deep_button.setEnabled(deep_available)
        if not deep_available:
            self.deep_button.setToolTip("Set a Gemini API key in Settings to enable Deep Analyze.")

    def show_fast_error(self, message: str) -> None:
        self.status_label.setText(f"Fast OCR failed: {message}")
        self.deep_button.setEnabled(False)

    def show_deep_loading(self) -> None:
        self.status_label.setText("☁ Analyzing remotely…")
        self.deep_button.setEnabled(False)

    def show_deep_result(self, result: DocumentResult) -> None:
        self.status_label.setText(f"☁ Analyzed with Gemini{_format_timing_suffix(result)}")
        pane = self._ensure_deep_pane()
        pane.set_result(result, allow_table_markdown_fallback=True)
        self.tabs.setCurrentWidget(pane)
        self.deep_button.setEnabled(True)

    def show_deep_error(self, message: str) -> None:
        self.status_label.setText(message)
        self.deep_button.setEnabled(True)

    def _ensure_deep_pane(self) -> ContentPane:
        if self.deep_pane is None:
            self.deep_pane = ContentPane()
            self.deep_pane.copied.connect(self.text_copied)
            self.tabs.addTab(self.deep_pane, "Deep")
        return self.deep_pane

    def _remove_deep_tab(self) -> None:
        if self.deep_pane is not None:
            index = self.tabs.indexOf(self.deep_pane)
            if index != -1:
                self.tabs.removeTab(index)
        self.deep_pane = None
