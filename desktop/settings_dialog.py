"""V6.2 Settings dialog: global shortcut editor + Gemini configuration
status + a privacy reminder. Deliberately minimal -- item 14 explicitly
says not to add a pile of future toggles yet."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QKeySequenceEdit,
    QLabel,
    QVBoxLayout,
)

from desktop.hotkey.shortcut import parse_shortcut


class SettingsDialog(QDialog):
    def __init__(self, current_shortcut: str, gemini_configured: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Local Lens Settings")

        self._shortcut_edit = QKeySequenceEdit(QKeySequence(current_shortcut))
        self._shortcut_edit.keySequenceChanged.connect(self._validate_shortcut)

        self._shortcut_status = QLabel()
        self._shortcut_status.setWordWrap(True)

        gemini_text = "Gemini configured" if gemini_configured else "Gemini not configured"
        self._gemini_label = QLabel(gemini_text)

        privacy_label = QLabel("Fast stays on-device. Deep sends the selected image to Gemini.")
        privacy_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Global shortcut", self._shortcut_edit)
        form.addRow("", self._shortcut_status)
        form.addRow("Deep Analyze", self._gemini_label)

        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(privacy_label)
        layout.addWidget(self._buttons)
        self.setLayout(layout)

        self._validate_shortcut()

    def _validate_shortcut(self) -> None:
        text = self._shortcut_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if not text:
            self._shortcut_status.setText("Press a key combination.")
            ok_button.setEnabled(False)
            return
        try:
            parse_shortcut(text)
        except ValueError as exc:
            self._shortcut_status.setText(str(exc))
            ok_button.setEnabled(False)
            return
        self._shortcut_status.setText("")
        ok_button.setEnabled(True)

    def shortcut_text(self) -> str:
        return self._shortcut_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
