"""Freezes the 12 selected benchmark fixtures into a reproducible manifest.

Recording each image's and ground truth's hash means a later run can
detect (not just assume) that "the same 12 fixtures" were actually used --
if `benchmarks/corpus.py` ever changes a fixture's rendering, the hash
changes and comparisons across runs stop silently conflating old and new
data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from local_lens.deep_analysis.benchmark_cases import build_deep_benchmark_cases

BENCHMARK_VERSION = "deep-v1"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_manifest() -> dict:
    """Materializes fixtures (same lightweight PIL rendering as the
    existing corpus -- no network, no model) and returns the frozen
    manifest dict. Deterministic: same corpus in, same manifest out."""
    cases = build_deep_benchmark_cases()

    entries = []
    for case in cases:
        ground_truth_text = case.expected_text if case.expected_text is not None else json.dumps(
            case.expected_table, sort_keys=True
        )
        entries.append(
            {
                "id": case.id,
                "category": case.category,
                "image_sha256": _sha256_file(case.image_path),
                "ground_truth_sha256": _sha256_text(ground_truth_text or ""),
                "languages": case.languages,
                "notes": case.notes,
            }
        )

    return {"benchmark_version": BENCHMARK_VERSION, "case_count": len(entries), "cases": entries}


def write_manifest(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(build_manifest(), indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path
