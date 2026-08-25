"""Tests for the free-first benchmark round: Groq config/serialization,
free-tier cost classification, round filtering, paid-candidate exclusion
from the free round, and the extra --free-tier-only execution safety gate.
Every test here is offline -- no real network call."""

from __future__ import annotations

from local_lens.deep_analysis.finalists import (
    FINALISTS,
    build_provider_for_finalist,
    credential_configured,
    finalists_for_round,
)
from local_lens.deep_analysis.openai_compatible_provider import OpenAICompatibleVisionProvider
from local_lens.deep_analysis.runner import execute_benchmark, run_preflight

# --- registry shape -----------------------------------------------------


def test_groq_is_in_the_free_round():
    groq = next(fc for fc in FINALISTS if "Groq" in fc.label)
    assert groq.round == "free"
    assert groq.cost_classification == "zero_cost_eligible"
    assert groq.model == "qwen/qwen3.6-27b"
    assert groq.base_url == "https://api.groq.com/openai/v1"
    assert groq.credential_env_var == "LOCAL_LENS_BENCHMARK_GROQ_API_KEY"


def test_gemini_uses_current_non_deprecated_model():
    gemini = next(fc for fc in FINALISTS if "Gemini" in fc.label)
    assert gemini.model == "gemini-3.1-flash-lite"
    assert gemini.round == "free"
    assert gemini.cost_classification == "zero_cost_eligible"


def test_hf_is_not_in_the_registry():
    # Deliberately excluded from Round 1 -- see docs/DEEP_PROVIDER_EVALUATION.md
    # "Free-first strategy" (only $0.10/month free credit, unconfirmed
    # per-request pricing, real risk of exhausting it within 12 requests).
    assert not any("Hugging Face" in fc.label or fc.provider_kind == "huggingface" for fc in FINALISTS)


def test_paid_finalists_are_classified_paid():
    for fc in FINALISTS:
        if fc.label in ("OpenAI GPT-5", "Claude Sonnet 5", "Qwen2.5-VL-72B-Instruct (Fireworks AI)"):
            assert fc.round == "paid"
            assert fc.cost_classification == "paid"


def test_finalists_for_round_free_excludes_paid():
    free = finalists_for_round("free")
    labels = {fc.label for fc in free}
    assert "Groq Qwen3.6-27B" in labels
    assert "Gemini 3.1 Flash-Lite" in labels
    assert "OpenAI GPT-5" not in labels
    assert "Claude Sonnet 5" not in labels


def test_finalists_for_round_paid_excludes_free():
    paid = finalists_for_round("paid")
    labels = {fc.label for fc in paid}
    assert "Groq Qwen3.6-27B" not in labels
    assert "OpenAI GPT-5" in labels


# --- Groq provider construction (reuses the generic adapter) -------------


def test_groq_credential_env_var_detected():
    assert credential_configured(next(fc for fc in FINALISTS if "Groq" in fc.label), env={}) is False
    assert (
        credential_configured(
            next(fc for fc in FINALISTS if "Groq" in fc.label),
            env={"LOCAL_LENS_BENCHMARK_GROQ_API_KEY": "x"},
        )
        is True
    )


def test_groq_reuses_openai_compatible_provider_no_new_adapter():
    fc = next(fc for fc in FINALISTS if "Groq" in fc.label)
    provider = build_provider_for_finalist(fc, env={"LOCAL_LENS_BENCHMARK_GROQ_API_KEY": "x"})
    assert isinstance(provider, OpenAICompatibleVisionProvider)
    assert provider.base_url == "https://api.groq.com/openai/v1"
    assert provider.model == "qwen/qwen3.6-27b"


# --- preflight: free-tier cost classification -----------------------------


def test_preflight_free_round_excludes_paid_finalists():
    report = run_preflight(env={}, round_name="free")
    labels = {f.label for f in report.finalists}
    assert "OpenAI GPT-5" not in labels
    assert "Groq Qwen3.6-27B" in labels


