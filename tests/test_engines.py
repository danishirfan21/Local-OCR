"""Engine abstraction tests using a fake engine -- no real OCR models loaded."""

from PIL import Image

from local_lens.models import BoundingBox, DocumentResult, TextBlock
from local_lens.services.ocr_service import OCRService


class FakeEngine:
    """Minimal stand-in satisfying the OCREngine protocol."""

    name = "fake"

    def __init__(self, blocks=None):
        self._blocks = blocks if blocks is not None else [
            TextBlock("fake", 0.99, BoundingBox(0, 0, 10, 10))
        ]

    def extract(self, image: Image.Image, langs: list[str]) -> DocumentResult:
        return DocumentResult(
            text="",
            blocks=list(self._blocks),
            language=langs[0] if langs else None,
            engine=self.name,
            metadata={},
        )


def _png_bytes():
    import io

    img = Image.new("RGB", (20, 20), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_service_calls_engine_and_reconstructs_text():
    service = OCRService(FakeEngine())
    result = service.process(_png_bytes(), ["en"], "none")
    assert result.engine == "fake"
    assert result.text == "fake"
    assert result.language == "en"


def test_service_attaches_classification_metadata():
    service = OCRService(FakeEngine())
    result = service.process(_png_bytes(), ["en"], "none")
    assert "content_type" in result.metadata
    assert "content_type_confidence" in result.metadata
    assert result.metadata["block_count"] == 1


def test_service_records_preprocessing_choice():
    service = OCRService(FakeEngine())
    result = service.process(_png_bytes(), ["en"], "high_contrast")
    assert result.metadata["preprocessing"] == "high_contrast"


def test_empty_engine_result_produces_empty_text():
    service = OCRService(FakeEngine(blocks=[]))
    result = service.process(_png_bytes(), ["en"], "none")
    assert result.text == ""
    assert result.metadata["content_type"] == "unknown"


def test_service_attaches_timings_and_language_detection():
    service = OCRService(FakeEngine())
    result = service.process(_png_bytes(), ["en"], "none")
    assert "timings" in result.metadata
    assert "ocr_ms" in result.metadata["timings"]
    assert result.detected_scripts == ["latin"]


def _table_like_blocks():
    blocks = []
    for row in range(4):
        blocks.append(TextBlock("word", 0.9, BoundingBox(0, row * 30, 50, 20)))
        blocks.append(TextBlock("42", 0.9, BoundingBox(200, row * 30, 50, 20)))
    return blocks


def test_table_extraction_not_attempted_for_non_table_content():
    service = OCRService(FakeEngine())  # single block -> plain text
    result = service.process(_png_bytes(), ["en"], "none")
    assert result.metadata["table_extraction_status"] == "not_attempted"
    assert result.tables == []


def test_table_content_without_extractor_reports_unavailable():
    service = OCRService(FakeEngine(blocks=_table_like_blocks()), table_extractor=None)
    result = service.process(_png_bytes(), ["en"], "none")
    assert result.metadata["content_type"] == "table"
    assert result.metadata["table_extraction_status"] == "unavailable"
    assert result.tables == []


class _FailingTableExtractor:
    name = "failing"

    def extract(self, image):
        raise RuntimeError("simulated table extractor failure")


def test_table_extractor_failure_does_not_lose_plain_ocr_result():
    service = OCRService(FakeEngine(blocks=_table_like_blocks()), table_extractor=_FailingTableExtractor())
    result = service.process(_png_bytes(), ["en"], "none")
    assert result.text  # plain OCR text still present
    assert result.tables == []
    assert "failed" in result.metadata["table_extraction_status"]


class _WorkingTableExtractor:
    name = "working"

    def extract(self, image):
        from local_lens.models import TableResult

        return [TableResult(rows=[["a", "b"]], cells=[], markdown=None, confidence=None, bbox=None)]


def test_table_extractor_success_populates_tables():
    service = OCRService(FakeEngine(blocks=_table_like_blocks()), table_extractor=_WorkingTableExtractor())
    result = service.process(_png_bytes(), ["en"], "none")
    assert len(result.tables) == 1
    assert result.metadata["table_extraction_status"] == "ok"


class _MessyTableExtractor:
    name = "messy"

    def extract(self, image):
        from local_lens.models import TableResult

        return [
            TableResult(
                rows=[[" a ", " b "], ["", ""], ["c", ""]],
                cells=[],
                markdown=None,
                confidence=None,
                bbox=None,
            )
        ]


def test_table_cleanup_trims_and_drops_empty_rows_and_records_metadata():
    service = OCRService(FakeEngine(blocks=_table_like_blocks()), table_extractor=_MessyTableExtractor())
    result = service.process(_png_bytes(), ["en"], "none")

    table = result.tables[0]
    assert table.rows == [["a", "b"], ["c", ""]]
    assert table.metadata["row_count"] == 2
    assert table.metadata["column_count"] == 2
    assert table.metadata["removed_empty_rows"] == 1
    assert table.metadata["empty_cell_ratio"] == 0.25
