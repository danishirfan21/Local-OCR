from local_lens.classification import classify
from local_lens.models import ContentType


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
