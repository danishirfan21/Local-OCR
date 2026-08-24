import json

from local_lens.export import to_json, to_markdown, to_txt
from local_lens.models import BoundingBox, DocumentResult, TextBlock


def make_result(content_type="text"):
    return DocumentResult(
        text="Hello\nWorld",
        blocks=[
            TextBlock("Hello", 0.95, BoundingBox(0, 0, 40, 10)),
            TextBlock("World", 0.80, BoundingBox(0, 20, 40, 10)),
        ],
        language="en",
        engine="easyocr",
        metadata={"content_type": content_type},
    )


def test_to_txt_returns_plain_text():
    assert to_txt(make_result()) == "Hello\nWorld"


def test_to_markdown_wraps_code_in_fence():
    md = to_markdown(make_result(content_type="code"))
    assert "```" in md
    assert "Hello\nWorld" in md


def test_to_markdown_plain_text_no_fence():
    md = to_markdown(make_result(content_type="text"))
    assert "```" not in md


def test_to_json_round_trips_expected_fields():
    payload = json.loads(to_json(make_result()))
    assert payload["engine"] == "easyocr"
    assert payload["language"] == "en"
    assert payload["text"] == "Hello\nWorld"
    assert len(payload["blocks"]) == 2
    assert payload["blocks"][0]["text"] == "Hello"
    assert payload["blocks"][0]["confidence"] == 0.95
    assert payload["blocks"][0]["bounding_box"] == {
        "left": 0,
        "top": 0,
        "width": 40,
        "height": 10,
    }
    assert payload["average_confidence"] == (0.95 + 0.80) / 2


def test_to_json_handles_missing_bbox():
    result = DocumentResult(
        text="x",
        blocks=[TextBlock("x", None, None)],
        language=None,
        engine="fake",
        metadata={},
    )
    payload = json.loads(to_json(result))
    assert payload["blocks"][0]["bounding_box"] is None
    assert payload["blocks"][0]["confidence"] is None
