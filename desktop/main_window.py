"""V6.1 milestone window: Open Image -> Fast OCR -> result -> Copy.

No hotkey, tray, or capture yet -- those are V6.2/V6.3 per
docs/V6_DESKTOP_FRAMEWORK_DECISION.md's revised milestone plan. This proves
the Qt shell + QThread worker + OCRService integration in isolation.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.ocr_worker import OCRWorker
from local_lens.models import DocumentResult

_IMAGE_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp)"


def format_result_summary(result: DocumentResult) -> str:
    """Thin, explicit projection of DocumentResult for display -- the UI
    layer reads this, not DocumentResult internals directly, matching the
    "no ad hoc reaching into result internals" rule carried over from the
    superseded IPC-contract design."""
    content_type = result.metadata.get("content_type", "unknown")
    total_ms = result.metadata.get("total_ms")
    timing = f"{total_ms:.0f}ms" if isinstance(total_ms, (int, float)) else "n/a"
    scripts = ", ".join(result.detected_scripts) or "none detected"
    return f"Engine: {result.engine}  ·  Detected: {content_type}  ·  Scripts: {scripts}  ·  Time: {timing}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Local Lens")
        self.resize(640, 480)

        self._worker: OCRWorker | None = None
        self._last_result: DocumentResult | None = None

        self.open_button = QPushButton("Open Image")
        self.open_button.clicked.connect(self.open_image)

        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self.copy_result_text)
        self.copy_button.setEnabled(False)

        self.status_label = QLabel("Open an image to run Fast OCR.")
        self.status_label.setWordWrap(True)

        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setPlaceholderText("Extracted text will appear here.")

        button_row = QHBoxLayout()
        button_row.addWidget(self.open_button)
        button_row.addWidget(self.copy_button)
        button_row.addStretch(1)

        layout = QVBoxLayout()
        layout.addLayout(button_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.result_view, stretch=1)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def open_image(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Open Image", "", _IMAGE_FILE_FILTER)
        if not path_str:
            return
        self.run_ocr(Path(path_str).read_bytes())

    def run_ocr(self, image_bytes: bytes) -> None:
        self.open_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.status_label.setText("Running Fast OCR (local, offline)…")
        self.result_view.clear()

        self._worker = OCRWorker(image_bytes)
        self._worker.succeeded.connect(self._on_ocr_succeeded)
        self._worker.failed.connect(self._on_ocr_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_ocr_succeeded(self, result: DocumentResult) -> None:
        self._last_result = result
        self.result_view.setPlainText(result.text)
        self.status_label.setText(format_result_summary(result))
        self.copy_button.setEnabled(bool(result.text))

    def _on_ocr_failed(self, message: str) -> None:
        self.status_label.setText(f"Fast OCR failed: {message}")

    def _on_worker_finished(self) -> None:
        self.open_button.setEnabled(True)
        self._worker = None

    def copy_result_text(self) -> None:
        if self._last_result is None:
            return
        QGuiApplication.clipboard().setText(self._last_result.text)
