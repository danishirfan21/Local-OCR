"""Verifies EasyOCREngine's download_enabled wiring and the desktop
friendly-error translation for a missing model -- no real EasyOCR model
construction happens (a fake `easyocr` module is injected via sys.modules
so importing the real ~1GB torch-backed library never occurs here).
"""

from __future__ import annotations

import sys
import types

import pytest
from PIL import Image

from desktop.ocr_service_factory import MODEL_UNAVAILABLE_MESSAGE, friendly_model_error_message
from local_lens.engines.easyocr_engine import EasyOCREngine, _reader_cache


class _FakeReader:
    def __init__(self, langs, download_enabled=True):
        self.langs = langs
        self.download_enabled = download_enabled

    def readtext(self, image_np):
        return []


@pytest.fixture(autouse=True)
def _fake_easyocr_module(monkeypatch):
    _reader_cache.clear()
    fake_module = types.ModuleType("easyocr")
    fake_module.Reader = _FakeReader
    monkeypatch.setitem(sys.modules, "easyocr", fake_module)
    yield
    _reader_cache.clear()


def test_download_enabled_true_by_default():
    engine = EasyOCREngine()
    engine.extract(Image.new("RGB", (8, 8)), ["en"])
    reader = next(iter(_reader_cache.values()))
    assert reader.download_enabled is True


def test_download_enabled_false_is_passed_through():
    engine = EasyOCREngine(download_enabled=False)
    engine.extract(Image.new("RGB", (8, 8)), ["en"])
    reader = next(iter(_reader_cache.values()))
    assert reader.download_enabled is False


def test_friendly_model_error_message_translates_file_not_found():
    exc = FileNotFoundError("Missing C:/whatever/model.pth and downloads disabled")
    assert friendly_model_error_message(exc) == MODEL_UNAVAILABLE_MESSAGE


def test_friendly_model_error_message_passes_through_other_exceptions():
    exc = ValueError("some other unrelated failure")
    assert friendly_model_error_message(exc) == "some other unrelated failure"
