"""Secret-redaction tests -- every one of these represents a way a
credential could leak into a stored benchmark artifact if this module
didn't catch it."""

from __future__ import annotations

from local_lens.deep_analysis.sanitize import (
    sanitize_error_message,
    sanitize_headers,
    sanitize_result_record,
    sanitize_url,
)


def test_sanitize_headers_redacts_authorization():
    headers = {"Authorization": "Bearer sk-real-secret", "Content-Type": "application/json"}
    sanitized = sanitize_headers(headers)
    assert sanitized["Authorization"] == "***REDACTED***"
    assert sanitized["Content-Type"] == "application/json"
    assert headers["Authorization"] == "Bearer sk-real-secret"  # input not mutated


def test_sanitize_headers_redacts_x_goog_api_key_case_insensitive():
    headers = {"X-Goog-Api-Key": "secret"}
    sanitized = sanitize_headers(headers)
    assert sanitized["X-Goog-Api-Key"] == "***REDACTED***"


def test_sanitize_url_strips_key_query_param():
    url = "https://example.com/v1/generate?key=sk-real-secret&model=x"
    sanitized = sanitize_url(url)
    assert "sk-real-secret" not in sanitized
    assert "model=x" in sanitized


def test_sanitize_error_message_redacts_bearer_token():
    msg = "request failed: Authorization: Bearer sk-abcdef123456 was rejected"
    sanitized = sanitize_error_message(msg)
    assert "sk-abcdef123456" not in sanitized


def test_sanitize_result_record_drops_forbidden_keys():
    record = {"provider": "openai", "api_key": "sk-secret", "headers": {"Authorization": "x"}, "case_id": "c1"}
    sanitized = sanitize_result_record(record)
    assert "api_key" not in sanitized
    assert "headers" not in sanitized
    assert sanitized["provider"] == "openai"
    assert sanitized["case_id"] == "c1"


def test_sanitize_result_record_sanitizes_error_field():
    record = {"error": "auth failed: Bearer sk-real-secret-value"}
    sanitized = sanitize_result_record(record)
    assert "sk-real-secret-value" not in sanitized["error"]
