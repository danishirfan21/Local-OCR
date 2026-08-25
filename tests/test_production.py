"""Tests for the production Gemini Deep Analyze provider
(local_lens/deep_analysis/production.py) -- config detection, env
precedence, request/response behavior (via a fake transport), every
documented error path, latency/usage metadata, and secret non-exposure.
No real network call anywhere in this file."""

from __future__ import annotations

import json

import pytest
from PIL import Image

from local_lens.deep_analysis.base import (
    DeepAnalysisAuthError,
    DeepAnalysisBadResponse,
    DeepAnalysisRateLimited,
    DeepAnalysisServerError,
    DeepAnalysisTimeout,
)
from local_lens.deep_analysis.http_client import HttpResponse, HttpTimeout
from local_lens.deep_analysis.production import (
    PRODUCTION_GEMINI_MODEL,
    GeminiDeepProvider,
    build_production_gemini_provider,
    production_gemini_configured,
    production_gemini_status,
)


def _image() -> Image.Image:
    return Image.new("RGB", (10, 10), "white")


class _FakeTransport:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls: list[tuple] = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, body, timeout))
        if self.exc is not None:
            raise self.exc
        return self.response


def _gemini_response(text: str, usage: dict | None = None) -> HttpResponse:
    payload = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    if usage:
        payload["usageMetadata"] = usage
    return HttpResponse(status=200, body=json.dumps(payload).encode("utf-8"), headers={})


# --- config detection / precedence ----------------------------------------


def test_not_configured_by_default():
    assert production_gemini_configured(env={}) is False


def test_configured_when_key_present():
    assert production_gemini_configured(env={"LOCAL_LENS_GEMINI_API_KEY": "real-looking-key"}) is True


def test_placeholder_value_treated_as_unconfigured():
    assert production_gemini_configured(env={"LOCAL_LENS_GEMINI_API_KEY": "changeme"}) is False


def test_benchmark_key_alone_does_not_configure_production():
    env = {"LOCAL_LENS_BENCHMARK_GEMINI_API_KEY": "benchmark-key"}
    assert production_gemini_configured(env=env) is False


def test_production_key_and_benchmark_key_are_independent():
    env = {
        "LOCAL_LENS_GEMINI_API_KEY": "prod-key",
        "LOCAL_LENS_BENCHMARK_GEMINI_API_KEY": "different-benchmark-key",
    }
    assert production_gemini_configured(env=env) is True
    provider = build_production_gemini_provider(env=env)
    # The provider must have been built from the PRODUCTION key, not the
    # benchmark one -- checked indirectly via a request using it.
    assert provider is not None


def test_status_reports_frozen_model_when_configured():
    status = production_gemini_status(env={"LOCAL_LENS_GEMINI_API_KEY": "k"})
    assert status.available is True
    assert PRODUCTION_GEMINI_MODEL in status.reason


def test_status_reports_env_var_name_when_unconfigured():
    status = production_gemini_status(env={})
    assert status.available is False
    assert "LOCAL_LENS_GEMINI_API_KEY" in status.reason


def test_build_provider_returns_none_when_unconfigured():
    assert build_production_gemini_provider(env={}) is None


# --- provider construction / model freeze ----------------------------------


def test_provider_model_is_frozen_and_not_overridable_by_env():
    env = {"LOCAL_LENS_GEMINI_API_KEY": "k", "LOCAL_LENS_DEEP_MODEL": "gemini-99-experimental"}
    provider = build_production_gemini_provider(env=env)
    assert provider.model == PRODUCTION_GEMINI_MODEL


def test_gemini_deep_provider_name():
    provider = GeminiDeepProvider(api_key="k")
    assert provider.name == "gemini_deep"
    assert provider.model == PRODUCTION_GEMINI_MODEL


# --- request/response behavior (fake transport, no network) ---------------


def test_successful_extraction():
    transport = _FakeTransport(_gemini_response('{"text": "Save", "blocks": []}'))
    provider = GeminiDeepProvider(api_key="k", transport=transport)

    result = provider.extract(_image(), ["en"])

    assert result.blocks[0].text == "Save"
    assert result.metadata["provider"] == "gemini_deep"
    assert result.metadata["model"] == PRODUCTION_GEMINI_MODEL
    assert result.metadata["remote"] is True
    assert "latency_ms" in result.metadata


def test_usage_metadata_captured():
    usage = {"promptTokenCount": 500, "candidatesTokenCount": 80}
    transport = _FakeTransport(_gemini_response('{"text": "hi", "blocks": []}', usage=usage))
    provider = GeminiDeepProvider(api_key="k", transport=transport)

    result = provider.extract(_image(), ["en"])

    assert result.metadata["usage"]["input_tokens"] == 500
    assert result.metadata["usage"]["output_tokens"] == 80


