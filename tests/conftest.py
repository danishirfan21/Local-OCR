"""Session-wide test isolation for desktop logging.

desktop.logging_setup writes a small rotating log file under the OS's
real per-user app-data directory (item 10) -- exactly the kind of real
user-state write this project's other desktop tests are careful to avoid
(see AppSettings's temp-file QSettings pattern, the fake hotkey/registry
adapters). This autouse fixture redirects it to a pytest tmp_path before
any test can trigger it, without importing PySide6 at collection time so
non-desktop test runs (no PySide6 installed) are unaffected.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_desktop_log_directory(tmp_path, monkeypatch):
    try:
        import desktop.logging_setup as logging_setup
    except ImportError:
        yield
        return
    monkeypatch.setattr(logging_setup, "log_directory", lambda: tmp_path / "logs")
    yield
