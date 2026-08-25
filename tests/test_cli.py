"""CLI tests -- Fast-mode extraction is exercised with a fake engine (no
real EasyOCR model load, to keep the suite fast); Deep-mode-unconfigured
and `doctor` are exercised for real since they only touch config/env, not
the network or a model."""

from __future__ import annotations

import io

import pytest
from PIL import Image

import local_lens.cli as cli
from local_lens.services.ocr_service import OCRService
from tests.test_engines import FakeEngine


@pytest.fixture
def fake_image(tmp_path):
    path = tmp_path / "sample.png"
    Image.new("RGB", (20, 20), "white").save(path)
    return path


@pytest.fixture(autouse=True)
def _fake_fast_service(monkeypatch):
    monkeypatch.setattr(cli, "_build_fast_service", lambda engine_name: OCRService(FakeEngine()))


def test_extract_fast_mode_prints_text(fake_image, capsys):
    exit_code = cli.main(["extract", str(fake_image), "--mode", "fast", "--format", "text"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "fake" in out


def test_extract_missing_file_returns_error(capsys):
    exit_code = cli.main(["extract", "does-not-exist.png"])
    assert exit_code == 1
    assert "no such file" in capsys.readouterr().err


def test_extract_deep_mode_unconfigured_raises_clear_error(fake_image, monkeypatch):
    monkeypatch.delenv("LOCAL_LENS_DEEP_BASE_URL", raising=False)
    with pytest.raises(SystemExit, match="not configured"):
        cli.main(["extract", str(fake_image), "--mode", "deep"])


def test_extract_json_format(fake_image, capsys):
    exit_code = cli.main(["extract", str(fake_image), "--format", "json"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert '"engine"' in out


def test_doctor_reports_easyocr_available(capsys):
    exit_code = cli.main(["doctor"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "easyocr" in out
    assert "Deep Analyze" in out


def test_no_args_exits_nonzero():
    with pytest.raises(SystemExit):
        cli.main([])


def test_providers_reports_unconfigured_deep_by_default(capsys, monkeypatch):
    monkeypatch.delenv("LOCAL_LENS_DEEP_BASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_LENS_DEEP_PROVIDER", raising=False)
    exit_code = cli.main(["providers"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Fast / easyocr" in out
    assert "not configured" in out


def test_providers_reports_configured_deep_without_network_call(capsys, monkeypatch):
    monkeypatch.setenv("LOCAL_LENS_DEEP_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LOCAL_LENS_DEEP_API_KEY", "k")
    exit_code = cli.main(["providers"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "not tested (no network call made)" in out


def test_benchmark_deep_requires_a_mode_flag(capsys):
    exit_code = cli.main(["benchmark-deep"])
    assert exit_code == 1
    assert "choose one of" in capsys.readouterr().err


def test_benchmark_deep_rejects_multiple_mode_flags(capsys):
    exit_code = cli.main(["benchmark-deep", "--dry-run", "--preflight"])
    assert exit_code == 1
    assert "only one of" in capsys.readouterr().err


def test_benchmark_deep_preflight_makes_no_network_call(capsys, monkeypatch):
    import urllib.request

    def _forbidden(*args, **kwargs):
        raise AssertionError("preflight must not open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)

    exit_code = cli.main(["benchmark-deep", "--preflight"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Fixtures: 12" in out
    assert "No requests sent." in out
    assert "Total executable requests:" in out


def test_benchmark_deep_run_requires_confirm_remote(capsys):
    exit_code = cli.main(["benchmark-deep", "--run", "--max-cost-usd", "0.25"])
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "requires --confirm-remote" in err
    assert "No requests were sent." in err


def test_benchmark_deep_run_requires_max_cost_usd(capsys):
    exit_code = cli.main(["benchmark-deep", "--run", "--confirm-remote"])
    assert exit_code == 1
    assert "requires --max-cost-usd" in capsys.readouterr().err


def test_benchmark_deep_run_aborts_when_estimate_exceeds_ceiling(capsys, monkeypatch):
    monkeypatch.setenv("LOCAL_LENS_BENCHMARK_OPENAI_API_KEY", "x")
    exit_code = cli.main(["benchmark-deep", "--run", "--confirm-remote", "--max-cost-usd", "0.0001"])
    assert exit_code == 1
    out = capsys.readouterr()
    assert "ABORTED" in out.err
    assert "No requests sent." in out.err
    assert "Estimated maximum:" in out.out


def test_benchmark_deep_run_with_nothing_configured_makes_no_network_call(capsys, monkeypatch):
    import urllib.request

    def _forbidden(*args, **kwargs):
        raise AssertionError("must not open a network connection when nothing is configured")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    for var in [
        "LOCAL_LENS_BENCHMARK_OPENAI_API_KEY",
        "LOCAL_LENS_BENCHMARK_GEMINI_API_KEY",
        "LOCAL_LENS_BENCHMARK_ANTHROPIC_API_KEY",
        "LOCAL_LENS_BENCHMARK_FIREWORKS_API_KEY",
    ]:
        monkeypatch.delenv(var, raising=False)

    exit_code = cli.main(["benchmark-deep", "--run", "--confirm-remote", "--max-cost-usd", "10.0"])
    assert exit_code == 1
    assert "No configured, executable finalists" in capsys.readouterr().err


def test_benchmark_deep_dry_run_makes_no_network_call(capsys, monkeypatch):
    import urllib.request

    def _forbidden(*args, **kwargs):
        raise AssertionError("dry-run must not open a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)

    exit_code = cli.main(["benchmark-deep", "--dry-run"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "Total requests if fully executed:" in out
    assert "No network call was made." in out
