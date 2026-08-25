"""packaging/dist_size_report.py tests -- pure filesystem-walking logic,
no PyInstaller invocation, exercised against a synthetic tmp_path tree
rather than a real dist output."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent.parent / "packaging" / "dist_size_report.py"
_spec = importlib.util.spec_from_file_location("dist_size_report", _MODULE_PATH)
dist_size_report = importlib.util.module_from_spec(_spec)
sys.modules["dist_size_report"] = dist_size_report
_spec.loader.exec_module(dist_size_report)


def _make_fake_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "FakeApp"
    internal = dist / "_internal"
    big = internal / "big_package"
    big.mkdir(parents=True)
    (big / "weights.bin").write_bytes(b"x" * 2_000_000)  # ~2MB
    small = internal / "small_package"
    small.mkdir()
    (small / "code.py").write_bytes(b"y" * 1000)
    (internal / "FakeApp.exe").write_bytes(b"z" * 500_000)
    return dist


def test_report_lists_largest_entries_first(tmp_path):
    dist = _make_fake_dist(tmp_path)
    output = dist_size_report.report(dist, top=5)
    big_line = next(line for line in output.splitlines() if "big_package" in line)
    small_line = next(line for line in output.splitlines() if "small_package" in line)
    assert output.index(big_line) < output.index(small_line)


def test_report_total_reflects_all_measured_bytes(tmp_path):
    dist = _make_fake_dist(tmp_path)
    output = dist_size_report.report(dist, top=5)
    assert "Total measured" in output


def test_report_falls_back_to_dist_root_when_no_internal_dir(tmp_path):
    dist = tmp_path / "OnefileStyle"
    dist.mkdir()
    (dist / "app.exe").write_bytes(b"a" * 100_000)
    output = dist_size_report.report(dist, top=5)
    assert "app.exe" in output
