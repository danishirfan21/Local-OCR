"""Pure coordinate-math tests for region selection -- no Qt, no screen,
no Windows API. See desktop/capture/geometry.py."""

from __future__ import annotations

from desktop.capture.geometry import (
    PixelRect,
    clamp_to_bounds,
    is_too_small,
    logical_to_physical,
    normalize_rect,
)


def test_normalize_rect_top_left_to_bottom_right():
    rect = normalize_rect(10, 20, 110, 220)
    assert rect == PixelRect(left=10, top=20, width=100, height=200)


def test_normalize_rect_bottom_right_to_top_left():
    rect = normalize_rect(110, 220, 10, 20)
    assert rect == PixelRect(left=10, top=20, width=100, height=200)


def test_normalize_rect_top_right_to_bottom_left():
    rect = normalize_rect(110, 20, 10, 220)
    assert rect == PixelRect(left=10, top=20, width=100, height=200)


def test_normalize_rect_bottom_left_to_top_right():
    rect = normalize_rect(10, 220, 110, 20)
    assert rect == PixelRect(left=10, top=20, width=100, height=200)


def test_normalize_rect_zero_size_drag():
    rect = normalize_rect(50, 50, 50, 50)
    assert rect == PixelRect(left=50, top=50, width=0, height=0)


def test_logical_to_physical_at_100_percent_dpi_is_identity():
    rect = PixelRect(left=10, top=20, width=100, height=200)
    assert logical_to_physical(rect, 1.0) == rect


def test_logical_to_physical_at_125_percent_dpi():
    # Values chosen to divide evenly at 1.25x so the expected result is
    # unambiguous regardless of round-half-to-even vs round-half-up.
    rect = PixelRect(left=8, top=16, width=80, height=160)
    physical = logical_to_physical(rect, 1.25)
    assert physical == PixelRect(left=10, top=20, width=100, height=200)


def test_logical_to_physical_at_150_percent_dpi():
    rect = PixelRect(left=10, top=20, width=100, height=200)
    physical = logical_to_physical(rect, 1.5)
    assert physical == PixelRect(left=15, top=30, width=150, height=300)


def test_logical_to_physical_never_depends_on_a_negative_global_origin():
    # Overlay-local coordinates start at (0, 0) regardless of the
    # monitor's global desktop position -- a monitor placed left of or
    # above the primary one (negative geometry.x()/y()) never appears in
    # this function's inputs at all, by construction.
    rect = PixelRect(left=0, top=0, width=40, height=40)
    assert logical_to_physical(rect, 1.25) == PixelRect(left=0, top=0, width=50, height=50)


def test_clamp_to_bounds_leaves_in_bounds_rect_unchanged():
    rect = PixelRect(left=10, top=10, width=50, height=50)
    assert clamp_to_bounds(rect, 1920, 1080) == rect


def test_clamp_to_bounds_clips_overflow_past_right_and_bottom_edge():
    rect = PixelRect(left=1900, top=1060, width=100, height=100)
    clamped = clamp_to_bounds(rect, 1920, 1080)
    assert clamped == PixelRect(left=1900, top=1060, width=20, height=20)


def test_clamp_to_bounds_clips_negative_origin():
    rect = PixelRect(left=-10, top=-10, width=50, height=50)
    clamped = clamp_to_bounds(rect, 1920, 1080)
    assert clamped == PixelRect(left=0, top=0, width=40, height=40)


def test_is_too_small_rejects_below_minimum():
    assert is_too_small(PixelRect(0, 0, 5, 5), minimum=10) is True
    assert is_too_small(PixelRect(0, 0, 9, 100), minimum=10) is True


def test_is_too_small_accepts_at_or_above_minimum():
    assert is_too_small(PixelRect(0, 0, 10, 10), minimum=10) is False
    assert is_too_small(PixelRect(0, 0, 100, 100), minimum=10) is False
