"""One-per-session Deep Analyze consent dialog. Session-only by design
(item 20) -- not persisted in QSettings; the app_controller tracks
whether it's been accepted for the lifetime of the running process only.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

_PRIVACY_TEXT = (
    "Deep Analyze sends this selected image to Google's Gemini API.\n\n"
    "Fast OCR stays on your device.\n\n"
    "Google's free-tier API may use submitted content to improve products "
    "and may involve human review."
)


class DeepPrivacyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Deep Analyze")

        label = QLabel(_PRIVACY_TEXT)
        label.setWordWrap(True)

        buttons = QDialogButtonBox()
        buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.addButton("Analyze remotely", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(buttons)
        self.setLayout(layout)
