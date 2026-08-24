"""Optional image preprocessing pipeline.

Pure PIL (no OpenCV dependency, to keep the core install light -- see
requirements.txt). Three presets are exposed; the default ("none") is
conservative on purpose, since aggressive preprocessing can hurt OCR quality
on already-clean screenshots as easily as it helps noisy photos.
"""

from __future__ import annotations

from PIL import Image, ImageEnhance, ImageOps

PRESET_NONE = "none"
PRESET_AUTO = "auto"
PRESET_HIGH_CONTRAST = "high_contrast"

PRESETS = [PRESET_NONE, PRESET_AUTO, PRESET_HIGH_CONTRAST]

_MAX_DIM = 2200


def normalize_orientation(image: Image.Image) -> Image.Image:
    """Apply EXIF orientation so rotated phone photos display/OCR upright."""
    return ImageOps.exif_transpose(image) or image


def to_rgb(image: Image.Image) -> Image.Image:
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def resize_max_dim(image: Image.Image, max_dim: int = _MAX_DIM) -> Image.Image:
    if max(image.size) <= max_dim:
        return image
    ratio = max_dim / max(image.size)
    new_size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
    return image.resize(new_size, Image.LANCZOS)


def enhance_contrast(image: Image.Image, factor: float = 1.4) -> Image.Image:
    return ImageEnhance.Contrast(image).enhance(factor)


def to_grayscale(image: Image.Image) -> Image.Image:
    return ImageOps.grayscale(image)


def apply_preset(image: Image.Image, preset: str) -> Image.Image:
    """Apply a named preprocessing preset and return a new image.

    - none: orientation fix + size cap only (safe baseline, always applied)
    - auto: + mild contrast boost, still conservative
    - high_contrast: + grayscale and a stronger contrast boost, for faint or
      low-contrast screenshots/photos
    """
    if preset not in PRESETS:
        raise ValueError(f"Unknown preprocessing preset: {preset!r}")

    image = normalize_orientation(image)
    image = to_rgb(image)
    image = resize_max_dim(image)

    if preset == PRESET_NONE:
        return image

    if preset == PRESET_AUTO:
        return enhance_contrast(image, factor=1.25)

    # high_contrast
    image = to_grayscale(image)
    image = enhance_contrast(image, factor=1.8)
    return image.convert("RGB")
