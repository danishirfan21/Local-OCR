"""Monitor selection + screenshot grab -- QScreen only, no external
dependency (QGuiApplication.screenAt/QScreen.grabWindow proved sufficient;
see docs/V6_3_CAPTURE.md for the mss evaluation)."""

from __future__ import annotations

from PySide6.QtGui import QCursor, QGuiApplication, QPixmap, QScreen


def screen_under_cursor() -> QScreen:
    """Prefers the monitor the mouse is currently on; falls back to the
    primary screen if that can't be determined (e.g. the cursor is
    momentarily outside every screen's geometry)."""
    screen = QGuiApplication.screenAt(QCursor.pos())
    return screen if screen is not None else QGuiApplication.primaryScreen()


def grab_screen(screen: QScreen) -> QPixmap:
    return screen.grabWindow(0)
