from local_lens.classification import classify
from local_lens.models import BoundingBox, ContentType, TextBlock


def block(text, left, top, width=50, height=20, confidence=0.9):
    return TextBlock(text=text, confidence=confidence, bbox=BoundingBox(left, top, width, height))


def test_empty_text_is_unknown():
    content_type, confidence = classify("")
    assert content_type == ContentType.UNKNOWN
    assert confidence == 0.0


def test_whitespace_only_is_unknown():
    content_type, _ = classify("   \n  \n")
    assert content_type == ContentType.UNKNOWN


def test_plain_prose_is_text():
    prose = (
        "This is a normal paragraph of extracted text. It has several "
        "sentences and no special formatting at all in it."
    )
    content_type, _ = classify(prose)
    assert content_type == ContentType.TEXT


def test_python_like_snippet_is_code():
    code = (
        "def greet(name):\n"
        "    if name:\n"
        "        return f'Hello, {name}!'\n"
        "    else:\n"
        "        return None\n"
    )
    content_type, confidence = classify(code)
    assert content_type == ContentType.CODE
    assert confidence > 0


def test_aligned_columns_is_table():
    table = (
        "Name        Score       Rank\n"
        "Alice       92          1\n"
        "Bob         85          2\n"
        "Carol       77          3\n"
    )
    content_type, confidence = classify(table)
    assert content_type == ContentType.TABLE
    assert confidence > 0


def test_confidence_never_overstated():
    code = "def f(): return {}"
    _, confidence = classify(code)
    assert confidence <= 0.9


def test_geometry_signal_detects_table_from_aligned_columns_alone():
    # Text alone gives no punctuation/whitespace hints (single words per
    # line), but the blocks form two clearly aligned columns across four
    # rows -- geometry should still surface this as a table.
    blocks = []
    for row in range(4):
        blocks.append(block("word", left=0, top=row * 30))
        blocks.append(block("42", left=200, top=row * 30))
    text = "\n".join("word 42" for _ in range(4))
    content_type, confidence = classify(text, blocks=blocks)
    assert content_type == ContentType.TABLE
    assert confidence > 0


def test_geometry_signal_omitted_falls_back_to_text_only_behavior():
    prose = "This is a normal paragraph of extracted text with no columns."
    without_blocks = classify(prose)
    with_none_blocks = classify(prose, blocks=None)
    assert without_blocks == with_none_blocks


def test_geometry_signal_does_not_misfire_on_few_blocks():
    blocks = [block("Hello", 0, 0), block("World", 60, 0)]
    content_type, _ = classify("Hello World", blocks=blocks)
    assert content_type == ContentType.TEXT
