"""Corpus-freeze manifest tests -- materializes fixtures locally (same
lightweight PIL rendering as the rest of the corpus, no network) and
checks the manifest is deterministic and hash-based."""

from __future__ import annotations

from local_lens.deep_analysis.manifest import BENCHMARK_VERSION, build_manifest


def test_manifest_has_expected_shape():
    manifest = build_manifest()
    assert manifest["benchmark_version"] == BENCHMARK_VERSION
    assert manifest["case_count"] == 12
    assert len(manifest["cases"]) == 12
    for case in manifest["cases"]:
        assert case["image_sha256"]
        assert case["ground_truth_sha256"]
        assert case["category"]


def test_manifest_is_deterministic():
    m1 = build_manifest()
    m2 = build_manifest()
    assert m1 == m2


def test_write_manifest_creates_file(tmp_path):
    from local_lens.deep_analysis.manifest import write_manifest

    path = write_manifest(tmp_path)
    assert path.exists()
    assert path.name == "manifest.json"
