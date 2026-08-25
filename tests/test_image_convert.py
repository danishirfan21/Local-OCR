"""QImage -> PNG bytes conversion tests -- width/height/pixel values
preserved, no accidental channel swap, no lossy compression."""

from __future__ import annotations

import io

import pytest

pytest.importorskip("PySide6")

from PIL import Image  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402

from desktop.capture.image_convert import qimage_to_png_bytes  # noqa: E402


def _solid_color_qimage(width: int, height: int, color: QColor) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(color)
    return image


def test_round_trip_preserves_width_and_height():
    image = _solid_color_qimage(37, 21, QColor(10, 20, 30))
    png_bytes = qimage_to_png_bytes(image)
    pil_image = Image.open(io.BytesIO(png_bytes))
    assert pil_image.size == (37, 21)


def test_round_trip_preserves_rgb_values_without_channel_swap():
    image = _solid_color_qimage(5, 5, QColor(200, 60, 10))  # distinct R/G/B so a swap is detectable
    png_bytes = qimage_to_png_bytes(image)
    pil_image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    assert pil_image.getpixel((2, 2)) == (200, 60, 10)


def test_output_is_a_valid_lossless_png_not_jpeg():
    image = _solid_color_qimage(4, 4, QColor(0, 0, 0))
    png_bytes = qimage_to_png_bytes(image)
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_distinct_pixels_are_preserved_exactly():
    image = QImage(2, 1, QImage.Format.Format_RGB32)
    image.setPixelColor(0, 0, QColor(255, 0, 0))
    image.setPixelColor(1, 0, QColor(0, 255, 0))
    png_bytes = qimage_to_png_bytes(image)
    pil_image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    assert pil_image.getpixel((0, 0)) == (255, 0, 0)
    assert pil_image.getpixel((1, 0)) == (0, 255, 0)
