"""Fast mode must never make a network call on its own -- only an explicit
Deep Analyze provider.extract() call is allowed to touch the network. This
guards against silent cloud requests during ordinary OCR/CLI/import use."""

from __future__ import annotations

import urllib.request

import pytest

from local_lens.services.ocr_service import OCRService
from tests.test_engines import FakeEngine, _png_bytes


@pytest.fixture(autouse=True)
def _fail_on_network(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("Fast-mode code path must not open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    yield


def test_fast_mode_ocr_makes_no_network_call():
    service = OCRService(FakeEngine())
    result = service.process(_png_bytes(), ["en"])
    assert result.engine == "fake"


def test_importing_deep_analysis_modules_makes_no_network_call():
    import local_lens.backends  # noqa: F401
    import local_lens.deep_analysis.anthropic_provider  # noqa: F401
    import local_lens.deep_analysis.benchmark  # noqa: F401
    import local_lens.deep_analysis.benchmark_cases  # noqa: F401
    import local_lens.deep_analysis.config  # noqa: F401
    import local_lens.deep_analysis.deep_metrics  # noqa: F401
    import local_lens.deep_analysis.finalists  # noqa: F401
    import local_lens.deep_analysis.gemini_provider  # noqa: F401
    import local_lens.deep_analysis.manifest  # noqa: F401
    import local_lens.deep_analysis.openai_compatible_provider  # noqa: F401
    import local_lens.deep_analysis.paddle_vllm_provider  # noqa: F401
    import local_lens.deep_analysis.runner  # noqa: F401
    import local_lens.deep_analysis.sanitize  # noqa: F401
    import local_lens.env_file  # noqa: F401

    from local_lens.backends import deep_backend_status
    from local_lens.deep_analysis.config import build_deep_provider

    deep_backend_status()
    build_deep_provider(env={})
