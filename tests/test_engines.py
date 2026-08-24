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
