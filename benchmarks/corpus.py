"""Benchmark corpus: fixture definitions + synthetic generation.

All fixtures are synthetic (rendered via PIL) or trivially self-generated --
nothing copyrighted or private. Materializes benchmarks/samples/<category>/<id>.png
and benchmarks/ground_truth/<category>/<id>.json from CORPUS on first run;
images/ground-truth are regenerated if missing so the corpus is reproducible
without committing binary files (see .gitignore).

Urdu shaping (V4): this environment's Pillow has no `raqm` text-shaping
support even in the latest wheel (checked via PIL.features.check("raqm")
after a forced reinstall -- not available on this platform without a
from-source build). Instead, Urdu/Arabic-script fixtures are shaped with
`arabic_reshaper` + `python-bidi`: arabic_reshaper converts each base
Arabic-block codepoint into its correct contextual (initial/medial/final/
isolated) Presentation-Forms glyph *before* PIL draws it, and python-bidi
produces the correct visual (left-to-right-on-canvas) character order. This
needs no raqm at all and was visually verified (via the Read tool viewing
the rendered PNGs directly) to produce genuinely connected, readable Urdu
script -- unlike V3's fixtures, which rendered isolated, disconnected
letterforms. See docs/V4_IMPLEMENTATION.md for the before/after comparison
and the exact package versions used (arabic-reshaper 3.0.1, python-bidi
0.6.7).
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
GROUND_TRUTH_DIR = Path(__file__).resolve().parent / "ground_truth"

_LATIN_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_ARABIC_FONT_CANDIDATES = [
    "C:/Windows/Fonts/tahoma.ttf",
]
_MONO_FONT_CANDIDATES = [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf",
]


def _first_available_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def font_available(family: str) -> bool:
    candidates = {"latin": _LATIN_FONT_CANDIDATES, "arabic": _ARABIC_FONT_CANDIDATES,
                  "mono": _MONO_FONT_CANDIDATES}[family]
    return any(Path(p).exists() for p in candidates)


def shape_arabic_line(line: str) -> str:
    """Reshape+bidi-reorder a single line of Arabic-script text for PIL rendering.

    Applied per-line (not across a whole multi-line block) because bidi
    reordering operates on paragraph/line units -- reordering across
    newlines would scramble line order, not just character order within
    a line.
    """
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(arabic_reshaper.reshape(line))


def _wrap_text(text: str, max_chars: int = 55) -> str:
    """Wrap long unbroken lines to a realistic on-screen paragraph shape.

    Preserves existing newlines (so code snippets with intentional line
    breaks are untouched) -- only wraps individual lines that are
    themselves longer than max_chars, which is what turns a single very
    long line into an unrealistic ~30:1 aspect-ratio strip (see
    edge_cases/extreme_wide_line, which intentionally keeps the old
    unwrapped behavior for regression testing).
    """
    import textwrap

    out_lines = []
    for line in text.split("\n"):
        if len(line) > max_chars:
            out_lines.extend(textwrap.wrap(line, width=max_chars))
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def _render_text_image(text: str, font_family: str, wrap: bool = False, font_size: int = 26) -> Image.Image:
    if wrap:
        text = _wrap_text(text)
    if font_family == "arabic":
        text = "\n".join(shape_arabic_line(line) if line.strip() else line for line in text.split("\n"))

    candidates = {"latin": _LATIN_FONT_CANDIDATES, "arabic": _ARABIC_FONT_CANDIDATES,
                  "mono": _MONO_FONT_CANDIDATES}[font_family]
    font = _first_available_font(candidates, font_size)
    lines = text.split("\n")
    line_height = int(font_size * 1.4)
    width = max(500, max(len(line) for line in lines) * int(font_size * 0.65))
    img = Image.new("RGB", (width, line_height * len(lines) + 20), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((10, 10 + i * line_height), line, fill="black", font=font)
    return img


def _render_table_image(
    rows: list[list[str]],
    border_style: str = "full",
    font_family: str = "latin",
    font_size: int = 20,
    col_width: int = 130,
    merges: list[tuple[int, int, int]] | None = None,
    multiline_row: int | None = None,
) -> Image.Image:
    """Render a table. `merges` is a list of (row, start_col, col_span) for
    cells that visually span multiple columns (border between them
    omitted, text drawn once, spanning the merged width). `multiline_row`
    marks one row's cells as two lines of text (taller row).
    """
    font = _first_available_font(
        _ARABIC_FONT_CANDIDATES if font_family == "arabic" else _LATIN_FONT_CANDIDATES, font_size
    )
    n_cols = len(rows[0])
    row_height = 40
    tall_row_height = 64
    width = col_width * n_cols + 10
    height = sum(tall_row_height if r == multiline_row else row_height for r in range(len(rows))) + 10
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    merge_map = {}
    if merges:
        for row, start_col, span in merges:
            for c in range(start_col, start_col + span):
                merge_map[(row, c)] = (start_col, span)

    y = 5
    row_tops = []
    for r, row in enumerate(rows):
        row_tops.append(y)
        h = tall_row_height if r == multiline_row else row_height
        for c, val in enumerate(row):
            if (r, c) in merge_map and merge_map[(r, c)][0] != c:
                continue  # drawn as part of the merge's first column
            cell_text = val
            if font_family == "arabic" and cell_text.strip():
                cell_text = shape_arabic_line(cell_text)
            if r == multiline_row and "\n" in cell_text:
                for li, sub in enumerate(cell_text.split("\n")):
                    draw.text((10 + c * col_width, y + 4 + li * 22), sub, fill="black", font=font)
            else:
                draw.text((10 + c * col_width, y + 10), cell_text, fill="black", font=font)
        y += h
    row_tops.append(y)

    if border_style != "none":
        for x in range(0, width, col_width):
            draw.line([(x, 0), (x, height)], fill="black", width=1)
        draw.line([(width - 1, 0), (width - 1, height)], fill="black", width=1)

        if border_style == "partial":
            draw.line([(0, 0), (width, 0)], fill="black", width=1)
            draw.line([(0, row_tops[1]), (width, row_tops[1])], fill="black", width=1)
            draw.line([(0, height - 1), (width, height - 1)], fill="black", width=1)
        else:  # full
            for yy in row_tops:
                draw.line([(0, yy), (width, yy)], fill="black", width=1)

        # erase the vertical border segment(s) inside a merged cell's row
        if merges:
            for row, start_col, span in merges:
                top, bottom = row_tops[row], row_tops[row + 1]
                for c in range(start_col + 1, start_col + span):
                    x = c * col_width
                    draw.line([(x, top + 1), (x, bottom - 1)], fill="white", width=1)

    return img


def _render_document_page(text: str) -> Image.Image:
    """A taller, page-like block of text (for photo/scan transform fixtures)."""
    return _render_text_image(text, "latin", wrap=True, font_size=22)


def _apply_rotation(img: Image.Image, degrees: float) -> Image.Image:
    return img.rotate(degrees, expand=True, fillcolor="white")


def _apply_perspective(img: Image.Image, strength: float = 0.08) -> Image.Image:
    w, h = img.size
    dx, dy = int(w * strength), int(h * strength)
    # Skew the top edge inward to simulate a camera-angle photo of a page.
    coeffs = [dx, dy, dx, h - dy, w - dx, h, w, 0]
    return img.transform((w, h), Image.QUAD, data=coeffs, fillcolor="white")


def _apply_low_contrast(img: Image.Image) -> Image.Image:
    return ImageEnhance.Contrast(img).enhance(0.35)


def _apply_uneven_lighting(img: Image.Image) -> Image.Image:
    import numpy as np

    arr = np.array(img.convert("RGB")).astype(float)
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    gradient = 1.0 - 0.5 * (xx / w)  # darker on the right side
    arr *= gradient[:, :, None]
    return Image.fromarray(arr.clip(0, 255).astype("uint8"))


def _apply_grayscale_scan(img: Image.Image) -> Image.Image:
    gray = img.convert("L")
    return ImageEnhance.Contrast(gray).enhance(1.3).convert("RGB")


# Each entry: id, category, kind ("text" | "table" | "transform"), and
# kind-specific fields (text/rows/etc). "transform" entries derive their
# image from a `base` document via a named PIL transform pipeline; ground
# truth is identical to the base text since transforms are purely visual.
_DOCUMENT_TEXT = (
    "Local Lens turns a screenshot into structured text. This page "
    "simulates a photographed or scanned document for routing benchmarks."
)

CORPUS = [
    {"id": "short_ui_save", "category": "short_ui", "kind": "text", "font": "latin",
     "text": "Save"},
    {"id": "short_ui_cancel", "category": "short_ui", "kind": "text", "font": "latin",
     "text": "Cancel Settings OK"},
    {"id": "paragraph", "category": "english", "kind": "text", "font": "latin", "wrap": True,
     "text": "This is a normal paragraph of extracted text. It has several "
             "sentences and no special formatting at all in it."},
    {"id": "numeric", "category": "english", "kind": "text", "font": "latin",
     "text": "123456 789012 345 67890"},
    {"id": "english_numbers", "category": "english", "kind": "text", "font": "latin",
     "text": "Order 12345 confirmed for $99.50"},

    # --- edge case: preserved from V3, the fixture that revealed PaddleOCR-VL's
    # extreme-aspect-ratio recognition failure (see docs/V4_IMPLEMENTATION.md).
    {"id": "extreme_wide_line", "category": "edge_cases", "kind": "text", "font": "latin",
     "text": "This is a normal paragraph of extracted text. It has several "
             "sentences and no special formatting at all in it."},

    # --- code (Python kept from V3, adds Java/TS/JSON/shell) ---
    {"id": "python", "category": "code", "kind": "text", "font": "mono",
     "text": "def greet(name):\n    if name:\n        return f'Hi {name}'\n    return None"},
    {"id": "java", "category": "code", "kind": "text", "font": "mono",
     "text": "public class Greeter {\n    public String greet(String name) {\n        return \"Hi \" + name;\n    }\n}"},
    {"id": "typescript", "category": "code", "kind": "text", "font": "mono",
     "text": "function greet(name: string): string {\n  if (name) {\n    return `Hi ${name}`;\n  }\n  return \"\";\n}"},
    {"id": "json", "category": "code", "kind": "text", "font": "mono",
     "text": '{\n  "name": "Local Lens",\n  "mode": "fast",\n  "engines": ["easyocr", "paddleocr"]\n}'},
    {"id": "shell", "category": "code", "kind": "text", "font": "mono",
     "text": "$ pip install -r requirements.txt\n$ streamlit run app.py --server.port 8501"},

    # --- tables: existing simple/dense + robustness set ---
    {"id": "table_simple", "category": "tables", "kind": "table", "font": "latin",
     "rows": [["Product", "Quantity", "Price"], ["Keyboard", "2", "50"], ["Mouse", "1", "25"]],
     "has_header": True},
    {"id": "table_dense", "category": "tables", "kind": "table", "font": "latin",
     "rows": [
         ["Name", "Score", "Rank", "Team"],
         ["Alice", "92", "1", "Red"],
         ["Bob", "85", "2", "Blue"],
         ["Carol", "77", "3", "Red"],
         ["Dave", "65", "4", "Blue"],
     ], "has_header": True},
    {"id": "table_merged_cells", "category": "tables", "kind": "table", "font": "latin",
     "rows": [["Region", "Region", "Q1", "Q2"], ["North", "North", "10", "20"]],
     "has_header": True, "merges": [(0, 0, 2)]},
    {"id": "table_borderless", "category": "tables", "kind": "table", "font": "latin",
     "rows": [["Item", "Cost"], ["Pen", "2"], ["Notebook", "5"]],
     "has_header": True, "border_style": "none"},
    {"id": "table_partial_borders", "category": "tables", "kind": "table", "font": "latin",
     "rows": [["Item", "Cost"], ["Pen", "2"], ["Notebook", "5"]],
     "has_header": True, "border_style": "partial"},
    {"id": "table_multiline_cells", "category": "tables", "kind": "table", "font": "latin",
     "rows": [["Item", "Notes"], ["Widget\n(large)", "In stock\nships free"]],
     "has_header": True, "multiline_row": 1, "col_width": 160},
    {"id": "table_financial", "category": "tables", "kind": "table", "font": "latin",
     "rows": [["Account", "Amount", "Change"], ["Revenue", "$12,450.00", "+4.2%"],
              ["Refunds", "-$320.50", "-1.1%"]],
     "has_header": True, "col_width": 150},
    {"id": "table_urdu", "category": "tables", "kind": "table", "font": "arabic",
     "rows": [["نام", "عمر"], ["علی", "25"], ["سارہ", "30"]],
     "has_header": True},
    {"id": "table_mixed", "category": "tables", "kind": "table", "font": "latin",
     "rows": [["Product", "نام"], ["Pen", "قلم"], ["Book", "کتاب"]],
     "has_header": True},

    # --- Urdu: shaped via arabic_reshaper+bidi (see module docstring) ---
    {"id": "urdu_simple_sentence", "category": "urdu", "kind": "text", "font": "arabic",
     "text": "سلام دنیا"},
    {"id": "urdu_paragraph", "category": "urdu", "kind": "text", "font": "arabic",
     "text": "سلام دنیا یہ ایک جملہ ہے۔ یہ دوسرا جملہ ہے۔ یہ تیسرا جملہ ہے۔"},
    {"id": "urdu_numbers", "category": "urdu", "kind": "text", "font": "arabic",
     "text": "نمبر 12345 اور 67890"},
    {"id": "urdu_punctuation", "category": "urdu", "kind": "text", "font": "arabic",
     "text": "کیا آپ ٹھیک ہیں؟ جی ہاں، شکریہ!"},
    {"id": "urdu_brand_term", "category": "urdu", "kind": "text", "font": "arabic",
     "text": "یہ Local Lens ایپ ہے"},
    {"id": "mixed_urdu_english", "category": "mixed", "kind": "text", "font": "arabic",
     "text": "Order نمبر 12345 confirmed"},

    # --- photo/scan: synthetic PIL transforms over a self-rendered document ---
    {"id": "photo_rotated", "category": "photo_scan", "kind": "transform", "base": _DOCUMENT_TEXT,
     "transforms": ["rotate"]},
    {"id": "photo_perspective", "category": "photo_scan", "kind": "transform", "base": _DOCUMENT_TEXT,
     "transforms": ["perspective"]},
    {"id": "photo_low_light", "category": "photo_scan", "kind": "transform", "base": _DOCUMENT_TEXT,
     "transforms": ["uneven_lighting"]},
    {"id": "photo_low_contrast", "category": "photo_scan", "kind": "transform", "base": _DOCUMENT_TEXT,
     "transforms": ["low_contrast"]},
    {"id": "photo_full_camera", "category": "photo_scan", "kind": "transform", "base": _DOCUMENT_TEXT,
     "transforms": ["rotate", "perspective", "uneven_lighting"]},
    {"id": "scan_clean", "category": "photo_scan", "kind": "transform", "base": _DOCUMENT_TEXT,
     "transforms": ["grayscale_scan"]},
]

_TRANSFORM_FNS = {
    "rotate": lambda img: _apply_rotation(img, 4),
    "perspective": _apply_perspective,
    "uneven_lighting": _apply_uneven_lighting,
    "low_contrast": _apply_low_contrast,
    "grayscale_scan": _apply_grayscale_scan,
}


def _render_transform_image(entry: dict) -> Image.Image:
    img = _render_document_page(entry["base"])
    for name in entry["transforms"]:
        img = _TRANSFORM_FNS[name](img)
    return img


def ensure_corpus() -> list[dict]:
    """Materialize every fixture's image + ground truth if missing. Returns CORPUS."""
    for entry in CORPUS:
        category_dir = SAMPLES_DIR / entry["category"]
        gt_category_dir = GROUND_TRUTH_DIR / entry["category"]
        category_dir.mkdir(parents=True, exist_ok=True)
        gt_category_dir.mkdir(parents=True, exist_ok=True)

        image_path = category_dir / f"{entry['id']}.png"
        gt_path = gt_category_dir / f"{entry['id']}.json"

        if not image_path.exists():
            if entry["kind"] == "table":
                img = _render_table_image(
                    entry["rows"],
                    border_style=entry.get("border_style", "full"),
                    font_family=entry.get("font", "latin"),
                    col_width=entry.get("col_width", 130),
                    merges=entry.get("merges"),
                    multiline_row=entry.get("multiline_row"),
                )
            elif entry["kind"] == "transform":
                img = _render_transform_image(entry)
            else:
                img = _render_text_image(entry["text"], entry["font"], wrap=entry.get("wrap", False))
            img.save(image_path)

        if not gt_path.exists():
            if entry["kind"] == "table":
                payload = {"kind": "table", "rows": entry["rows"], "has_header": entry["has_header"]}
            elif entry["kind"] == "transform":
                payload = {"kind": "text", "text": entry["base"]}
            else:
                payload = {"kind": "text", "text": entry["text"]}
            gt_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return CORPUS


def image_path_for(entry: dict) -> Path:
    return SAMPLES_DIR / entry["category"] / f"{entry['id']}.png"
