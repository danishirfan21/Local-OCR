"""Pure popup-placement math -- no Qt, no widgets. Unlike
desktop/capture/geometry.py (deliberately monitor-local, global origin
never matters for cropping), placing an actual window requires *global*
desktop coordinates, since QWidget.move() positions in the shared virtual-
desktop coordinate space -- a monitor placed left of or above the primary
one (negative geometry().x()/y()) is a real input here, not something to
ignore.
"""

from __future__ import annotations

from desktop.capture.geometry import PixelRect

_DEFAULT_MARGIN = 12


def place_popup(
    selection: PixelRect,
    popup_width: int,
    popup_height: int,
    monitor: PixelRect,
    margin: int = _DEFAULT_MARGIN,
) -> tuple[int, int]:
    """Returns the (x, y) top-left position, in the same global coordinate
    space as `selection` and `monitor`, to place a popup of the given size.

    Preference order: below the selection, then above it, then centered on
    the monitor -- each candidate is only used if the popup would fit
    entirely within the monitor vertically; the final position is always
    clamped to the monitor bounds regardless of which branch was used, so
    a popup can never end up partially or fully off-screen.
    """
    x = selection.left
    y = selection.bottom + margin

    if y + popup_height > monitor.bottom:
        y = selection.top - margin - popup_height
        if y < monitor.top:
            # Neither below nor above fits -- center on the monitor instead.
            x = monitor.left + (monitor.width - popup_width) // 2
            y = monitor.top + (monitor.height - popup_height) // 2

    x = max(monitor.left, min(x, monitor.right - popup_width))
    y = max(monitor.top, min(y, monitor.bottom - popup_height))
    return x, y
