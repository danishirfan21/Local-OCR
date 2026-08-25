"""System tray icon + menu. Emits signals only -- the controller
(app_controller.py) decides what each action actually does, keeping tray
UI and lifecycle policy separate (item 3)."""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TrayController:
    def __init__(self, icon: QIcon):
        self.tray_icon = QSystemTrayIcon(icon)
        self.tray_icon.setToolTip("Local Lens")

        menu = QMenu()
        self.capture_action = menu.addAction("Capture")
        self.open_action = menu.addAction("Open Local Lens")
        self.settings_action = menu.addAction("Settings")
        menu.addSeparator()
        self.quit_action = menu.addAction("Quit")
        self.tray_icon.setContextMenu(menu)

        # Left-click/double-click the tray icon also opens the window --
        # only the menu's "Open Local Lens" is required, this is a small
        # UX nicety on top of it.
        self.tray_icon.activated.connect(self._on_activated)

        self.capture_requested = self.capture_action.triggered
        self.open_requested = self.open_action.triggered
        self.settings_requested = self.settings_action.triggered
        self.quit_requested = self.quit_action.triggered

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_action.trigger()

    def show(self) -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        self.tray_icon.show()
        return True

    def hide(self) -> None:
        self.tray_icon.hide()
