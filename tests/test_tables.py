from local_lens.models import BoundingBox, TableCell, TableResult
from local_lens.tables.paddle_table_extractor import _cells_to_rows, _parse_html_table


def test_table_cell_defaults():
    cell = TableCell(row=0, column=0, text="x")
    assert cell.confidence is None
    assert cell.bbox is None


def test_table_result_has_header_defaults_false():
    table = TableResult(rows=[["a"]], cells=[], markdown=None, confidence=None, bbox=None)
    assert table.has_header is False


def test_cells_to_rows_builds_grid():
    cells = [
        TableCell(row=0, column=0, text="Product"),
        TableCell(row=0, column=1, text="Qty"),
        TableCell(row=1, column=0, text="Keyboard"),
        TableCell(row=1, column=1, text="2"),
    ]
    rows = _cells_to_rows(cells)
    assert rows == [["Product", "Qty"], ["Keyboard", "2"]]


def test_cells_to_rows_empty():
    assert _cells_to_rows([]) == []


def test_parse_html_table_extracts_cells_and_header():
    html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
    cells, has_header = _parse_html_table(html)
    assert has_header is True
    assert len(cells) == 4
    texts = {(c.row, c.column): c.text for c in cells}
    assert texts[(0, 0)] == "A"
    assert texts[(1, 1)] == "2"


def test_parse_html_table_without_header():
    html = "<table><tr><td>1</td><td>2</td></tr></table>"
    cells, has_header = _parse_html_table(html)
    assert has_header is False
    assert len(cells) == 2
