"""Lightweight desktop event logging.

Deliberately logs only event names (startup, hotkey registered/failed/
triggered, shutdown) -- never the Gemini key, .env contents, OCR text, or
screenshot/image bytes. Callers must pass short, generic messages, not
extracted text or file contents.
"""

from __future__ import annotations

import logging

_LOGGER_NAME = "local_lens.desktop"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)
