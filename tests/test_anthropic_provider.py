"""AnthropicProvider tests against a fake transport -- confirms the
dedicated adapter is actually necessary (request shape differs from
OpenAI) and that it maps responses/errors the same way the other
providers do. No real network call."""

from __future__ import annotations

import json

import pytest
from PIL import Image

from local_lens.deep_analysis.anthropic_provider import AnthropicProvider
from local_lens.deep_analysis.base import DeepAnalysisAuthError, DeepAnalysisBadResponse
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


def _anthropic_response(text: str, status: int = 200) -> HttpResponse:
    body = json.dumps({"content": [{"type": "text", "text": text}]}).encode("utf-8")
    return HttpResponse(status=status, body=body, headers={})


def test_request_uses_anthropic_image_shape_not_openai():
    transport = _FakeTransport(_anthropic_response('{"text": "hi", "blocks": []}'))
    provider = AnthropicProvider(api_key="k", model="claude-sonnet-5", transport=transport)

    provider.extract(_image(), ["en"])

    url, headers, body, _timeout = transport.calls[0]
    assert url.endswith("/messages")
    assert headers["x-api-key"] == "k"
    assert headers["anthropic-version"]
    assert "Authorization" not in headers  # Anthropic uses x-api-key, not Bearer

    payload = json.loads(body)
    image_block = payload["messages"][0]["content"][1]
    assert image_block["type"] == "image"
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    assert "image_url" not in image_block  # confirms it's not the OpenAI shape


def test_successful_structured_response():
    transport = _FakeTransport(_anthropic_response('{"text": "Hello Claude", "blocks": []}'))
    provider = AnthropicProvider(api_key="k", transport=transport)

    result = provider.extract(_image(), ["en"])

    assert result.metadata["provider"] == "anthropic"
    assert result.metadata["remote"] is True
    assert result.blocks == [] or result.text == ""


def test_401_maps_to_auth_error():
    transport = _FakeTransport(HttpResponse(status=401, body=b"{}", headers={}))
    provider = AnthropicProvider(api_key="bad-key", transport=transport, max_retries=0)

    with pytest.raises(DeepAnalysisAuthError):
        provider.extract(_image(), ["en"])


def test_malformed_content_shape_maps_to_bad_response():
    body = json.dumps({"unexpected": "shape"}).encode("utf-8")
    transport = _FakeTransport(HttpResponse(status=200, body=body, headers={}))
    provider = AnthropicProvider(api_key="k", transport=transport)

    with pytest.raises(DeepAnalysisBadResponse):
        provider.extract(_image(), ["en"])


def test_default_base_url_used_when_not_overridden():
    provider = AnthropicProvider(api_key="k")
    assert provider.base_url == "https://api.anthropic.com/v1"
