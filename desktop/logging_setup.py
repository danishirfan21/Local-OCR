"""Lightweight desktop event logging.

Deliberately logs only event names (startup, hotkey registered/failed/
triggered, capture lifecycle, warm-up outcome, shutdown) -- never the
Gemini key, .env contents, OCR text, or screenshot/image bytes. Callers
must pass short, generic messages, not extracted text or file contents.

A --windowed PyInstaller build has no console: sys.stdout/sys.stderr are
None, and a plain StreamHandler crashes the moment it tries to write to
them. This adds a small rotating file handler under the OS's per-user app
data location (so startup failures in a windowed packaged build are still
diagnosable, item 10) and only attaches the console handler when a real
stream actually exists.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "local_lens.desktop"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 2
_LOG_FILE_NAME = "local_lens.log"


def log_directory() -> Path:
    """Per-user app-data directory for Local Lens's log file -- Qt's own
    AppDataLocation convention, so this lands in the same family of
    locations Windows users already expect app data to live (distinct
    from AppSettings's QSettings registry storage)."""
    try:
        from PySide6.QtCore import QStandardPaths

        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    except ImportError:
        base = ""
    if not base:
        base = str(Path.home() / "Local Lens")
    return Path(base)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

        if sys.stderr is not None:
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)

        try:
            directory = log_directory()
            directory.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                directory / _LOG_FILE_NAME, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            pass  # best-effort -- a logging failure must never block startup

    logger.setLevel(level)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)
