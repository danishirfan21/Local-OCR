"""Benchmark corpus: fixture definitions + synthetic generation.

All fixtures are synthetic (rendered via PIL) or trivially self-generated --
nothing copyrighted or private, per the V3 requirement to keep the corpus
safe to commit. Materializes benchmarks/samples/<category>/<id>.png and
benchmarks/ground_truth/<category>/<id>.json from CORPUS on first run;
images/ground-truth are regenerated if missing so the corpus is
reproducible without committing binary files (see .gitignore).

Urdu fixtures: this environment's Pillow build lacks the `raqm` text-shaping
library (checked via PIL.features.check("raqm")), so rendered Arabic-script
glyphs come out in isolated letterforms rather than properly joined
Nastaliq/Naskh script. This is a real fixture-quality limitation -- it means
Urdu benchmark numbers here should be read as "can the pipeline handle
Arabic-script Unicode text end-to-end" rather than "how accurate is this on
realistic joined Urdu," which would need a real screenshot or a
shaping-capable renderer.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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


# Each entry: id, category, kind ("text" or "table"), font family, and
# either `text` (kind="text") or `rows`+`has_header` (kind="table").
CORPUS = [
    {"id": "short_ui_save", "category": "short_ui", "kind": "text", "font": "latin",
     "text": "Save"},
    {"id": "short_ui_cancel", "category": "short_ui", "kind": "text", "font": "latin",
     "text": "Cancel Settings OK"},
    {"id": "paragraph", "category": "english", "kind": "text", "font": "latin",
     "text": "This is a normal paragraph of extracted text. It has several "
             "sentences and no special formatting at all in it."},
    {"id": "numeric", "category": "english", "kind": "text", "font": "latin",
     "text": "123456 789012 345 67890"},
    {"id": "english_numbers", "category": "english", "kind": "text", "font": "latin",
     "text": "Order 12345 confirmed for $99.50"},
    {"id": "code_snippet", "category": "code", "kind": "text", "font": "mono",
     "text": "def greet(name):\n    if name:\n        return f'Hi {name}'\n    return None"},
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
    {"id": "urdu_paragraph", "category": "urdu", "kind": "text", "font": "arabic",
     "text": "سلام دنیا یہ ایک جملہ ہے"},
    {"id": "mixed_urdu_english", "category": "mixed", "kind": "text", "font": "arabic",
     "text": "Order نمبر 12345 confirmed"},
    {"id": "urdu_numbers", "category": "urdu", "kind": "text", "font": "arabic",
     "text": "نمبر 12345 اور 67890"},
]


def font_available(family: str) -> bool:
    candidates = {"latin": _LATIN_FONT_CANDIDATES, "arabic": _ARABIC_FONT_CANDIDATES,
                  "mono": _MONO_FONT_CANDIDATES}[family]
    return any(Path(p).exists() for p in candidates)


def _render_text_image(text: str, font_family: str) -> Image.Image:
    candidates = {"latin": _LATIN_FONT_CANDIDATES, "arabic": _ARABIC_FONT_CANDIDATES,
                  "mono": _MONO_FONT_CANDIDATES}[font_family]
    font = _first_available_font(candidates, 26)
    lines = text.split("\n")
    line_height = 36
    width = max(500, max(len(line) for line in lines) * 16)
    img = Image.new("RGB", (width, line_height * len(lines) + 20), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((10, 10 + i * line_height), line, fill="black", font=font)
    return img


def _render_table_image(rows: list[list[str]]) -> Image.Image:
    font = _first_available_font(_LATIN_FONT_CANDIDATES, 20)
    n_cols = len(rows[0])
    col_width = 130
    row_height = 40
    width = col_width * n_cols + 10
    height = row_height * len(rows) + 10
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            draw.text((10 + c * col_width, 10 + r * row_height), val, fill="black", font=font)
    for x in range(0, width, col_width):
        draw.line([(x, 0), (x, height)], fill="black", width=1)
    draw.line([(width - 1, 0), (width - 1, height)], fill="black", width=1)
    for y in range(0, height, row_height):
        draw.line([(0, y), (width, y)], fill="black", width=1)
    draw.line([(0, height - 1), (width, height - 1)], fill="black", width=1)
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
                img = _render_table_image(entry["rows"])
            else:
                img = _render_text_image(entry["text"], entry["font"])
            img.save(image_path)

        if not gt_path.exists():
            if entry["kind"] == "table":
                payload = {"kind": "table", "rows": entry["rows"], "has_header": entry["has_header"]}
            else:
                payload = {"kind": "text", "text": entry["text"]}
            gt_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return CORPUS


def image_path_for(entry: dict) -> Path:
    return SAMPLES_DIR / entry["category"] / f"{entry['id']}.png"