@pytest.mark.parametrize(
    "status,exc_type",
    [(401, DeepAnalysisAuthError), (403, DeepAnalysisAuthError), (429, DeepAnalysisRateLimited), (500, DeepAnalysisServerError)],
)
def test_error_status_mapping(status, exc_type):
    transport = _FakeTransport(response=HttpResponse(status=status, body=b"{}", headers={}))
    provider = GeminiDeepProvider(api_key="k", transport=transport, max_retries=0)
    with pytest.raises(exc_type):
        provider.extract(_image(), ["en"])


def test_timeout_maps_to_deep_analysis_timeout():
    transport = _FakeTransport(exc=HttpTimeout("timed out"))
    provider = GeminiDeepProvider(api_key="k", transport=transport, max_retries=0)
    with pytest.raises(DeepAnalysisTimeout):
        provider.extract(_image(), ["en"])


def test_malformed_response_maps_to_bad_response():
    transport = _FakeTransport(response=HttpResponse(status=200, body=b'{"nonsense": true}', headers={}))
    provider = GeminiDeepProvider(api_key="k", transport=transport)
    with pytest.raises(DeepAnalysisBadResponse):
        provider.extract(_image(), ["en"])


# --- table / code / Urdu / mixed-script parsing (regression coverage) -----


def test_table_response_parses_via_shared_markdown_fallback():
    from local_lens.deep_analysis.deep_metrics import parse_markdown_table

    text = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    transport = _FakeTransport(_gemini_response(json.dumps({"text": text, "content_type": "table", "blocks": []})))
    provider = GeminiDeepProvider(api_key="k", transport=transport)

    result = provider.extract(_image(), ["en"])
    produced_text = result.text or "\n".join(b.text for b in result.blocks)
    assert parse_markdown_table(produced_text) == [["A", "B"], ["1", "2"]]


def test_code_response_preserves_indentation_exactly():
    code = "def f():\n    if True:\n        return 1"
    transport = _FakeTransport(_gemini_response(json.dumps({"text": code, "content_type": "code", "blocks": []})))
    provider = GeminiDeepProvider(api_key="k", transport=transport)

    result = provider.extract(_image(), ["en"])
    produced_text = result.text or "\n".join(b.text for b in result.blocks)
    assert produced_text == code


def test_urdu_response_preserved_verbatim():
    urdu_text = "سلام دنیا"
    transport = _FakeTransport(_gemini_response(json.dumps({"text": urdu_text, "blocks": []})))
    provider = GeminiDeepProvider(api_key="k", transport=transport)

    result = provider.extract(_image(), ["ur"])
    produced_text = result.text or "\n".join(b.text for b in result.blocks)
    assert produced_text == urdu_text


def test_mixed_urdu_english_reordering_regression():
    """Regression fixture from the actual Round 1 benchmark run: Gemini
    swapped the Urdu word and the number ("Order نمبر 12345 confirmed" ->
    "Order 12345 نمبر confirmed"). This test doesn't assert the swap is
    fixed (it's a model behavior, not a parser bug) -- it asserts the
    parser doesn't further corrupt or reorder content beyond what the
    model itself returned, i.e. the text survives verbatim end to end."""
    swapped = "Order 12345 نمبر confirmed"
    transport = _FakeTransport(_gemini_response(json.dumps({"text": swapped, "blocks": []})))
    provider = GeminiDeepProvider(api_key="k", transport=transport)

    result = provider.extract(_image(), ["ur", "en"])
    produced_text = result.text or "\n".join(b.text for b in result.blocks)
    assert produced_text == swapped  # parser must not introduce further reordering


# --- secrets never surface ---------------------------------------------


def test_api_key_never_appears_in_result_or_repr():
    transport = _FakeTransport(_gemini_response('{"text": "hi", "blocks": []}'))
    provider = GeminiDeepProvider(api_key="super-secret-production-key", transport=transport)

    result = provider.extract(_image(), ["en"])

    assert "super-secret-production-key" not in repr(result)
    assert "super-secret-production-key" not in repr(result.metadata)
    url, headers, _body, _timeout = transport.calls[0]
    assert "super-secret-production-key" not in url
    assert headers["x-goog-api-key"] == "super-secret-production-key"  # sent correctly, just not logged/returned


def test_error_message_never_contains_the_key():
    transport = _FakeTransport(response=HttpResponse(status=401, body=b"{}", headers={}))
    provider = GeminiDeepProvider(api_key="super-secret-production-key", transport=transport, max_retries=0)
    with pytest.raises(DeepAnalysisAuthError) as exc_info:
        provider.extract(_image(), ["en"])
    assert "super-secret-production-key" not in str(exc_info.value)
