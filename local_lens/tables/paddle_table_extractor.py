"""PaddleOCR-based table extractor using TableRecognitionPipelineV2.

Separate, heavier pipeline from the plain PaddleOCR text engine (layout
detection -> table classification -> wired/wireless structure recognition
-> cell detection -> OCR) -- see local_lens/services/ocr_service.py for why
this only runs when content classification already suspects a table.

Result field names were confirmed empirically against a real run (see
tests/test_tables.py and the V3 implementation report) rather than assumed
from documentation, following the same approach used for the plain
PaddleOCR engine in V2. That real run also surfaced two honest limitations:
`pred_html` did not use <th> tags for the header row in testing, so
has_header comes back False even for tables with an obvious header row
(the alternative -- guessing a header from position -- would mean
fabricating structure the model didn't actually assert, which contradicts
this module's own has_header contract); and a spurious empty trailing row
appeared in one real run. Both are documented in the V3 report rather than
silently patched over.
"""

from __future__ import annotations

from PIL import Image

from local_lens.models import BoundingBox, TableCell, TableResult

try:
    from paddleocr import TableRecognitionPipelineV2 as _TableRecognitionPipelineV2

    TABLE_EXTRACTION_AVAILABLE = True
except ImportError:
    _TableRecognitionPipelineV2 = None
    TABLE_EXTRACTION_AVAILABLE = False

_pipeline_cache: dict[str, object] = {}


def _get_pipeline():
    if not TABLE_EXTRACTION_AVAILABLE:
        raise RuntimeError(
            "PaddleOCR table extraction is not installed. Install it with:\n"
            "  pip install -r requirements-paddle.txt\n"
            '  pip install "paddlex[ocr]"\n'
            "See README.md for details."
        )

    pipeline = _pipeline_cache.get("default")
    if pipeline is None:
        # Same CPU/oneDNN issue as the plain PaddleOCR engine (see
        # engines/paddleocr_engine.py) applies here too.
        pipeline = _TableRecognitionPipelineV2(enable_mkldnn=False)
        _pipeline_cache["default"] = pipeline
    return pipeline


def _cells_to_rows(cells: list[TableCell]) -> list[list[str]]:
    if not cells:
        return []
    n_rows = max(c.row for c in cells) + 1
    n_cols = max(c.column for c in cells) + 1
    grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for cell in cells:
        grid[cell.row][cell.column] = cell.text
    return grid


def _rows_to_markdown(rows: list[list[str]], has_header: bool) -> str:
    if not rows:
        return ""
    lines = []
    header = rows[0] if has_header else [f"Column {i + 1}" for i in range(len(rows[0]))]
    body = rows[1:] if has_header else rows
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


class PaddleTableExtractor:
    name = "paddleocr_table"

    def extract(self, image: Image.Image) -> list[TableResult]:
        import numpy as np

        pipeline = _get_pipeline()
        image_np = np.array(image.convert("RGB"))
        raw_results = pipeline.predict(image_np)

        tables: list[TableResult] = []
        for page in raw_results:
            table_entries = page.get("table_res_list") or page.get("tables") or []
            for entry in table_entries:
                cells, header_detected = _parse_cells(entry)
                rows = _cells_to_rows(cells)
                has_header = bool(entry.get("has_header", False)) or header_detected
                markdown = _rows_to_markdown(rows, has_header) if rows else None
                bbox = None
                region_box = entry.get("cell_box") or entry.get("table_box")
                if region_box:
                    bbox = BoundingBox.from_points(
                        [(region_box[i], region_box[i + 1]) for i in range(0, len(region_box), 2)]
                    )
                tables.append(
                    TableResult(
                        rows=rows,
                        cells=cells,
                        markdown=markdown,
                        confidence=None,
                        bbox=bbox,
                        has_header=has_header,
                    )
                )
        return tables


def _parse_cells(entry: dict) -> tuple[list[TableCell], bool]:
    """Parse one table entry's cells. Returns (cells, header_detected).

    TableRecognitionPipelineV2 primarily returns an HTML table representation
    (`pred_html`) rather than a flat cell list in all configurations; this
    parses whichever structured cell data is present (`cell_texts`/`cells`-
    style fields observed at runtime) and falls back to parsing `pred_html`
    with the standard library's HTMLParser if that's all that's available,
    rather than requiring a specific undocumented shape.
    """
    structured = entry.get("cell_texts") or entry.get("cells")
    if structured:
        cells = [
            TableCell(
                row=int(cell.get("row", cell.get("row_idx", 0))),
                column=int(cell.get("column", cell.get("col_idx", 0))),
                text=str(cell.get("text", "")).strip(),
                confidence=cell.get("confidence"),
            )
            for cell in structured
        ]
        return cells, False

    html = entry.get("pred_html")
    if html:
        return _parse_html_table(html)

    return [], False


def _parse_html_table(html: str) -> tuple[list[TableCell], bool]:
    from html.parser import HTMLParser

    class _TableHTMLParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.cells: list[TableCell] = []
            self.header_detected = False
            self._row = -1
            self._col = 0
            self._in_cell = False
            self._buffer = ""

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self._row += 1
                self._col = 0
            elif tag in ("td", "th"):
                self._in_cell = True
                self._buffer = ""
                if tag == "th":
                    self.header_detected = True

        def handle_endtag(self, tag):
            if tag in ("td", "th"):
                self.cells.append(
                    TableCell(row=max(self._row, 0), column=self._col, text=self._buffer.strip())
                )
                self._col += 1
                self._in_cell = False

        def handle_data(self, data):
            if self._in_cell:
                self._buffer += data

    parser = _TableHTMLParser()
    parser.feed(html)
    return parser.cells, parser.header_detected
