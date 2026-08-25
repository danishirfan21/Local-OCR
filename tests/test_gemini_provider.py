"""GeminiProvider tests against a fake transport -- confirms the native
adapter's request shape (not the OpenAI-compat beta layer), the
x-goog-api-key header (never a `?key=` URL param), usage extraction, and
error mapping. No real network call."""

from __future__ import annotations

import json

import pytest
from PIL import Image

from local_lens.deep_analysis.base import DeepAnalysisAuthError, DeepAnalysisBadResponse, DeepAnalysisRateLimited
from local_lens.deep_analysis.gemini_provider import GeminiProvider
from local_lens.deep_analysis.http_client import HttpResponse


def _image() -> Image.Image:
    return Image.new("RGB", (10, 10), "white")


class _FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls: list[tuple] = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, body, timeout))
        return self.response


def _gemini_response(text: str, usage: dict | None = None) -> HttpResponse:
    payload = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    if usage:
        payload["usageMetadata"] = usage
    return HttpResponse(status=200, body=json.dumps(payload).encode("utf-8"), headers={})


def test_uses_x_goog_api_key_header_not_url_param():
    transport = _FakeTransport(_gemini_response('{"text": "hi", "blocks": []}'))
    provider = GeminiProvider(api_key="secret-key", model="gemini-2.5-flash-lite", transport=transport)

    provider.extract(_image(), ["en"])

    url, headers, _body, _timeout = transport.calls[0]
    assert "secret-key" not in url
    assert headers["x-goog-api-key"] == "secret-key"
    assert "key=" not in url


def test_model_and_action_in_url_path():
    transport = _FakeTransport(_gemini_response('{"text": "hi", "blocks": []}'))
    provider = GeminiProvider(api_key="k", model="gemini-2.5-flash-lite", transport=transport)

    provider.extract(_image(), ["en"])

    url, _headers, _body, _timeout = transport.calls[0]
    assert url.endswith("/models/gemini-2.5-flash-lite:generateContent")


def test_request_uses_inline_data_image_shape():
    transport = _FakeTransport(_gemini_response('{"text": "hi", "blocks": []}'))
    provider = GeminiProvider(api_key="k", transport=transport)

    provider.extract(_image(), ["en"])

    _url, _headers, body, _timeout = transport.calls[0]
    payload = json.loads(body)
    parts = payload["contents"][0]["parts"]
    image_part = next(p for p in parts if "inline_data" in p)
    assert image_part["inline_data"]["mime_type"] == "image/png"
    assert "image_url" not in image_part


def test_usage_metadata_extracted():
    usage = {"promptTokenCount": 120, "candidatesTokenCount": 40}
    transport = _FakeTransport(_gemini_response('{"text": "hi", "blocks": []}', usage=usage))
    provider = GeminiProvider(api_key="k", transport=transport)

    result = provider.extract(_image(), ["en"])

    assert result.metadata["usage"]["input_tokens"] == 120
    assert result.metadata["usage"]["output_tokens"] == 40


def test_401_maps_to_auth_error():
    transport = _FakeTransport(HttpResponse(status=401, body=b"{}", headers={}))
    provider = GeminiProvider(api_key="bad", transport=transport, max_retries=0)
    with pytest.raises(DeepAnalysisAuthError):
        provider.extract(_image(), ["en"])


def test_429_maps_to_rate_limited():
    transport = _FakeTransport(HttpResponse(status=429, body=b"{}", headers={}))
    provider = GeminiProvider(api_key="k", transport=transport, max_retries=0)
    with pytest.raises(DeepAnalysisRateLimited):
        provider.extract(_image(), ["en"])


def test_malformed_response_maps_to_bad_response():
    transport = _FakeTransport(HttpResponse(status=200, body=b'{"unexpected": true}', headers={}))
    provider = GeminiProvider(api_key="k", transport=transport)
    with pytest.raises(DeepAnalysisBadResponse):
        provider.extract(_image(), ["en"])
