"""Pure coordinate math for region selection -- no Qt widgets, no Windows
API. Kept separate and dependency-free so it's trivially unit-tested
(tests/test_capture_geometry.py) without a real Qt event loop or screen.

Key design invariant, verified empirically on this machine (125% DPI,
single monitor): `QScreen.geometry()` is in *logical* pixels (what mouse
events and widget positioning use); the QPixmap returned by
`QScreen.grabWindow(0)` is stored at *physical* pixel resolution, tagged
with a `devicePixelRatio()` matching the screen's. Cropping that pixmap
therefore needs physical-pixel coordinates, so overlay-local logical
selection coordinates must be scaled by the screen's device pixel ratio
before use.

A second invariant these functions rely on: because the overlay window is
created with `setGeometry(screen.geometry())`, mouse-event coordinates
inside it are already local to that one monitor (0,0 at its top-left) --
Qt widget coordinates are always local to the widget, never global desktop
coordinates. This means a monitor with a negative global desktop origin
(one placed left of or above the primary monitor) needs no special-casing
here: these functions never see or need the monitor's global (x, y)
offset at all.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PixelRect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


def normalize_rect(x1: float, y1: float, x2: float, y2: float) -> PixelRect:
    """Turns a drag between any two points, in any direction (top-left to
    bottom-right, bottom-right to top-left, or either off-axis
    combination), into a positive-size, top-left-origin rect."""
    left = min(x1, x2)
    top = min(y1, y2)
    width = abs(x2 - x1)
    height = abs(y2 - y1)
    return PixelRect(left=round(left), top=round(top), width=round(width), height=round(height))


def logical_to_physical(rect: PixelRect, device_pixel_ratio: float) -> PixelRect:
    """Converts an overlay-local logical-pixel rect into the physical-pixel
    rect needed to crop a QPixmap grabbed via QScreen.grabWindow()."""
    return PixelRect(
        left=round(rect.left * device_pixel_ratio),
        top=round(rect.top * device_pixel_ratio),
        width=round(rect.width * device_pixel_ratio),
        height=round(rect.height * device_pixel_ratio),
    )


def clamp_to_bounds(rect: PixelRect, bounds_width: int, bounds_height: int) -> PixelRect:
    """Clips a rect to [0, bounds_width) x [0, bounds_height) so cropping
    never reads outside the screenshot -- defensive against a drag that
    ends slightly past the overlay edge, or a fractional-DPI rounding
    edge case in logical_to_physical()."""
    left = max(0, min(rect.left, bounds_width))
    top = max(0, min(rect.top, bounds_height))
    right = max(0, min(rect.right, bounds_width))
    bottom = max(0, min(rect.bottom, bounds_height))
    return PixelRect(left=left, top=top, width=max(0, right - left), height=max(0, bottom - top))


def is_too_small(rect: PixelRect, minimum: int = 10) -> bool:
    return rect.width < minimum or rect.height < minimum
