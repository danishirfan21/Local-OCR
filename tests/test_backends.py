"""Backend capability/status reporting -- must never raise, and must
report distinct not-installed vs not-configured states rather than
conflating them."""

from __future__ import annotations

from local_lens.backends import (
    deep_backend_status,
    fast_backend_statuses,
    legacy_local_deep_status,
    table_backend_status,
)


def test_easyocr_is_always_available():
    statuses = {s.name: s for s in fast_backend_statuses()}
    assert statuses["easyocr"].available is True
    assert statuses["easyocr"].mode == "local"


def test_fast_backend_statuses_never_raises_when_paddleocr_absent():
    statuses = {s.name: s for s in fast_backend_statuses()}
    assert "paddleocr" in statuses
    if not statuses["paddleocr"].available:
        assert statuses["paddleocr"].reason is not None


def test_table_backend_status_reports_reason_when_unavailable():
    status = table_backend_status()
    if not status.available:
        assert status.reason


def test_legacy_local_deep_status_reports_reason_when_unavailable():
    status = legacy_local_deep_status()
    assert status.mode == "local"
    if not status.available:
        assert status.reason


def test_deep_backend_status_shape():
    status = deep_backend_status()
    assert status.name == "deep_analyze"
    assert status.mode == "remote"
    assert isinstance(status.available, bool)
