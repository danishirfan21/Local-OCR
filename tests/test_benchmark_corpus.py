from benchmarks.corpus import CORPUS, ensure_corpus, image_path_for, shape_arabic_line


def test_corpus_covers_required_categories():
    categories = {entry["category"] for entry in CORPUS}
    assert {
        "english", "urdu", "mixed", "short_ui", "tables", "code",
        "edge_cases", "photo_scan",
    }.issubset(categories)


def test_edge_cases_preserves_extreme_wide_line_regression_fixture():
    ids = {e["id"] for e in CORPUS if e["category"] == "edge_cases"}
    assert "extreme_wide_line" in ids


def test_paragraph_fixture_is_distinct_from_extreme_wide_line():
    paragraph = next(e for e in CORPUS if e["id"] == "paragraph")
    extreme = next(e for e in CORPUS if e["id"] == "extreme_wide_line")
    assert paragraph.get("wrap") is True
    assert not extreme.get("wrap")


def test_shape_arabic_line_reorders_and_joins_glyphs():
    shaped = shape_arabic_line("سلام")
    # The shaped/visual string must differ from the raw logical-order input
    # (reshaping substitutes presentation-form codepoints, bidi reorders).
    assert shaped != "سلام"
    assert len(shaped) > 0


def test_photo_scan_fixtures_present():
    ids = {e["id"] for e in CORPUS if e["category"] == "photo_scan"}
    assert {"photo_rotated", "photo_perspective", "photo_low_light",
            "photo_low_contrast", "photo_full_camera", "scan_clean"}.issubset(ids)


def test_urdu_corpus_covers_required_variants():
    ids = {e["id"] for e in CORPUS if e["category"] == "urdu"}
    assert {"urdu_simple_sentence", "urdu_paragraph", "urdu_numbers", "urdu_punctuation",
            "urdu_brand_term"}.issubset(ids)


def test_code_corpus_covers_required_languages():
    ids = {e["id"] for e in CORPUS if e["category"] == "code"}
    assert {"python", "java", "typescript", "json", "shell"}.issubset(ids)


def test_table_robustness_fixtures_present():
    ids = {e["id"] for e in CORPUS if e["category"] == "tables"}
    assert {"table_merged_cells", "table_borderless", "table_partial_borders",
            "table_multiline_cells", "table_financial", "table_urdu", "table_mixed"}.issubset(ids)


def test_corpus_has_both_simple_and_dense_tables():
    table_ids = {e["id"] for e in CORPUS if e["category"] == "tables"}
    assert "table_simple" in table_ids
    assert "table_dense" in table_ids


def test_ensure_corpus_materializes_all_images():
    ensure_corpus()
    for entry in CORPUS:
        path = image_path_for(entry)
        assert path.exists(), f"missing generated image for {entry['id']}"


def test_table_entries_have_consistent_row_widths():
    for entry in CORPUS:
        if entry["kind"] != "table":
            continue
        widths = {len(row) for row in entry["rows"]}
        assert len(widths) == 1, f"{entry['id']} has inconsistent row widths"