def test_preflight_zero_cost_eligible_never_counts_toward_ceiling():
    env = {"LOCAL_LENS_BENCHMARK_GROQ_API_KEY": "x", "LOCAL_LENS_BENCHMARK_GEMINI_API_KEY": "x"}
    report = run_preflight(env=env, round_name="free")
    assert report.total_executable_requests == 24
    assert report.estimated_max_cost_usd == 0.0  # both finalists are zero_cost_eligible

    for f in report.finalists:
        assert f.expected_actual_charge_usd == 0.0
        assert f.nominal_cost_usd == 0.0  # Groq/Gemini free-tier pricing is recorded as $0 nominal


def test_preflight_within_free_tier_request_limit_true_for_12_cases():
    env = {"LOCAL_LENS_BENCHMARK_GROQ_API_KEY": "x"}
    report = run_preflight(env=env, round_name="free")
    groq = next(f for f in report.finalists if "Groq" in f.label)
    assert groq.within_free_tier_request_limit is True  # 12 requests << documented RPD of 1000


def test_preflight_paid_round_still_counts_nominal_cost():
    env = {"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"}
    report = run_preflight(env=env, round_name="paid")
    openai = next(f for f in report.finalists if f.label == "OpenAI GPT-5")
    assert openai.expected_actual_charge_usd == openai.nominal_cost_usd
    assert report.estimated_max_cost_usd > 0


def test_preflight_free_round_makes_zero_network_calls(monkeypatch):
    import urllib.request

    def _forbidden(*args, **kwargs):
        raise AssertionError("preflight must not open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    run_preflight(
        env={"LOCAL_LENS_BENCHMARK_GROQ_API_KEY": "x", "LOCAL_LENS_BENCHMARK_GEMINI_API_KEY": "x"},
        round_name="free",
    )


def test_preflight_includes_groq_privacy_note_only_when_groq_configured():
    without = run_preflight(env={}, round_name="free")
    assert not any("Groq" in w for w in without.warnings)

    with_groq = run_preflight(env={"LOCAL_LENS_BENCHMARK_GROQ_API_KEY": "x"}, round_name="free")
    assert any("Groq" in w and "not retained" in w for w in with_groq.warnings)


# --- execute_benchmark: --free-tier-only gating ---------------------------


def test_execute_benchmark_free_round_requires_free_tier_only(tmp_path):
    import pytest

    with pytest.raises(PermissionError, match="free_tier_only"):
        execute_benchmark(
            max_cost_usd=0.0, output_dir=tmp_path, env={"LOCAL_LENS_BENCHMARK_GROQ_API_KEY": "x"},
            confirm_remote=True, round_name="free", free_tier_only=False,
        )


def test_execute_benchmark_free_round_zero_ceiling_is_satisfiable(tmp_path):
    from local_lens.models import DocumentResult, TextBlock

    class _FakeProvider:
        def extract(self, image, langs):
            return DocumentResult(
                text="", blocks=[TextBlock(text="hi", confidence=None, bbox=None)],
                language="en", engine="fake", metadata={"provider": "fake", "http_status": 200},
            )

    env = {"LOCAL_LENS_BENCHMARK_GROQ_API_KEY": "x"}
    summary = execute_benchmark(
        max_cost_usd=0.00,  # a strict $0.00 ceiling
        output_dir=tmp_path,
        env=env,
        confirm_remote=True,
        round_name="free",
        free_tier_only=True,
        provider_overrides={"Groq Qwen3.6-27B": _FakeProvider()},
    )
    assert summary.aborted is False
    assert len(summary.results) == 12
    assert summary.total_estimated_cost_usd == 0.0


def test_execute_benchmark_paid_finalist_never_exempted_from_ceiling(tmp_path):
    import pytest

    from local_lens.deep_analysis.runner import BudgetExceeded

    env = {"LOCAL_LENS_BENCHMARK_OPENAI_API_KEY": "x"}
    with pytest.raises(BudgetExceeded):
        execute_benchmark(
            max_cost_usd=0.00, output_dir=tmp_path, env=env, confirm_remote=True, round_name="paid",
        )
