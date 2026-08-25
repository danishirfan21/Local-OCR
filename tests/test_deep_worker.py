"""DeepWorker tests -- no real Gemini call. Mocks
build_production_gemini_provider so nothing reaches the network."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from local_lens.deep_analysis.base import (  # noqa: E402
    DeepAnalysisAuthError,
    DeepAnalysisError,
    DeepAnalysisRateLimited,
    DeepAnalysisTimeout,
)
from desktop.result.deep_worker import deep_error_message  # noqa: E402


def test_deep_error_message_maps_auth_error():
    assert deep_error_message(DeepAnalysisAuthError("nope")) == "Gemini rejected the configured API key."


def test_deep_error_message_maps_rate_limit():
    msg = deep_error_message(DeepAnalysisRateLimited("slow down"))
    assert "rate limit" in msg.lower()
    assert "Fast result is still available" in msg


def test_deep_error_message_maps_timeout():
    msg = deep_error_message(DeepAnalysisTimeout("too slow"))
    assert "timed out" in msg.lower()
    assert "Fast result" in msg


def test_deep_error_message_maps_generic_deep_analysis_error():
    msg = deep_error_message(DeepAnalysisError("server exploded"))
    assert "temporarily unavailable" in msg.lower()


def test_deep_error_message_maps_unexpected_exception():
    msg = deep_error_message(ValueError("weird"))
    assert "unexpectedly" in msg.lower()


def test_worker_fails_cleanly_when_no_provider_configured():
    from desktop.result.deep_worker import DeepWorker

    worker = DeepWorker(b"fake png bytes")
    failures = []
    worker.failed.connect(failures.append)
    worker.succeeded.connect(lambda _: pytest.fail("must not succeed without a configured key"))

    # Force "not configured" regardless of the real local .env -- tests
    # must never depend on (or accidentally use) real credentials.
    import desktop.result.deep_worker as deep_worker_module

    original = deep_worker_module.build_production_gemini_provider
    deep_worker_module.build_production_gemini_provider = lambda env=None: None
    try:
        worker.run()  # call synchronously -- no need for a real QThread here
    finally:
        deep_worker_module.build_production_gemini_provider = original

    assert failures == ["Deep Analyze requires a Gemini API key."]
