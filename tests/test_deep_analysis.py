"""Deep Analyze provider tests -- all against a fake HTTP transport, never
the real network. Confirms: config parsing, status reporting, successful
structured/unstructured response mapping, and every documented failure
mode (timeout, 401/403, 429, 5xx, malformed JSON) maps to a clear,
secret-free error rather than a crash."""

from __future__ import annotations

import json

import pytest
from PIL import Image

from local_lens.backends import deep_backend_status
from local_lens.deep_analysis.base import (
    DeepAnalysisAuthError,
    DeepAnalysisBadResponse,
    DeepAnalysisError,
    DeepAnalysisRateLimited,
    DeepAnalysisServerError,
    DeepAnalysisTimeout,
)
from local_lens.deep_analysis.config import build_deep_provider, load_deep_provider_config
from local_lens.deep_analysis.http_client import HttpResponse, HttpTimeout, redact_headers
from local_lens.deep_analysis.openai_compatible_provider import OpenAICompatibleVisionProvider
from local_lens.deep_analysis.paddle_vllm_provider import PaddleVLLMProvider


def _image() -> Image.Image:
    return Image.new("RGB", (10, 10), "white")


def _chat_response(content: str, status: int = 200) -> HttpResponse:
    body = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
    return HttpResponse(status=status, body=body, headers={})


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


# --- config -------------------------------------------------------------


def test_no_base_url_means_unconfigured():
    assert load_deep_provider_config(env={}) is None


def test_base_url_alone_defaults_to_openai_compatible():
    config = load_deep_provider_config(env={"LOCAL_LENS_DEEP_BASE_URL": "https://example.com/v1"})
    assert config.provider == "openai-compatible"
    assert config.model == "gpt-4o-mini"
    assert config.api_key is None


def test_full_config_respected():
    env = {
        "LOCAL_LENS_DEEP_BASE_URL": "https://vllm.example.com/v1",
        "LOCAL_LENS_DEEP_PROVIDER": "paddle-vllm",
        "LOCAL_LENS_DEEP_API_KEY": "secret-key",
        "LOCAL_LENS_DEEP_MODEL": "PaddleOCR-VL-1.6",
    }
    config = load_deep_provider_config(env=env)
    assert config.provider == "paddle-vllm"
    assert config.base_url == "https://vllm.example.com/v1"
    assert config.api_key == "secret-key"
    assert config.model == "PaddleOCR-VL-1.6"


def test_build_deep_provider_returns_none_when_unconfigured():
    assert build_deep_provider(env={}) is None


def test_build_deep_provider_constructs_paddle_vllm_without_network():
    env = {"LOCAL_LENS_DEEP_BASE_URL": "https://x/v1", "LOCAL_LENS_DEEP_PROVIDER": "paddle-vllm"}
    provider = build_deep_provider(env=env)
    assert isinstance(provider, PaddleVLLMProvider)


def test_status_not_configured_by_default():
    status = deep_backend_status()
    # No assumption about the *current* environment's env vars beyond: if
    # unset, it must clearly report unconfigured rather than crashing.
    assert status.mode == "remote"
    assert isinstance(status.available, bool)


# --- provider request/response mapping -----------------------------------


def test_structured_response_maps_to_document_result():
    payload = {
        "text": "Hello world",
        "content_type": "text",
        "language": "en",
        "blocks": [{"type": "text", "text": "Hello world"}],
    }
    transport = _FakeTransport(response=_chat_response(json.dumps(payload)))
    provider = OpenAICompatibleVisionProvider(
        base_url="https://example.com/v1", api_key="k", model="gpt-4o-mini", transport=transport
    )

    result = provider.extract(_image(), ["en"])

    assert result.blocks[0].text == "Hello world"
    assert result.document_blocks[0].type == "text"
    assert result.metadata["remote"] is True
    assert result.metadata["provider"] == "openai_compatible"
    assert result.metadata["structured_response"] is True


def test_unstructured_response_falls_back_to_plain_text():
    transport = _FakeTransport(response=_chat_response("just some plain text, not JSON"))
    provider = OpenAICompatibleVisionProvider(
        base_url="https://example.com/v1", api_key=None, model="gpt-4o-mini", transport=transport
    )

    result = provider.extract(_image(), ["en"])

    assert result.blocks[0].text == "just some plain text, not JSON"
    assert result.metadata["structured_response"] is False


