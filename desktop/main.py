"""Entry point: `python -m desktop.main` from the repo root."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from desktop.app_controller import DesktopApplication
from desktop.startup import START_HIDDEN_FLAG


def main() -> int:
    # Launched by Windows startup (desktop/startup.py's Run-key command)
    # rather than by hand -- start quietly in the tray, not with the main
    # window popping up at login (item 6).
    start_hidden = START_HIDDEN_FLAG in sys.argv[1:]

    app = QApplication(sys.argv)
    app.setApplicationName("Local Lens")
    app.setOrganizationName("Local Lens")

    controller = DesktopApplication(  # noqa: F841 -- must stay alive for the app's lifetime
        app, start_hidden=start_hidden
    )
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
