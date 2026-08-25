"""Settings dialog -- V6.5's first-release scope (item 3): General,
Behavior, and Deep Analyze only. Deliberately excludes an OCR-engine
dropdown, benchmark settings, a provider zoo, model tuning, history
controls, and account/subscription controls -- those are out of scope
for a screenshot-OCR utility, not deferred features."""

from __future__ import annotations

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from desktop.hotkey.shortcut import DEFAULT_SHORTCUT, parse_shortcut


class SettingsDialog(QDialog):
    def __init__(
        self,
        current_shortcut: str,
        gemini_configured: bool,
        *,
        start_with_windows: bool = False,
        auto_copy_fast_result: bool = False,
        show_result_popup: bool = True,
        close_popup_after_copy: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Local Lens Settings")

        # -- General ----------------------------------------------------
        self._shortcut_edit = QKeySequenceEdit(QKeySequence(current_shortcut))
        self._shortcut_edit.keySequenceChanged.connect(self._validate_shortcut)

        self._restore_default_button = QPushButton("Restore Default")
        self._restore_default_button.clicked.connect(self._restore_default_shortcut)

        shortcut_row = QHBoxLayout()
        shortcut_row.addWidget(self._shortcut_edit, stretch=1)
        shortcut_row.addWidget(self._restore_default_button)

        self._shortcut_status = QLabel()
        self._shortcut_status.setWordWrap(True)
        self._shortcut_status.setStyleSheet("color: #b45309;")

        self._start_with_windows_check = QCheckBox("Start Local Lens with Windows")
        self._start_with_windows_check.setChecked(start_with_windows)

        self._auto_copy_check = QCheckBox("Auto-copy Fast result after capture")
        self._auto_copy_check.setChecked(auto_copy_fast_result)

        general_form = QFormLayout()
        general_form.addRow("Capture shortcut", shortcut_row)
        general_form.addRow("", self._shortcut_status)
        general_group = QGroupBox("General")
        general_layout = QVBoxLayout()
        general_layout.addLayout(general_form)
        general_layout.addWidget(self._start_with_windows_check)
        general_layout.addWidget(self._auto_copy_check)
        general_group.setLayout(general_layout)

        # -- Behavior -----------------------------------------------------
        self._show_popup_check = QCheckBox("Show result popup after capture")
        self._show_popup_check.setChecked(show_result_popup)
        self._show_popup_check.toggled.connect(self._on_show_popup_toggled)

        self._close_after_copy_check = QCheckBox("Close popup after successful copy")
        self._close_after_copy_check.setChecked(close_popup_after_copy)
        self._close_after_copy_check.setEnabled(show_result_popup)

        behavior_group = QGroupBox("Behavior")
        behavior_layout = QVBoxLayout()
        behavior_layout.addWidget(self._show_popup_check)
        behavior_layout.addWidget(self._close_after_copy_check)
        behavior_group.setLayout(behavior_layout)

        # -- Deep Analyze ---------------------------------------------
        gemini_text = "Gemini configured" if gemini_configured else "Gemini not configured"
        self._gemini_label = QLabel(gemini_text)

        privacy_label = QLabel(
            "Fast OCR runs entirely on this device.\nDeep Analyze sends the selected image to Google's Gemini API."
        )
        privacy_label.setWordWrap(True)

        key_guidance = QLabel(
            "To enable Deep Analyze, set LOCAL_LENS_GEMINI_API_KEY in a .env file "
            "in the Local Lens folder, then restart Local Lens."
        )
        key_guidance.setWordWrap(True)
        key_guidance.setVisible(not gemini_configured)

        deep_group = QGroupBox("Deep Analyze")
        deep_layout = QVBoxLayout()
        deep_layout.addWidget(self._gemini_label)
        deep_layout.addWidget(privacy_label)
        deep_layout.addWidget(key_guidance)
        deep_group.setLayout(deep_layout)

        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(general_group)
        layout.addWidget(behavior_group)
        layout.addWidget(deep_group)
        layout.addWidget(self._buttons)
        self.setLayout(layout)

        self._validate_shortcut()

    def _restore_default_shortcut(self) -> None:
        self._shortcut_edit.setKeySequence(QKeySequence(DEFAULT_SHORTCUT))

    def _on_show_popup_toggled(self, checked: bool) -> None:
        self._close_after_copy_check.setEnabled(checked)
        if not checked:
            self._close_after_copy_check.setChecked(False)

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

    def start_with_windows(self) -> bool:
        return self._start_with_windows_check.isChecked()

    def auto_copy_fast_result(self) -> bool:
        return self._auto_copy_check.isChecked()

    def show_result_popup(self) -> bool:
        return self._show_popup_check.isChecked()

    def close_popup_after_copy(self) -> bool:
        return self._close_after_copy_check.isChecked()
