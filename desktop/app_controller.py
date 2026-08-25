"""Lifecycle coordinator: owns the main window, tray icon, global hotkey,
settings, capture, and the result popup -- and decides what each user
action means. MainWindow itself stays a plain result-display widget (used
only for the Open Image workflow now, see item 35) plus the one piece of
window-level behavior it must own (hide-vs-close); ResultWindow is the
flagship capture -> result surface (V6.4). Everything about *policy* --
what "Capture" does, Deep Analyze consent, OCR/Deep reentrancy, what
happens on Quit -- lives here, not scattered across widgets.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

from local_lens.deep_analysis.production import production_gemini_configured
from local_lens.env_file import load_env

from desktop.capture.controller import CaptureController, CaptureResult
from desktop.hotkey.manager import GlobalHotkeyManager
from desktop.hotkey.shortcut import is_supported
from desktop.icon import default_icon
from desktop.logging_setup import get_logger, setup_logging
from desktop.main_window import MainWindow
from desktop.ocr_worker import OCRWorker
from desktop.result.deep_worker import DeepWorker
from desktop.result.positioning import place_popup
from desktop.result.privacy_dialog import DeepPrivacyDialog
from desktop.result.window import ResultWindow
from desktop.settings import AppSettings
from desktop.settings_dialog import SettingsDialog
from desktop.tray import TrayController
from desktop.warmup_worker import WarmupWorker

logger = get_logger()


class DesktopApplication:
    """`app` is the QApplication instance -- passed in rather than created
    here so main.py stays the single place that constructs it."""

    def __init__(
        self,
        app,
        settings: AppSettings | None = None,
        hotkey_manager: GlobalHotkeyManager | None = None,
        enable_warmup: bool = True,
    ):
        setup_logging()
        logger.info("startup")

        self.app = app
        self.app.setQuitOnLastWindowClosed(False)

        self.settings = settings if settings is not None else AppSettings()

        self.main_window = MainWindow()
        self.main_window.hide_to_tray_enabled = True

        self.result_window = ResultWindow()
        self.result_window.deep_requested.connect(self._on_deep_requested)

        self._current_image_bytes: bytes | None = None
        self._fast_worker: OCRWorker | None = None
        self._deep_worker: DeepWorker | None = None
        self._deep_privacy_acknowledged = False

        self._window_was_visible_before_capture = False
        self.capture = CaptureController(hide_windows=self._hide_all_windows)
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

        self.warmup_worker = WarmupWorker()
        self.warmup_worker.finished_warmup.connect(self._on_warmup_finished)
        if enable_warmup:
            # Skippable for tests (item 45's "no actual OCR needed") --
            # starting this unconditionally would trigger a real ~10s
            # EasyOCR cold-load in every test that constructs a controller.
            self.tray.tray_icon.setToolTip("Local Lens -- starting OCR…")
            self.warmup_worker.start()

        # Dev-default: show on startup (item 7) -- "start minimized" is a
        # future Settings toggle.
        self.main_window.show()

    # -- hotkey / settings -----------------------------------------------

    def _register_hotkey(self, shortcut_text: str) -> bool:
        ok = self.hotkey_manager.register(shortcut_text)
        logger.info("hotkey %s", "registered" if ok else "registration failed")
        if ok:
            self.main_window.clear_shortcut_warning()
        return ok

    def _on_hotkey_registration_failed(self, message: str) -> None:
        self.main_window.show_shortcut_warning(message)

    def _on_warmup_finished(self) -> None:
        logger.info("OCR ready")
        self.tray.tray_icon.setToolTip("Local Lens -- ready")

    def _on_settings_requested(self) -> None:
        gemini_configured = production_gemini_configured(load_env())
        dialog = SettingsDialog(self.settings.shortcut, gemini_configured, parent=self.main_window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
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

    # -- windows -----------------------------------------------------------

    def _on_open_requested(self) -> None:
        self.main_window.bring_to_front()

    # -- capture -------------------------------------------------------

    def _hide_all_windows(self) -> None:
        # Both windows can appear inside a new capture if left visible --
        # a previous result popup left on screen leaked into a live test
        # capture until this was added. See docs/V6_4_RESULT_UX.md.
        self.main_window.hide()
        self.result_window.hide()

    def _is_ocr_busy(self) -> bool:
        for worker in (self.main_window._worker, self._fast_worker, self._deep_worker):
            if worker is not None and worker.isRunning():
                return True
        return False

    def _start_capture(self) -> None:
        """Shared by the global hotkey and the tray's Capture action --
        both trigger the exact same region-selection workflow."""
        if self._is_ocr_busy():
            # Reentrancy (item 25/40): prefer letting the current Fast/Deep
            # job finish rather than starting a second one concurrently.
            logger.info("capture requested while OCR/Deep in progress -- ignored")
            return

        self._window_was_visible_before_capture = self.main_window.isVisible()
        self.capture.start()

    def _on_capture_finished(self, capture_result: CaptureResult) -> None:
        logger.info("capture complete -- showing result popup")
        self._current_image_bytes = capture_result.png_bytes

        self.result_window.show_loading()
        self._position_result_window(capture_result)
        self.result_window.show()
        self.result_window.raise_()
        self.result_window.activateWindow()

        self._start_fast_ocr(capture_result.png_bytes)

    def _position_result_window(self, capture_result: CaptureResult) -> None:
        size = self.result_window.size()
        x, y = place_popup(
            capture_result.selection_global, size.width(), size.height(), capture_result.monitor_global
        )
        self.result_window.move(x, y)

    def _on_capture_cancelled(self) -> None:
        if self._window_was_visible_before_capture:
            self.main_window.bring_to_front()

    # -- Fast OCR (popup) -----------------------------------------------

    def _start_fast_ocr(self, image_bytes: bytes) -> None:
        worker = OCRWorker(image_bytes)
        worker.succeeded.connect(self._on_fast_ocr_succeeded)
        worker.failed.connect(self._on_fast_ocr_failed)
        worker.finished.connect(self._on_fast_worker_finished)
        self._fast_worker = worker
        worker.start()

    def _on_fast_ocr_succeeded(self, result) -> None:
        logger.info("OCR completed")
        deep_available = production_gemini_configured(load_env())
        self.result_window.show_fast_result(result, deep_available=deep_available)

    def _on_fast_ocr_failed(self, message: str) -> None:
        logger.info("OCR failed")
        self.result_window.show_fast_error(message)

    def _on_fast_worker_finished(self) -> None:
        self._fast_worker = None

    # -- Deep Analyze ------------------------------------------------

    def _on_deep_requested(self) -> None:
        if self._current_image_bytes is None or self._deep_worker is not None:
            return

        if not self._deep_privacy_acknowledged:
            dialog = DeepPrivacyDialog(parent=self.result_window)
            # Compared against the stable QDialog enum rather than
            # DeepPrivacyDialog's own DialogCode -- an injected fake
            # dialog (as tests use) only needs to implement exec(), not
            # redeclare a class attribute it inherits from QDialog.
            if dialog.exec() != QDialog.DialogCode.Accepted:
                logger.info("deep analyze declined at privacy prompt")
                return
            self._deep_privacy_acknowledged = True

        logger.info("deep analyze requested")
        self.result_window.show_deep_loading()

        worker = DeepWorker(self._current_image_bytes)
        worker.succeeded.connect(self._on_deep_succeeded)
        worker.failed.connect(self._on_deep_failed)
        worker.finished.connect(self._on_deep_worker_finished)
        self._deep_worker = worker
        worker.start()

    def _on_deep_succeeded(self, result) -> None:
        logger.info("deep analyze completed")
        self.result_window.show_deep_result(result)

    def _on_deep_failed(self, message: str) -> None:
        logger.info("deep analyze failed")
        self.result_window.show_deep_error(message)

    def _on_deep_worker_finished(self) -> None:
        self._deep_worker = None

    # -- shutdown --------------------------------------------------------

    def quit(self) -> None:
        logger.info("shutdown")
        self.hotkey_manager.unregister()

        for worker in (self.main_window._worker, self._fast_worker, self._deep_worker, self.warmup_worker):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(3000)

        self.tray.hide()
        self.result_window.hide()
        self.main_window.hide_to_tray_enabled = False
        self.main_window.close()
        self.app.quit()
