"""Tests for the real benchmark executor (local_lens/deep_analysis/runner.py).

Every test here either makes zero network calls (preflight) or injects a
fake-transport-backed provider via `provider_overrides` (execution) --
nothing in this file makes a real HTTP request. This is the test suite
that stands in for actually running the bake-off: it proves the
orchestration, safety gates, and result capture all work correctly before
a single real request would ever be made.
"""

from __future__ import annotations

import json

import pytest
from PIL import Image

from local_lens.deep_analysis.base import DeepAnalysisAuthError, DeepAnalysisBadResponse, DeepAnalysisTimeout
from local_lens.deep_analysis.http_client import HttpResponse
from local_lens.deep_analysis.runner import (
    BudgetExceeded,
    NoExecutableFinalists,
    execute_benchmark,
    run_preflight,
)


def _image() -> Image.Image:
    return Image.new("RGB", (10, 10), "white")


class _FakeProvider:
    """Stands in for any DeepAnalysisProvider -- raises/returns whatever
    the test configures, tracks call count, never touches the network."""

    def __init__(self, responses=None, exc=None, exc_sequence=None):
        self.responses = responses if responses is not None else []
        self.exc = exc
        self.exc_sequence = list(exc_sequence) if exc_sequence else None
        self.calls = 0

    def extract(self, image, langs):
        self.calls += 1
        if self.exc_sequence:
            exc = self.exc_sequence.pop(0)
            if exc is not None:
                raise exc
        elif self.exc is not None:
            raise self.exc

        from local_lens.models import DocumentResult, TextBlock

        text = self.responses[min(self.calls - 1, len(self.responses) - 1)] if self.responses else "hi"
        return DocumentResult(
            text="",
            blocks=[TextBlock(text=text, confidence=None, bbox=None)],
            language="en",
            engine="fake",
            metadata={"provider": "fake", "remote": True, "http_status": 200, "usage": {"input_tokens": 10, "output_tokens": 5}},
        )


# --- preflight (zero network) -----------------------------------------


def test_preflight_reports_unconfigured_when_no_env():
    report = run_preflight(env={})
    assert report.fixture_count == 12
    assert report.total_executable_requests == 0
    assert all(not f.executable for f in report.finalists)


def test_preflight_reports_paddle_vl_never_executable():
    report = run_preflight(env={"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"})
    paddle = next(f for f in report.finalists if "PaddleOCR" in f.label)
    assert paddle.executable is False
    assert "historical" in paddle.unavailable_reason or "hosting pending" in paddle.unavailable_reason


def test_preflight_reports_executable_when_configured():
    report = run_preflight(env={"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"})
    openai = next(f for f in report.finalists if f.label == "OpenAI GPT-5")
    assert openai.configured is True
    assert openai.executable is True
    assert openai.requests == 12
    assert openai.estimated_max_cost_usd > 0


