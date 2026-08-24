import csv
import io

from local_lens.export import export_table_csv, export_table_markdown
from local_lens.models import TableResult


def test_export_table_csv_basic():
    table = TableResult(
        rows=[["Product", "Quantity"], ["Keyboard", "2"]],
        cells=[],
        markdown=None,
        confidence=None,
        bbox=None,
        has_header=True,
    )
    csv_text = export_table_csv(table)
    reader = list(csv.reader(io.StringIO(csv_text)))
    assert reader == [["Product", "Quantity"], ["Keyboard", "2"]]


def test_export_table_csv_handles_commas_and_quotes():
    table = TableResult(
        rows=[["a,b", 'say "hi"'], ["line\nbreak", "normal"]],
        cells=[],
        markdown=None,
        confidence=None,
        bbox=None,
    )
    csv_text = export_table_csv(table)
    reader = list(csv.reader(io.StringIO(csv_text)))
    assert reader == [["a,b", 'say "hi"'], ["line\nbreak", "normal"]]


def test_export_table_csv_handles_unicode_urdu():
    table = TableResult(rows=[["نمبر", "12345"]], cells=[], markdown=None, confidence=None, bbox=None)
    csv_text = export_table_csv(table)
    reader = list(csv.reader(io.StringIO(csv_text)))
    assert reader == [["نمبر", "12345"]]


def test_export_table_csv_handles_empty_cells():
    table = TableResult(rows=[["a", ""], ["", "b"]], cells=[], markdown=None, confidence=None, bbox=None)
    csv_text = export_table_csv(table)
    reader = list(csv.reader(io.StringIO(csv_text)))
    assert reader == [["a", ""], ["", "b"]]


def test_export_table_markdown_with_header():
    table = TableResult(
        rows=[["Product", "Quantity"], ["Keyboard", "2"]],
        cells=[],
        markdown=None,
        confidence=None,
        bbox=None,
        has_header=True,
    )
    md = export_table_markdown(table)
    assert md.splitlines()[0] == "| Product | Quantity |"
    assert "Keyboard" in md


def test_export_table_markdown_without_header_does_not_fabricate_one():
    table = TableResult(rows=[["Keyboard", "2"]], cells=[], markdown=None, confidence=None, bbox=None)
    md = export_table_markdown(table)
    assert "Column 1" in md  # explicit placeholder, not a fabricated real header
    assert "Keyboard" in md


def test_export_table_markdown_prefers_extractor_provided_markdown():
    table = TableResult(
        rows=[["x"]], cells=[], markdown="| custom |\n|---|\n| x |", confidence=None, bbox=None
    )
    assert export_table_markdown(table) == "| custom |\n|---|\n| x |"


def test_export_table_markdown_empty_rows():
    table = TableResult(rows=[], cells=[], markdown=None, confidence=None, bbox=None)
    assert "no rows" in export_table_markdown(table).lower()
