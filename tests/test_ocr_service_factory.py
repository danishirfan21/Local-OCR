"""desktop.ocr_service_factory wiring tests -- _new_fast_engine's
download_enabled/model_storage_directory wiring and the one-time model-
source log line (V6.8 item 16). No real EasyOCR construction: a fake
`easyocr` module is injected via sys.modules, same technique as
tests/test_easyocr_download_guard.py.
"""

from __future__ import annotations

import sys
import types

import pytest
from PIL import Image

import desktop.ocr_service_factory as ocr_service_factory
from local_lens.engines.easyocr_engine import _reader_cache


class _FakeReader:
    def __init__(self, langs, download_enabled=True, model_storage_directory=None):
        self.download_enabled = download_enabled
        self.model_storage_directory = model_storage_directory

    def readtext(self, image_np):
        return []


@pytest.fixture(autouse=True)
def _fake_easyocr_module(monkeypatch):
    _reader_cache.clear()
    fake_module = types.ModuleType("easyocr")
    fake_module.Reader = _FakeReader
    monkeypatch.setitem(sys.modules, "easyocr", fake_module)
    ocr_service_factory._logged_model_source_once = False
    yield
    _reader_cache.clear()


def test_new_fast_engine_keeps_download_enabled_false():
    engine = ocr_service_factory._new_fast_engine()
    engine.extract(Image.new("RGB", (8, 8)), ["en"])
    reader = next(iter(_reader_cache.values()))
    assert reader.download_enabled is False


def test_new_fast_engine_passes_resolved_model_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr_service_factory, "resolve_easyocr_model_dir", lambda: tmp_path)
    engine = ocr_service_factory._new_fast_engine()
    engine.extract(Image.new("RGB", (8, 8)), ["en"])
    reader = next(iter(_reader_cache.values()))
    assert reader.model_storage_directory == str(tmp_path)


def test_new_fast_engine_logs_model_source_label_once(monkeypatch, caplog):
    monkeypatch.setattr(ocr_service_factory, "easyocr_model_source_label", lambda: "bundled")
    import logging

    caplog.set_level(logging.INFO, logger=ocr_service_factory.logger.name)
    ocr_service_factory._new_fast_engine()
    ocr_service_factory._new_fast_engine()
    matching = [r for r in caplog.records if "Fast OCR model source" in r.getMessage()]
    assert len(matching) == 1  # logged once per process, not once per engine construction
    assert "bundled" in matching[0].getMessage()


def test_model_unavailable_message_does_not_tell_a_packaged_user_to_run_dev_setup():
    # V6.7's wording ("run the desktop app in a normal development setup")
    # made no sense for a portable release build; V6.8's replacement must
    # not regress back to it.
    assert "development setup" not in ocr_service_factory.MODEL_UNAVAILABLE_MESSAGE
