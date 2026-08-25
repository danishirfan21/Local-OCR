"""Tests for the compact Deep Analyze benchmark corpus subset. Building
these cases materializes fixture images (lightweight PIL rendering, same
as the existing Fast-mode corpus) but makes no network call and downloads
no model."""

from __future__ import annotations

from local_lens.deep_analysis.benchmark_cases import build_deep_benchmark_cases


def test_build_deep_benchmark_cases_materializes_images():
    cases = build_deep_benchmark_cases()
    assert len(cases) == 12
    for case in cases:
        assert case.image_path.exists()


def test_cases_cover_expected_categories():
    cases = build_deep_benchmark_cases()
    categories = {c.category for c in cases}
    assert {"short_ui", "english", "edge_cases", "code", "tables", "urdu", "mixed", "photo_scan"} <= categories


def test_table_cases_have_expected_table_not_text():
    cases = {c.id: c for c in build_deep_benchmark_cases()}
    assert cases["table_simple"].expected_table is not None
    assert cases["table_simple"].expected_text is None


def test_urdu_case_has_ur_language():
    cases = {c.id: c for c in build_deep_benchmark_cases()}
    assert "ur" in cases["urdu_paragraph"].languages


def test_mixed_case_has_both_languages():
    cases = {c.id: c for c in build_deep_benchmark_cases()}
    assert set(cases["mixed_urdu_english"].languages) == {"ur", "en"}
