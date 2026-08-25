"""Lifecycle coordinator: owns the main window, tray icon, global hotkey,
and settings, and decides what each user action means. MainWindow itself
stays a plain result-display widget (V6.1) plus the one piece of window-
level behavior it must own (hide-vs-close) -- everything else (what
"Capture" does, what happens on Quit, hotkey registration) lives here,
per item 3's "do not place all this logic inside MainWindow."
"""

from __future__ import annotations

from local_lens.deep_analysis.production import production_gemini_configured
from local_lens.env_file import load_env

from desktop.capture.controller import CaptureController
from desktop.hotkey.manager import GlobalHotkeyManager
from desktop.hotkey.shortcut import is_supported
from desktop.icon import default_icon
from desktop.logging_setup import get_logger, setup_logging
from desktop.main_window import MainWindow
from desktop.settings import AppSettings
from desktop.settings_dialog import SettingsDialog
from desktop.tray import TrayController

logger = get_logger()


class DesktopApplication:
    """`app` is the QApplication instance -- passed in rather than created
    here so main.py stays the single place that constructs it."""

    def __init__(
        self,
        app,
        settings: AppSettings | None = None,
        hotkey_manager: GlobalHotkeyManager | None = None,
    ):
        setup_logging()
        logger.info("startup")

        self.app = app
        self.app.setQuitOnLastWindowClosed(False)

        self.settings = settings if settings is not None else AppSettings()

        self.main_window = MainWindow()
        self.main_window.hide_to_tray_enabled = True

        self._window_was_visible_before_capture = False
        self.capture = CaptureController(hide_windows=self.main_window.hide)
        self.capture.captured.connect(self._on_capture_finished)
        self.capture.cancelled.connect(self._on_capture_cancelled)

        self.hotkey_manager = hotkey_manager if hotkey_manager is not None else GlobalHotkeyManager(app=self.app)
        self.hotkey_manager.triggered.connect(self._start_capture)
        self.hotkey_manager.registration_failed.connect(self._on_hotkey_registration_failed)

        self.tray = TrayController(default_icon())
        self.tray.capture_requested.connect(self._start_capture)
        self.tray.open_requested.connect(self._on_open_requested)
        self.tray.settings_requested.connect(self._on_settings_requested)
        self.tray.quit_requested.connect(self.quit)

        tray_available = self.tray.show()
        logger.info("tray %s", "available" if tray_available else "unavailable")

        self._register_hotkey(self.settings.shortcut)

        # Dev-default: show on startup (item 7) -- "start minimized" is a
        # future Settings toggle, not V6.2.
        self.main_window.show()

    def _register_hotkey(self, shortcut_text: str) -> bool:
        ok = self.hotkey_manager.register(shortcut_text)
        logger.info("hotkey %s", "registered" if ok else "registration failed")
        if ok:
            self.main_window.clear_shortcut_warning()
        return ok

    def _on_hotkey_registration_failed(self, message: str) -> None:
        self.main_window.show_shortcut_warning(message)

    def _start_capture(self) -> None:
        """Shared by the global hotkey and the tray's Capture action --
        both trigger the exact same region-selection workflow."""
        worker = self.main_window._worker
        if worker is not None and worker.isRunning():
            # OCR reentrancy: prefer letting the current job finish rather
            # than starting a second EasyOCR run concurrently (item 25).
            logger.info("capture requested while OCR in progress -- ignored")
            self.main_window.bring_to_front()
            self.main_window.status_label.setText("OCR already in progress -- please wait.")
            return

        self._window_was_visible_before_capture = self.main_window.isVisible()
        self.capture.start()

    def _on_capture_finished(self, png_bytes: bytes) -> None:
        logger.info("capture complete -- starting Fast OCR")
        self.main_window.bring_to_front()
        self.main_window.run_ocr(png_bytes)

    def _on_capture_cancelled(self) -> None:
        if self._window_was_visible_before_capture:
            self.main_window.bring_to_front()

    def _on_open_requested(self) -> None:
        self._show_main_window()

    def _show_main_window(self) -> None:
        self.main_window.bring_to_front()

    def _on_settings_requested(self) -> None:
        gemini_configured = production_gemini_configured(load_env())
        dialog = SettingsDialog(self.settings.shortcut, gemini_configured, parent=self.main_window)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return

        new_shortcut = dialog.shortcut_text()
        if not new_shortcut or new_shortcut == self.settings.shortcut or not is_supported(new_shortcut):
            return

        previous = self.settings.shortcut
        if self._register_hotkey(new_shortcut):
            self.settings.shortcut = new_shortcut
        else:
            # Registration failed -- restore the previously working
            # shortcut rather than leaving nothing registered (item 28).
            self._register_hotkey(previous)

    def quit(self) -> None:
        logger.info("shutdown")
        self.hotkey_manager.unregister()

        worker = self.main_window._worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.wait(3000)

        self.tray.hide()
        self.main_window.hide_to_tray_enabled = False
        self.main_window.close()
        self.app.quit()
