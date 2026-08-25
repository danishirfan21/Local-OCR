"""Generates packaging/assets/app_icon.ico -- the .exe file icon used by
packaging/local_lens.spec. Mirrors desktop/icon.py's in-app tray/window
icon exactly (a blue circle with a white "L", drawn programmatically, no
downloaded asset) so the packaged executable's file icon matches what
the running app already shows.

Run manually when the icon design changes:
    .venv\\Scripts\\python.exe packaging\\generate_icon.py

Not run automatically by the build -- the committed .ico is the actual
build input (see local_lens.spec's `icon=` argument), matching item 25's
"very simple original placeholder icon... no downloaded icon pack."
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_OUTPUT_PATH = Path(__file__).resolve().parent / "assets" / "app_icon.ico"
_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _make_layer(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(1, size // 16)
    draw.ellipse([margin, margin, size - margin, size - margin], fill=(47, 111, 237, 255))

    font_size = int(size * 0.55)
    try:
        font = ImageFont.truetype("arialbd.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    text = "L"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]), text, fill=(255, 255, 255, 255), font=font)
    return img


def generate() -> Path:
    largest = _make_layer(max(_SIZES))
    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    largest.save(_OUTPUT_PATH, sizes=[(s, s) for s in _SIZES])
    return _OUTPUT_PATH


if __name__ == "__main__":
    path = generate()
    print(f"wrote {path}")
