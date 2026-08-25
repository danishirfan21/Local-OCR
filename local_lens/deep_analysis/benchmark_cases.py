"""A compact, decision-quality subset of the existing benchmarks/corpus.py
fixtures, wrapped as provider-independent `DeepBenchmarkCase`s.

Deliberately reuses the corpus that already exists for Fast-mode
benchmarking rather than inventing a second fixture set -- these images
are already rights-safe (self-rendered), already committed as ground
truth, and already cover the categories this bake-off needs. This module
adds no new fixtures; it only selects and adapts.

12 cases, not "hundreds": one representative per category the task asked
for (short UI text, realistic paragraph, the extreme-aspect edge case,
numeric text, two programming languages, a simple table, a dense table,
shaped Urdu, mixed Urdu/English, an invoice-like financial table, and one
photographed/scanned document). See docs/DEEP_PROVIDER_EVALUATION.md for
the reasoning behind this selection.
"""

from __future__ import annotations

from local_lens.deep_analysis.benchmark import DeepBenchmarkCase

# (corpus id, languages) -- everything else is read off the corpus entry
# itself (category, expected text/table) by _case_from_corpus_entry().
_SELECTED = [
    ("short_ui_save", ["en"]),
    ("paragraph", ["en"]),
    ("extreme_wide_line", ["en"]),
    ("numeric", ["en"]),
    ("python", ["en"]),
    ("typescript", ["en"]),
    ("table_simple", ["en"]),
    ("table_dense", ["en"]),
    ("urdu_paragraph", ["ur"]),
    ("mixed_urdu_english", ["ur", "en"]),
    ("table_financial", ["en"]),
    ("scan_clean", ["en"]),
]


def _case_from_corpus_entry(entry: dict, languages: list[str]) -> DeepBenchmarkCase:
    from benchmarks.corpus import image_path_for

    kind = entry["kind"]
    expected_text = None
    expected_table = None
    content_type = None

    if kind == "table":
        expected_table = entry["rows"]
        content_type = "table"
    elif kind == "transform":
        expected_text = entry["base"]
        content_type = "text"
    else:
        expected_text = entry["text"]
        content_type = "code" if entry["category"] == "code" else "text"

    return DeepBenchmarkCase(
        id=entry["id"],
        category=entry["category"],
        image_path=image_path_for(entry),
        expected_text=expected_text,
        expected_content_type=content_type,
        expected_table=expected_table,
        languages=languages,
        notes=f"corpus kind={kind}",
    )


def build_deep_benchmark_cases() -> list[DeepBenchmarkCase]:
    """Materializes the underlying corpus fixtures (lightweight PIL
    rendering, no network, no model download -- same as the existing Fast
    benchmark) and returns the selected subset as benchmark cases."""
    from benchmarks.corpus import CORPUS, ensure_corpus

    ensure_corpus()
    by_id = {entry["id"]: entry for entry in CORPUS}

    cases = []
    for corpus_id, languages in _SELECTED:
        entry = by_id[corpus_id]
        cases.append(_case_from_corpus_entry(entry, languages))
    return cases
