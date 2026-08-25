"""Pure popup-placement math -- global desktop coordinates, including a
monitor with a negative origin. See desktop/result/positioning.py."""

from __future__ import annotations

from desktop.capture.geometry import PixelRect
from desktop.result.positioning import place_popup

_MONITOR = PixelRect(left=0, top=0, width=1920, height=1080)


def test_places_popup_below_selection_when_it_fits():
    selection = PixelRect(left=100, top=100, width=200, height=50)
    x, y = place_popup(selection, popup_width=300, popup_height=200, monitor=_MONITOR)
    assert (x, y) == (100, 162)  # bottom (150) + default 12px margin


def test_falls_back_above_selection_when_below_does_not_fit():
    selection = PixelRect(left=100, top=900, width=200, height=150)  # bottom = 1050, near monitor edge
    x, y = place_popup(selection, popup_width=300, popup_height=200, monitor=_MONITOR)
    assert y + 200 <= selection.top  # placed fully above the selection
    assert y >= _MONITOR.top


def test_falls_back_to_centered_when_neither_below_nor_above_fits():
    # A selection covering nearly the whole monitor vertically -- no room
    # above or below for a 200px-tall popup.
    selection = PixelRect(left=100, top=10, width=200, height=1060)
    x, y = place_popup(selection, popup_width=300, popup_height=200, monitor=_MONITOR)
    assert x == _MONITOR.left + (_MONITOR.width - 300) // 2
    assert y == _MONITOR.top + (_MONITOR.height - 200) // 2


def test_clamps_horizontally_when_selection_is_near_right_edge():
    selection = PixelRect(left=1850, top=100, width=50, height=50)
    x, y = place_popup(selection, popup_width=300, popup_height=200, monitor=_MONITOR)
    assert x + 300 <= _MONITOR.right
    assert x >= _MONITOR.left


def test_negative_monitor_origin_is_handled_correctly():
    # A monitor placed left of and above the primary one.
    monitor = PixelRect(left=-1920, top=-200, width=1920, height=1080)
    selection = PixelRect(left=-1800, top=-100, width=100, height=50)
    x, y = place_popup(selection, popup_width=300, popup_height=200, monitor=monitor)
    assert monitor.left <= x <= monitor.right - 300
    assert monitor.top <= y <= monitor.bottom - 200


def test_result_always_fits_within_monitor_bounds_for_a_large_popup():
    selection = PixelRect(left=0, top=0, width=10, height=10)
    x, y = place_popup(selection, popup_width=1920, popup_height=1080, monitor=_MONITOR)
    assert x >= _MONITOR.left
    assert y >= _MONITOR.top
    assert x + 1920 <= _MONITOR.right + 0  # exactly fits, never overflows
    assert y + 1080 <= _MONITOR.bottom + 0
