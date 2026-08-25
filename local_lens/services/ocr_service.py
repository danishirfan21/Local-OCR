"""Top-level orchestration: preprocess -> engine -> reading order -> classify -> tables.

This is the single entry point the UI (or a future CLI/API) should call.
It has no Streamlit dependency, so it works the same way in a notebook, a
test, or a web server.
"""

from __future__ import annotations

import io

from PIL import Image

from local_lens.classification import classify
from local_lens.engines.base import OCREngine
from local_lens.models import DocumentResult, TableResult
from local_lens.preprocessing.image import PRESET_NONE, apply_preset
from local_lens.reconstruction import reconstruct_text
from local_lens.scripts import SCRIPT_ARABIC, detect_scripts, infer_languages
from local_lens.tables.base import TableExtractor
from local_lens.text_normalization import normalize_urdu_text
from local_lens.timing import Stopwatch


def _clean_table(table: TableResult) -> TableResult:
    """Trim cell whitespace and drop fully-empty rows, then record
    deterministic quality indicators the backend didn't provide itself.

    Never fabricates a confidence score -- `metadata` only ever holds
    counts/ratios computed directly from the (cleaned) rows.
    """
    trimmed_rows = [[cell.strip() for cell in row] for row in table.rows]
    kept_rows = [row for row in trimmed_rows if any(cell for cell in row)]
    removed_empty_rows = len(trimmed_rows) - len(kept_rows)

    total_cells = sum(len(row) for row in kept_rows)
    empty_cells = sum(1 for row in kept_rows for cell in row if not cell)
    empty_cell_ratio = round(empty_cells / total_cells, 3) if total_cells else 0.0

    table.rows = kept_rows
    table.metadata.update(
        {
            "row_count": len(kept_rows),
            "column_count": len(kept_rows[0]) if kept_rows else 0,
            "empty_cell_ratio": empty_cell_ratio,
            "removed_empty_rows": removed_empty_rows,
        }
    )
    return table


class OCRService:
    def __init__(self, engine: OCREngine, table_extractor: TableExtractor | None = None):
        self.engine = engine
        self.table_extractor = table_extractor

    def process(
        self,
        image_bytes: bytes,
        langs: list[str],
        preprocessing: str = PRESET_NONE,
    ) -> DocumentResult:
        sw = Stopwatch()

        with sw.measure("preprocess_ms"):
            original = Image.open(io.BytesIO(image_bytes))
            processed = apply_preset(original, preprocessing)

        with sw.measure("ocr_ms"):
            result = self.engine.extract(processed, langs)

        with sw.measure("reconstruct_ms"):
            result.text = reconstruct_text(result.blocks)

        result.detected_scripts = detect_scripts(result.text)
        result.detected_languages = infer_languages(result.detected_scripts, langs)
        if SCRIPT_ARABIC in result.detected_scripts:
            result.text = normalize_urdu_text(result.text)
            for b in result.blocks:
                b.text = normalize_urdu_text(b.text)

        with sw.measure("classify_ms"):
            content_type, confidence = classify(result.text, blocks=result.blocks)

        if content_type.value != "table":
            table_status = "not_attempted"
        elif self.table_extractor is None:
            table_status = "unavailable"
        else:
            with sw.measure("table_extraction_ms"):
                try:
                    result.tables = [_clean_table(t) for t in self.table_extractor.extract(processed)]
                    table_status = "ok" if result.tables else "no_tables_found"
                except Exception as exc:
                    # Table extraction is an enrichment step -- its failure
                    # must not lose the plain OCR result that already
                    # succeeded above.
                    table_status = f"failed: {exc}"

        result.metadata.update(
            {
                "preprocessing": preprocessing,
                "content_type": content_type.value,
                "content_type_confidence": confidence,
                "block_count": len(result.blocks),
                "table_extraction_status": table_status,
                "timings": sw.timings_ms,
                "total_ms": sw.total_ms,
            }
        )
        return result
