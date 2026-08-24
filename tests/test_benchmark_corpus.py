from benchmarks.corpus import CORPUS, ensure_corpus, image_path_for


def test_corpus_covers_required_categories():
    categories = {entry["category"] for entry in CORPUS}
    assert {"english", "urdu", "mixed", "short_ui", "tables", "code"}.issubset(categories)


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
