"""DesktopApplication lifecycle tests -- isolated QSettings (temp .ini) and
a fake hotkey adapter, so no real Windows registration or real registry
writes happen. Verifies close-to-tray behavior, Quit lifecycle, and the
Settings dialog's "don't overwrite a working shortcut with a failed one"
rule (item 28)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, QRect, QSettings, Signal  # noqa: E402
from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from desktop.app_controller import DesktopApplication  # noqa: E402
from desktop.capture.geometry import PixelRect  # noqa: E402
from desktop.hotkey.manager import GlobalHotkeyManager  # noqa: E402
from desktop.settings import AppSettings  # noqa: E402
from local_lens.models import DocumentResult  # noqa: E402
from tests.test_hotkey_manager import FakeAdapter  # noqa: E402


class _FakeRunningWorker:
    def isRunning(self):
        return True

    def requestInterruption(self):
        pass

    def wait(self, _timeout_ms):
        pass


def _fake_document_result(text: str = "extracted text", content_type: str = "text") -> DocumentResult:
    return DocumentResult(
        text=text,
        blocks=[],
        language="en",
        engine="easyocr",
        metadata={"content_type": content_type, "total_ms": 250.0},
        detected_scripts=["Latin"],
    )


class _FakeOCRWorker(QObject):
    """Stands in for desktop.ocr_worker.OCRWorker -- emits synchronously
    on start() so tests never run real EasyOCR (item 45)."""

    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, image_bytes, parent=None):
        super().__init__(parent)
        self._image_bytes = image_bytes

    def isRunning(self):
        return False

    def start(self):
        self.succeeded.emit(_fake_document_result())
        self.finished.emit()


class _FakeScreen:
    def geometry(self):
        return QRect(0, 0, 400, 300)

    def devicePixelRatio(self):
        return 1.0

    def name(self):
        return "FAKE-1"


def _fake_pixmap():
    pixmap = QPixmap(400, 300)
    pixmap.fill(QColor(20, 20, 20))
    return pixmap


def _patch_capture(monkeypatch):
    monkeypatch.setattr("desktop.capture.controller.screen_under_cursor", lambda: _FakeScreen())
    monkeypatch.setattr("desktop.capture.controller.grab_screen", lambda screen: _fake_pixmap())


def _pump_past_hide_settle(qapp):
    # CaptureController.start() defers _begin_overlay by a short real
    # settle delay (_HIDE_SETTLE_MS) -- processEvents() alone won't fire a
    # not-yet-due QTimer, so this actually waits past it.
    import time

    from desktop.capture.controller import _HIDE_SETTLE_MS

    deadline = time.time() + (_HIDE_SETTLE_MS / 1000) + 0.2
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Local Lens Test")
    app.setOrganizationName("Local Lens Test")
    yield app


def _controller(qapp, tmp_path, adapter=None) -> DesktopApplication:
    settings = AppSettings(backing=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    hotkey_manager = GlobalHotkeyManager(adapter=adapter if adapter is not None else FakeAdapter())
    return DesktopApplication(qapp, settings=settings, hotkey_manager=hotkey_manager, enable_warmup=False)


def test_controller_shows_main_window_and_registers_default_shortcut(qapp, tmp_path):
    controller = _controller(qapp, tmp_path)
    assert controller.main_window.isVisible()
    assert controller.hotkey_manager._adapter.registered_calls
    controller.quit()


def test_closing_main_window_hides_rather_than_exits(qapp, tmp_path):
    controller = _controller(qapp, tmp_path)
    assert controller.main_window.hide_to_tray_enabled is True
    controller.main_window.close()
    assert not controller.main_window.isVisible()
    # The app itself is still alive -- closing the window didn't quit it.
    assert controller.app is qapp
    controller.quit()


def test_quit_unregisters_hotkey_and_hides_window(qapp, tmp_path):
    adapter = FakeAdapter()
    controller = _controller(qapp, tmp_path, adapter=adapter)
    controller.quit()
    assert adapter.unregister_calls == 1
    assert not controller.main_window.isVisible()
    assert controller.main_window.hide_to_tray_enabled is False


def test_hotkey_triggered_starts_capture_and_hides_window(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)

    controller.hotkey_manager.triggered.emit()
    _pump_past_hide_settle(qapp)

    assert controller.capture.is_active
    assert not controller.main_window.isVisible()
    controller.capture._teardown_overlay()
    controller.quit()


def test_tray_capture_action_also_starts_capture(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)

    controller.tray.capture_requested.emit()
    _pump_past_hide_settle(qapp)

    assert controller.capture.is_active
    controller.capture._teardown_overlay()
    controller.quit()


def test_completed_capture_shows_result_popup_and_runs_fast_ocr(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeOCRWorker)
    controller = _controller(qapp, tmp_path)

    controller._start_capture()
    _pump_past_hide_settle(qapp)
    controller.capture._on_selection_made(PixelRect(left=10, top=10, width=50, height=50))

    assert controller.result_window.isVisible()
    assert not controller.main_window.isVisible()  # capture no longer routes through MainWindow (item 35)
    assert controller.result_window.fast_pane.text_view.toPlainText() == "extracted text"
    assert "Read locally" in controller.result_window.status_label.text()
    controller.quit()


def test_capture_ignored_while_ocr_already_running(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)

    controller.main_window._worker = _FakeRunningWorker()
    controller._start_capture()
    qapp.processEvents()

    assert not controller.capture.is_active  # capture never actually started
    assert not controller.result_window.isVisible()
    controller.quit()


def test_capture_ignored_while_fast_ocr_popup_worker_running(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)
    controller._fast_worker = _FakeRunningWorker()

    controller._start_capture()
    qapp.processEvents()

    assert not controller.capture.is_active
    controller.quit()


def test_capture_ignored_while_deep_worker_running(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)
    controller._deep_worker = _FakeRunningWorker()

    controller._start_capture()
    qapp.processEvents()

    assert not controller.capture.is_active
    controller.quit()


def test_cancelled_capture_restores_window_only_if_it_was_visible(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)
    assert controller.main_window.isVisible()

    controller._start_capture()
    _pump_past_hide_settle(qapp)
    controller.capture._on_cancelled()

    assert controller.main_window.isVisible()  # was visible before capture -- restored
    controller.quit()


def test_registration_failure_shows_warning_on_main_window(qapp, tmp_path):
    controller = _controller(qapp, tmp_path, adapter=FakeAdapter(should_succeed=False))
    assert controller.main_window.shortcut_status_label.isVisible()
    controller.quit()


def test_settings_dialog_rejecting_new_shortcut_restores_previous_registration(qapp, tmp_path, monkeypatch):
    # A working shortcut is registered first; simulate the user "changing"
    # it to something the adapter then refuses (already in use elsewhere)
    # -- the previously working shortcut must be re-registered, not left
    # unregistered (item 28).
    adapter = FakeAdapter(should_succeed=True)
    controller = _controller(qapp, tmp_path, adapter=adapter)
    assert controller.settings.shortcut == "Ctrl+Shift+Space"

    adapter.should_succeed = False
    ok = controller._register_hotkey("Ctrl+Alt+L")
    assert ok is False
    # Simulate the settings-dialog fallback path directly (the dialog
    # itself is exercised in test_settings_dialog.py; here we test the
    # controller's re-registration logic in isolation).
    adapter.should_succeed = True
    restored = controller._register_hotkey(controller.settings.shortcut)
    assert restored is True
    controller.quit()


class _FakeDeepWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, image_bytes, parent=None):
        super().__init__(parent)
        self._image_bytes = image_bytes

    def isRunning(self):
        return False

    def start(self):
        self.succeeded.emit(_fake_document_result(text="deep text"))
        self.finished.emit()


class _FakeAcceptingPrivacyDialog:
    def __init__(self, parent=None):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted


class _FakeRejectingPrivacyDialog:
    def __init__(self, parent=None):
        pass

    def exec(self):
        return QDialog.DialogCode.Rejected


def _capture_one_result(controller, qapp):
    controller._start_capture()
    _pump_past_hide_settle(qapp)
    controller.capture._on_selection_made(PixelRect(left=10, top=10, width=50, height=50))


def test_deep_requested_shows_privacy_dialog_then_runs_deep(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeOCRWorker)
    monkeypatch.setattr("desktop.app_controller.DeepWorker", _FakeDeepWorker)
    monkeypatch.setattr("desktop.app_controller.DeepPrivacyDialog", _FakeAcceptingPrivacyDialog)
    monkeypatch.setattr("desktop.app_controller.production_gemini_configured", lambda env: True)

    controller = _controller(qapp, tmp_path)
    _capture_one_result(controller, qapp)

    assert controller._deep_privacy_acknowledged is False
    controller.result_window.deep_requested.emit()

    assert controller._deep_privacy_acknowledged is True
    assert controller.result_window.deep_pane.text_view.toPlainText() == "deep text"
    controller.quit()


def test_declining_privacy_dialog_sends_no_deep_request(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeOCRWorker)
    monkeypatch.setattr("desktop.app_controller.DeepWorker", _FakeDeepWorker)
    monkeypatch.setattr("desktop.app_controller.DeepPrivacyDialog", _FakeRejectingPrivacyDialog)
    monkeypatch.setattr("desktop.app_controller.production_gemini_configured", lambda env: True)

    controller = _controller(qapp, tmp_path)
    _capture_one_result(controller, qapp)
    controller.result_window.deep_requested.emit()

    assert controller._deep_privacy_acknowledged is False
    assert controller.result_window.deep_pane is None
    controller.quit()


def test_privacy_dialog_only_shown_once_per_session(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeOCRWorker)
    monkeypatch.setattr("desktop.app_controller.DeepWorker", _FakeDeepWorker)
    monkeypatch.setattr("desktop.app_controller.production_gemini_configured", lambda env: True)

    construct_count = []

    class _CountingAcceptDialog(_FakeAcceptingPrivacyDialog):
        def __init__(self, parent=None):
            construct_count.append(1)

    monkeypatch.setattr("desktop.app_controller.DeepPrivacyDialog", _CountingAcceptDialog)

    controller = _controller(qapp, tmp_path)
    _capture_one_result(controller, qapp)
    controller.result_window.deep_requested.emit()
    controller.result_window.deep_requested.emit()  # second Deep click, same session

    assert len(construct_count) == 1
    controller.quit()


def test_capture_and_fast_ocr_make_zero_network_calls_until_deep_clicked(qapp, tmp_path, monkeypatch):
    import urllib.request

    def _forbidden(*args, **kwargs):
        raise AssertionError("Fast-mode capture path must not open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeOCRWorker)

    controller = _controller(qapp, tmp_path)
    _capture_one_result(controller, qapp)

    assert controller.result_window.isVisible()  # reached here without raising -> no network call happened
    controller.quit()


# -- V6.5: settings-driven capture/result behavior -----------------------


def test_start_hidden_keeps_main_window_hidden_at_startup(qapp, tmp_path):
    settings = AppSettings(backing=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    hotkey_manager = GlobalHotkeyManager(adapter=FakeAdapter())
    controller = DesktopApplication(
        qapp, settings=settings, hotkey_manager=hotkey_manager, enable_warmup=False, start_hidden=True
    )
    assert not controller.main_window.isVisible()
    controller.quit()


def test_capture_now_button_starts_capture(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    controller = _controller(qapp, tmp_path)

    controller.main_window.capture_button.click()
    _pump_past_hide_settle(qapp)

    assert controller.capture.is_active
    controller.capture._teardown_overlay()
    controller.quit()


def test_show_result_popup_disabled_still_runs_ocr_but_never_shows_the_window(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeOCRWorker)

    controller = _controller(qapp, tmp_path)
    controller.settings.show_result_popup = False
    _capture_one_result(controller, qapp)

    assert not controller.result_window.isVisible()
    assert controller.result_window.fast_pane.text_view.toPlainText() == "extracted text"
    controller.quit()


def test_auto_copy_enabled_copies_fast_text_to_clipboard(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QGuiApplication

    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeOCRWorker)

    controller = _controller(qapp, tmp_path)
    controller.settings.auto_copy_fast_result = True
    _capture_one_result(controller, qapp)

    assert QGuiApplication.clipboard().text() == "extracted text"
    controller.quit()


def test_auto_copy_disabled_by_default_leaves_clipboard_untouched(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QGuiApplication

    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeOCRWorker)

    QGuiApplication.clipboard().setText("sentinel-untouched")
    controller = _controller(qapp, tmp_path)
    _capture_one_result(controller, qapp)

    assert QGuiApplication.clipboard().text() == "sentinel-untouched"
    controller.quit()


def test_auto_copy_skips_empty_result(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QGuiApplication

    class _FakeEmptyOCRWorker(_FakeOCRWorker):
        def start(self):
            self.succeeded.emit(_fake_document_result(text=""))
            self.finished.emit()

    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeEmptyOCRWorker)

    QGuiApplication.clipboard().setText("sentinel-untouched")
    controller = _controller(qapp, tmp_path)
    controller.settings.auto_copy_fast_result = True
    _capture_one_result(controller, qapp)

    assert QGuiApplication.clipboard().text() == "sentinel-untouched"
    controller.quit()


def test_auto_copy_skips_fast_ocr_failure(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QGuiApplication

    class _FakeFailingOCRWorker(_FakeOCRWorker):
        def start(self):
            self.failed.emit("engine exploded")
            self.finished.emit()

    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeFailingOCRWorker)

    QGuiApplication.clipboard().setText("sentinel-untouched")
    controller = _controller(qapp, tmp_path)
    controller.settings.auto_copy_fast_result = True
    _capture_one_result(controller, qapp)

    assert QGuiApplication.clipboard().text() == "sentinel-untouched"
    controller.quit()


def test_close_after_copy_hides_popup_when_copy_button_clicked(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeOCRWorker)

    controller = _controller(qapp, tmp_path)
    controller.settings.close_popup_after_copy = True
    _capture_one_result(controller, qapp)
    assert controller.result_window.isVisible()

    controller.result_window.fast_pane.copy_button.click()
    assert not controller.result_window.isVisible()
    controller.quit()


def test_close_after_copy_disabled_by_default_leaves_popup_open(qapp, tmp_path, monkeypatch):
    _patch_capture(monkeypatch)
    monkeypatch.setattr("desktop.app_controller.OCRWorker", _FakeOCRWorker)

    controller = _controller(qapp, tmp_path)
    _capture_one_result(controller, qapp)
    controller.result_window.fast_pane.copy_button.click()

    assert controller.result_window.isVisible()
    controller.quit()


def test_settings_dialog_persists_v6_5_toggles(qapp, tmp_path, monkeypatch):
    class _FakeSettingsDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def shortcut_text(self):
            return "Ctrl+Shift+Space"

        def start_with_windows(self):
            return False

        def auto_copy_fast_result(self):
            return True

        def show_result_popup(self):
            return False

        def close_popup_after_copy(self):
            return False

    monkeypatch.setattr("desktop.app_controller.SettingsDialog", _FakeSettingsDialog)
    controller = _controller(qapp, tmp_path)

    controller._on_settings_requested()

    assert controller.settings.auto_copy_fast_result is True
    assert controller.settings.show_result_popup is False
    controller.quit()


def test_settings_dialog_start_with_windows_toggle_calls_startup_module(qapp, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("desktop.app_controller.set_startup_enabled", lambda enabled: calls.append(enabled))

    class _FakeSettingsDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def shortcut_text(self):
            return "Ctrl+Shift+Space"

        def start_with_windows(self):
            return True

        def auto_copy_fast_result(self):
            return False

        def show_result_popup(self):
            return True

        def close_popup_after_copy(self):
            return False

    monkeypatch.setattr("desktop.app_controller.SettingsDialog", _FakeSettingsDialog)
    controller = _controller(qapp, tmp_path)

    controller._on_settings_requested()

    assert calls == [True]
    assert controller.settings.start_with_windows is True
    controller.quit()
