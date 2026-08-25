"""Tests for the provider-independent Deep Analyze benchmark contract:
cost estimation, the extra_content_rate fidelity signal, benchmark case
construction (reuses the existing corpus, materializes fixtures locally,
no network), config validation, and the shared structured-reply parser.
All offline -- nothing here makes an HTTP request."""

from __future__ import annotations

from pathlib import Path

from local_lens.deep_analysis.benchmark import (
    DeepBenchmarkCase,
    DeepBenchmarkResult,
    TokenPricing,
    estimate_request_cost,
    extra_content_rate,
)
from local_lens.deep_analysis.config import validate_deep_provider_config
from local_lens.deep_analysis.response_parsing import parse_structured_reply

# --- cost estimation ---------------------------------------------------


def test_estimate_request_cost_basic():
    pricing = TokenPricing(input_per_million=1.0, output_per_million=2.0)
    cost = estimate_request_cost(pricing, estimated_input_tokens=1_000_000, estimated_output_tokens=500_000)
    assert cost == 2.0  # 1.0 (input) + 1.0 (output)


def test_estimate_request_cost_zero_pricing():
    pricing = TokenPricing(input_per_million=0.0, output_per_million=0.0)
    assert estimate_request_cost(pricing, 1000, 1000) == 0.0


# --- extra_content_rate --------------------------------------------------


def test_extra_content_rate_exact_match_is_zero():
    assert extra_content_rate("hello world", "hello world") == 0.0


def test_extra_content_rate_all_extra_is_one():
    assert extra_content_rate("hello world", "") == 1.0


def test_extra_content_rate_empty_produced_is_zero():
    assert extra_content_rate("", "hello world") == 0.0


def test_extra_content_rate_partial_extra():
    # "hello world extra" vs "hello world" -> 1 of 3 words is extra
    rate = extra_content_rate("hello world extra", "hello world")
    assert rate == round(1 / 3, 3)


def test_extra_content_rate_case_insensitive():
    assert extra_content_rate("HELLO", "hello") == 0.0


# --- benchmark case/result shape -----------------------------------------


def test_benchmark_case_defaults():
    case = DeepBenchmarkCase(id="x", category="c", image_path=Path("x.png"))
    assert case.expected_text is None
    assert case.expected_table is None
    assert case.languages == []


def test_benchmark_result_failure_shape():
    result = DeepBenchmarkResult(
        case_id="x", provider="p", model="m", latency_ms=10.0, success=False, error="timeout"
    )
    assert result.success is False
    assert result.text == ""
    assert result.parsed_result is None


# --- provider config validation (offline, no network) ---------------------


def test_validate_config_unconfigured():
    problems = validate_deep_provider_config(env={})
    assert problems and "not configured" in problems[0]


def test_validate_config_valid_openai_compatible():
    env = {
        "LOCAL_LENS_DEEP_BASE_URL": "https://example.com/v1",
        "LOCAL_LENS_DEEP_API_KEY": "key",
        "LOCAL_LENS_DEEP_MODEL": "gpt-4o-mini",
    }
    assert validate_deep_provider_config(env=env) == []


def test_validate_config_flags_missing_api_key():
    env = {"LOCAL_LENS_DEEP_BASE_URL": "https://example.com/v1"}
    problems = validate_deep_provider_config(env=env)
    assert any("API key" in p for p in problems)


def test_validate_config_paddle_vllm_does_not_require_api_key():
    env = {
        "LOCAL_LENS_DEEP_BASE_URL": "https://vllm.example.com/v1",
        "LOCAL_LENS_DEEP_PROVIDER": "paddle-vllm",
    }
    assert validate_deep_provider_config(env=env) == []


def test_validate_config_flags_malformed_base_url():
    env = {"LOCAL_LENS_DEEP_BASE_URL": "not-a-url", "LOCAL_LENS_DEEP_API_KEY": "k"}
    problems = validate_deep_provider_config(env=env)
    assert any("valid http" in p for p in problems)


def test_anthropic_provider_uses_default_base_url_without_explicit_url():
    from local_lens.deep_analysis.config import load_deep_provider_config

    env = {"LOCAL_LENS_DEEP_PROVIDER": "anthropic", "LOCAL_LENS_DEEP_API_KEY": "k"}
    config = load_deep_provider_config(env=env)
    assert config is not None
    assert config.base_url == "https://api.anthropic.com/v1"
    assert config.model == "claude-sonnet-5"


# --- shared structured-reply parser ---------------------------------------


def test_parse_structured_reply_valid_json():
    reply = '{"text": "hi", "content_type": "text", "blocks": [{"type": "text", "text": "hi"}]}'
    parsed = parse_structured_reply(reply)
    assert parsed.structured is True
    assert parsed.blocks[0].text == "hi"
    assert parsed.content_type == "text"


def test_parse_structured_reply_falls_back_on_non_json():
    parsed = parse_structured_reply("not json at all")
    assert parsed.structured is False
    assert parsed.blocks[0].text == "not json at all"


def test_parse_structured_reply_uses_languages_list_when_language_missing():
    reply = '{"text": "x", "languages": ["ur", "en"], "blocks": []}'
    parsed = parse_structured_reply(reply)
    assert parsed.language == "ur"