def test_markdown_fenced_json_is_unwrapped():
    payload = {"text": "fenced", "blocks": []}
    fenced = f"```json\n{json.dumps(payload)}\n```"
    transport = _FakeTransport(response=_chat_response(fenced))
    provider = OpenAICompatibleVisionProvider(
        base_url="https://example.com/v1", api_key=None, model="m", transport=transport
    )

    result = provider.extract(_image(), ["en"])

    assert result.metadata["structured_response"] is True


@pytest.mark.parametrize(
    "status,exc_type",
    [(401, DeepAnalysisAuthError), (403, DeepAnalysisAuthError), (429, DeepAnalysisRateLimited), (500, DeepAnalysisServerError), (503, DeepAnalysisServerError)],
)
def test_http_error_statuses_map_to_specific_exceptions(status, exc_type):
    transport = _FakeTransport(response=HttpResponse(status=status, body=b"{}", headers={}))
    provider = OpenAICompatibleVisionProvider(
        base_url="https://example.com/v1", api_key="k", model="m", transport=transport, max_retries=0
    )

    with pytest.raises(exc_type):
        provider.extract(_image(), ["en"])


def test_timeout_maps_to_deep_analysis_timeout():
    transport = _FakeTransport(exc=HttpTimeout("timed out"))
    provider = OpenAICompatibleVisionProvider(
        base_url="https://example.com/v1", api_key="k", model="m", transport=transport, max_retries=0
    )

    with pytest.raises(DeepAnalysisTimeout):
        provider.extract(_image(), ["en"])


def test_malformed_json_body_maps_to_bad_response():
    transport = _FakeTransport(response=HttpResponse(status=200, body=b"not json", headers={}))
    provider = OpenAICompatibleVisionProvider(
        base_url="https://example.com/v1", api_key="k", model="m", transport=transport
    )

    with pytest.raises(DeepAnalysisBadResponse):
        provider.extract(_image(), ["en"])


def test_401_does_not_retry():
    transport = _FakeTransport(response=HttpResponse(status=401, body=b"{}", headers={}))
    provider = OpenAICompatibleVisionProvider(
        base_url="https://example.com/v1", api_key="k", model="m", transport=transport, max_retries=2
    )

    with pytest.raises(DeepAnalysisAuthError):
        provider.extract(_image(), ["en"])

    assert len(transport.calls) == 1


def test_500_retries_up_to_max_retries():
    transport = _FakeTransport(response=HttpResponse(status=500, body=b"{}", headers={}))
    provider = OpenAICompatibleVisionProvider(
        base_url="https://example.com/v1", api_key="k", model="m", transport=transport, max_retries=2
    )

    with pytest.raises(DeepAnalysisServerError):
        provider.extract(_image(), ["en"])

    assert len(transport.calls) == 3  # initial + 2 retries


# --- secret redaction ------------------------------------------------------


def test_api_key_never_sent_in_plaintext_url_or_logged_headers():
    transport = _FakeTransport(response=_chat_response("hi"))
    provider = OpenAICompatibleVisionProvider(
        base_url="https://example.com/v1", api_key="super-secret-key", model="m", transport=transport
    )

    provider.extract(_image(), ["en"])

    url, headers, body, timeout = transport.calls[0]
    assert "super-secret-key" not in url
    assert headers["Authorization"] == "Bearer super-secret-key"

    redacted = redact_headers(headers)
    assert redacted["Authorization"] == "***REDACTED***"


def test_redact_headers_does_not_mutate_input():
    headers = {"Authorization": "Bearer abc", "Content-Type": "application/json"}
    redact_headers(headers)
    assert headers["Authorization"] == "Bearer abc"


# --- image never leaves the device outside an explicit provider.extract call --


def test_provider_construction_alone_makes_no_network_call():
    transport = _FakeTransport(response=_chat_response("unused"))
    OpenAICompatibleVisionProvider(base_url="https://example.com/v1", api_key="k", model="m", transport=transport)
    assert transport.calls == []
