from local_lens.models import BoundingBox, TextBlock
from local_lens.reconstruction import reconstruct_text


def block(text, left, top, width=50, height=20, confidence=0.9):
    return TextBlock(text=text, confidence=confidence, bbox=BoundingBox(left, top, width, height))


def test_single_line_sorted_left_to_right():
    blocks = [block("World", 100, 0), block("Hello", 0, 0)]
    assert reconstruct_text(blocks) == "Hello World"


def test_two_lines_top_to_bottom():
    blocks = [
        block("second", 0, 100),
        block("line", 60, 0),
        block("first", 0, 0),
    ]
    assert reconstruct_text(blocks) == "first line\nsecond"


def test_paragraph_not_collapsed_into_one_line():
    blocks = [block(f"line{i}", 0, i * 30) for i in range(5)]
    text = reconstruct_text(blocks)
    assert text == "line0\nline1\nline2\nline3\nline4"
    assert text.count("\n") == 4


def test_blocks_without_bbox_appended_as_extra_line():
    blocks = [block("has-bbox", 0, 0), TextBlock(text="no-bbox", confidence=None, bbox=None)]
    text = reconstruct_text(blocks)
    assert text == "has-bbox\nno-bbox"


def test_empty_input_returns_empty_string():
    assert reconstruct_text([]) == ""


def test_slightly_jittered_baselines_stay_on_one_line():
    # Two words on the "same" line but with a couple pixels of vertical
    # jitter (common in real OCR output) should not be split into two lines.
    blocks = [block("Hello", 0, 10, height=20), block("World", 60, 12, height=20)]
    assert reconstruct_text(blocks) == "Hello World"
