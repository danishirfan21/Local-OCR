"""Heuristic input-type classification: screenshot vs. photo vs. document scan.

This feeds engine routing, not user-facing certainty -- it is a handful of
cheap image-property heuristics, not a trained classifier, and confidence is
capped well below 1.0 accordingly. The signals:

- EXIF metadata presence: cameras/phones attach EXIF; screenshot tools and
  most screen-capture pipelines do not. Presence leans "photo"; absence is
  weak evidence (not proof) of "screenshot" or "scan".
- Unique-color ratio: rendered UI (screenshots) tends to use a small
  palette of flat colors; photos have continuous tonal variation and a much
  larger effective palette even after downsampling.
- Flat-region ratio (via PIL edge detection): screenshots have large flat
  areas (backgrounds, chrome); photos have texture almost everywhere.

None of these are reliable in isolation -- a photo of a mostly-blank wall
or a screenshot of a photo-heavy webpage will confuse this. That's why the
result is always paired with a confidence and surfaced as "why", not
asserted as fact.
"""

from __future__ import annotations

from PIL import Image, ImageFilter

INPUT_SCREENSHOT = "screenshot"
INPUT_PHOTO = "photo"
INPUT_DOCUMENT_SCAN = "document_scan"
INPUT_UNKNOWN = "unknown"

_ANALYSIS_SIZE = (200, 200)


def _has_exif(image: Image.Image) -> bool:
    try:
        exif = image.getexif()
        return exif is not None and len(exif) > 0
    except Exception:
        return False


def _unique_color_ratio(sample: Image.Image) -> float:
    colors = sample.convert("RGB").getcolors(maxcolors=_ANALYSIS_SIZE[0] * _ANALYSIS_SIZE[1])
    if colors is None:
        return 1.0  # more unique colors than pixels sampled -- very high variety
    total_pixels = _ANALYSIS_SIZE[0] * _ANALYSIS_SIZE[1]
    return len(colors) / total_pixels


def _flat_region_ratio(sample: Image.Image) -> float:
    edges = sample.convert("L").filter(ImageFilter.FIND_EDGES)
    pixels = list(edges.getdata())
    flat = sum(1 for p in pixels if p < 16)
    return flat / len(pixels)


def _grayscale_like_ratio(sample: Image.Image) -> float:
    rgb = sample.convert("RGB")
    pixels = list(rgb.getdata())
    if not pixels:
        return 0.0
    low_saturation = sum(1 for r, g, b in pixels if max(r, g, b) - min(r, g, b) < 12)
    return low_saturation / len(pixels)


def classify_input(image: Image.Image) -> tuple[str, float]:
    """Return (input_type, confidence) using cheap image-property heuristics."""
    sample = image.convert("RGB").resize(_ANALYSIS_SIZE, Image.BILINEAR)

    exif_present = _has_exif(image)
    unique_ratio = _unique_color_ratio(sample)
    flat_ratio = _flat_region_ratio(sample)
    gray_ratio = _grayscale_like_ratio(sample)

    if exif_present and unique_ratio > 0.15:
        return INPUT_PHOTO, 0.6

    if unique_ratio < 0.06 and flat_ratio > 0.55:
        return INPUT_SCREENSHOT, 0.65

    if gray_ratio > 0.7 and flat_ratio > 0.35 and not exif_present:
        return INPUT_DOCUMENT_SCAN, 0.5

    if unique_ratio > 0.25:
        return INPUT_PHOTO, 0.45

    return INPUT_UNKNOWN, 0.0