def test_preflight_treats_placeholder_as_unconfigured():
    report = run_preflight(env={"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "changeme"})
    openai = next(f for f in report.finalists if f.label == "OpenAI GPT-5")
    assert openai.configured is False


def test_preflight_includes_gemini_privacy_warning_only_when_gemini_configured():
    report_without = run_preflight(env={"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"})
    assert not any("Gemini" in w for w in report_without.warnings)

    report_with = run_preflight(env={"LOCAL_LENS_BENCHMARK_GEMINI_API_KEY": "x"})
    assert any("Gemini" in w and "free-tier" in w for w in report_with.warnings)


def test_preflight_makes_zero_network_calls(monkeypatch):
    import urllib.request

    def _forbidden(*args, **kwargs):
        raise AssertionError("preflight must not open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    run_preflight(env={"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x", "LOCAL_LENS_BENCHMARK_GEMINI_API_KEY": "x"})


# --- execute_benchmark gating --------------------------------------------


def test_execute_benchmark_refuses_without_confirm_remote(tmp_path):
    with pytest.raises(PermissionError):
        execute_benchmark(max_cost_usd=1.0, output_dir=tmp_path, confirm_remote=False)


def test_execute_benchmark_raises_budget_exceeded(tmp_path):
    env = {"LOCAL_LENS_BENCHMARK_ANTHROPIC_API_KEY": "x"}  # priciest finalist
    with pytest.raises(BudgetExceeded):
        execute_benchmark(max_cost_usd=0.001, output_dir=tmp_path, env=env, confirm_remote=True)


def test_execute_benchmark_raises_when_nothing_configured(tmp_path):
    with pytest.raises(NoExecutableFinalists):
        execute_benchmark(max_cost_usd=10.0, output_dir=tmp_path, env={}, confirm_remote=True)


# --- execute_benchmark real orchestration (fake provider) -----------------


def test_execute_benchmark_runs_all_cases_serially(tmp_path):
    env = {"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"}
    fake = _FakeProvider()
    summary = execute_benchmark(
        max_cost_usd=10.0, output_dir=tmp_path, env=env, confirm_remote=True,
        provider_overrides={"OpenAI GPT-5": fake},
    )
    assert fake.calls == 12
    assert len(summary.results) == 12
    assert all(r.success for r in summary.results)
    assert summary.aborted is False


def test_execute_benchmark_writes_manifest_and_results(tmp_path):
    env = {"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"}
    fake = _FakeProvider()
    summary = execute_benchmark(
        max_cost_usd=10.0, output_dir=tmp_path, env=env, confirm_remote=True,
        provider_overrides={"OpenAI GPT-5": fake},
    )
    assert summary.manifest_path.exists()
    manifest = json.loads(summary.manifest_path.read_text())
    assert manifest["case_count"] == 12

    results_path = summary.output_dir / "results.json"
    assert results_path.exists()
    results = json.loads(results_path.read_text())
    assert len(results) == 12


def test_execute_benchmark_raw_output_contains_no_secrets(tmp_path):
    env = {"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "super-secret-value"}
    fake = _FakeProvider()
    summary = execute_benchmark(
        max_cost_usd=10.0, output_dir=tmp_path, env=env, confirm_remote=True,
        provider_overrides={"OpenAI GPT-5": fake},
    )
    raw_dir = summary.output_dir / "raw"
    raw_files = list(raw_dir.glob("*.json"))
    assert raw_files
    for f in raw_files:
        content = f.read_text()
        assert "super-secret-value" not in content
        assert "api_key" not in content
        assert "Authorization" not in content


def test_execute_benchmark_drops_finalist_after_consecutive_auth_failures(tmp_path):
    env = {"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"}
    fake = _FakeProvider(exc=DeepAnalysisAuthError("bad key"))
    summary = execute_benchmark(
        max_cost_usd=10.0, output_dir=tmp_path, env=env, confirm_remote=True,
        provider_overrides={"OpenAI GPT-5": fake},
    )
    assert "OpenAI GPT-5" in summary.dropped_finalists
    # dropped after 2 consecutive failures -- must not have kept calling
    # for all 12 cases once it was dropped.
    assert fake.calls == 2
    assert summary.aborted is True  # the only configured finalist was dropped
    assert "auth" in summary.abort_reason.lower() or "dropped" in str(summary.dropped_finalists)


def test_execute_benchmark_drops_finalist_after_consecutive_malformed_responses(tmp_path):
    env = {"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"}
    fake = _FakeProvider(exc=DeepAnalysisBadResponse("garbage"))
    summary = execute_benchmark(
        max_cost_usd=10.0, output_dir=tmp_path, env=env, confirm_remote=True,
        provider_overrides={"OpenAI GPT-5": fake},
    )
    assert "OpenAI GPT-5" in summary.dropped_finalists
    assert fake.calls == 3


def test_execute_benchmark_records_generic_error_without_dropping_immediately(tmp_path):
    env = {"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"}
    fake = _FakeProvider(exc=DeepAnalysisTimeout("timed out"))
    summary = execute_benchmark(
        max_cost_usd=10.0, output_dir=tmp_path, env=env, confirm_remote=True,
        provider_overrides={"OpenAI GPT-5": fake},
    )
    # timeouts aren't in the auth/malformed drop-tracking, so all 12 cases
    # are attempted and all fail, but the finalist isn't dropped mid-run.
    assert fake.calls == 12
    assert all(not r.success for r in summary.results)
    assert "OpenAI GPT-5" not in summary.dropped_finalists


def test_execute_benchmark_aborts_mid_run_when_accumulated_cost_exceeds_ceiling(tmp_path):
    from local_lens.deep_analysis.finalists import ESTIMATED_INPUT_TOKENS_PER_REQUEST, ESTIMATED_OUTPUT_TOKENS_PER_REQUEST
    from local_lens.deep_analysis.benchmark import estimate_request_cost
    from local_lens.deep_analysis.finalists import FINALISTS
    from local_lens.models import DocumentResult, TextBlock

    fc = next(f for f in FINALISTS if f.label == "OpenAI GPT-5")
    preflight_per_request = estimate_request_cost(
        fc.pricing, ESTIMATED_INPUT_TOKENS_PER_REQUEST, ESTIMATED_OUTPUT_TOKENS_PER_REQUEST
    )
    ceiling = preflight_per_request * 12  # exactly the preflight's upfront estimate -- passes the upfront gate

    class _ExpensiveProvider:
        """Reports real usage far above the conservative preflight
        estimate, so accumulated ACTUAL cost exceeds the ceiling after the
        very first request even though the ceiling passed the upfront
        preflight check."""

        def __init__(self):
            self.calls = 0

        def extract(self, image, langs):
            self.calls += 1
            return DocumentResult(
                text="",
                blocks=[TextBlock(text="hi", confidence=None, bbox=None)],
                language="en",
                engine="fake",
                metadata={
                    "provider": "fake", "remote": True, "http_status": 200,
                    "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
                },
            )

    env = {"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"}
    fake = _ExpensiveProvider()
    summary = execute_benchmark(
        max_cost_usd=ceiling, output_dir=tmp_path, env=env, confirm_remote=True,
        provider_overrides={"OpenAI GPT-5": fake},
    )
    assert summary.aborted is True
    assert "ceiling" in summary.abort_reason
    assert fake.calls < 12


def test_execute_benchmark_scores_text_case_against_ground_truth(tmp_path):
    env = {"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"}
    fake = _FakeProvider(responses=["Save"])  # matches short_ui_save's ground truth exactly
    summary = execute_benchmark(
        max_cost_usd=10.0, output_dir=tmp_path, env=env, confirm_remote=True,
        provider_overrides={"OpenAI GPT-5": fake},
    )
    save_result = next(r for r in summary.results if r.case_id == "short_ui_save")
    assert save_result.metrics["kind"] == "text"
    assert save_result.metrics["cer"] == 0.0


def test_execute_benchmark_multiple_finalists_run_serially_case_major(tmp_path):
    env = {
        "LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x",
        "LOCAL_LENS_BENCHMARK_ANTHROPIC_API_KEY": "x",
    }
    call_order = []

    class _OrderTrackingProvider(_FakeProvider):
        def __init__(self, label):
            super().__init__()
            self.label = label

        def extract(self, image, langs):
            call_order.append(self.label)
            return super().extract(image, langs)

    openai_fake = _OrderTrackingProvider("openai")
    claude_fake = _OrderTrackingProvider("claude")
    execute_benchmark(
        max_cost_usd=10.0, output_dir=tmp_path, env=env, confirm_remote=True,
        provider_overrides={"OpenAI GPT-5": openai_fake, "Claude Sonnet 5": claude_fake},
    )
    # case-major order: both providers called for case 1 before either is
    # called for case 2.
    assert call_order[0] == "openai"
    assert call_order[1] == "claude"
    assert call_order[2] == "openai"
