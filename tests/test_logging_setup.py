"""desktop.logging_setup tests -- verifies a --windowed build (no
console, sys.stderr is None) doesn't crash, and that a file handler is
attached so packaged startup failures stay diagnosable (item 10)."""

from __future__ import annotations

import logging

import desktop.logging_setup as logging_setup


def _fresh_logger():
    logger = logging.getLogger(logging_setup._LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    return logger


def test_setup_logging_attaches_a_file_handler(tmp_path, monkeypatch):
    monkeypatch.setattr(logging_setup, "log_directory", lambda: tmp_path / "logs")
    _fresh_logger()

    logger = logging_setup.setup_logging()
    logger.info("test message")
    for handler in logger.handlers:
        handler.flush()

    log_file = tmp_path / "logs" / "local_lens.log"
    assert log_file.exists()
    assert "test message" in log_file.read_text(encoding="utf-8")


def test_setup_logging_never_crashes_when_stderr_is_none(tmp_path, monkeypatch):
    # The exact condition a --windowed PyInstaller build hits -- no console
    # attached, sys.stdout/sys.stderr are None.
    monkeypatch.setattr(logging_setup, "log_directory", lambda: tmp_path / "logs")
    monkeypatch.setattr(logging_setup.sys, "stderr", None)
    _fresh_logger()

    logger = logging_setup.setup_logging()  # must not raise
    logger.info("windowed build test message")

    log_file = tmp_path / "logs" / "local_lens.log"
    assert log_file.exists()


def test_get_logger_returns_the_same_named_logger():
    assert logging_setup.get_logger().name == logging_setup._LOGGER_NAME


def test_log_directory_resolves_to_a_path():
    # Exercises the real (non-monkeypatched) code path against the actual
    # installed PySide6 -- just confirms it resolves to something usable,
    # not a specific value (that's machine-dependent).
    from pathlib import Path

    result = logging_setup.log_directory()
    assert isinstance(result, Path)
    assert str(result)
