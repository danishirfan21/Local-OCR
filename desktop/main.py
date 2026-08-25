"""Entry point: `python -m desktop.main` from the repo root."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from desktop.app_controller import DesktopApplication


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local Lens")
    app.setOrganizationName("Local Lens")

    controller = DesktopApplication(app)  # noqa: F841 -- must stay alive for the app's lifetime
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
