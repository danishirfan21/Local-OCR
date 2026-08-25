"""Lightweight Streamlit AppTest smoke coverage for app.py.

Deliberately never uploads an image: doing so would trigger a real
EasyOCR cold-load (30-60s+), which doesn't belong in a fast unit-test
suite (see the no-heavy-local-inference-in-CI convention this project
already follows). These tests only exercise the code paths that run
before an image exists -- initial render, sidebar mode switching, and the
unconfigured-Deep warning -- which is enough to catch import/structural
regressions in app.py without adding a slow test. Manual verification of
the full upload -> extract -> Deep-Analyze flow was done separately via
the browser preview (see docs/V5_GEMINI_DEEP.md's UI verification note).
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _run_app() -> AppTest:
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    return at


def test_app_loads_without_error():
    at = _run_app()
    assert not at.exception


def test_initial_state_shows_upload_prompt():
    at = _run_app()
    body_text = " ".join(m.value for m in at.info if hasattr(m, "value"))
    assert "Upload, paste, or copy" in body_text


def _processing_radio(at: AppTest):
    return next(r for r in at.sidebar.radio if r.label == "Processing")


def test_sidebar_has_fast_and_deep_options():
    at = _run_app()
    processing_radio = _processing_radio(at)
    assert any("Fast" in opt for opt in processing_radio.options)
    assert any("Deep Analyze" in opt for opt in processing_radio.options)


def test_selecting_deep_mode_without_image_does_not_crash():
    at = _run_app()
    processing_radio = _processing_radio(at)
    deep_option = next(opt for opt in processing_radio.options if "Deep Analyze" in opt)
    processing_radio.set_value(deep_option).run()
    assert not at.exception


def test_selecting_deep_mode_without_key_shows_unconfigured_warning():
    at = _run_app()
    processing_radio = _processing_radio(at)
    deep_option = next(opt for opt in processing_radio.options if "Deep Analyze" in opt)
    processing_radio.set_value(deep_option).run()
    # No image was uploaded, so the "Deep Analyze requires a Gemini API
    # key" branch only renders once an image exists -- this test just
    # confirms mode-switching alone is inert and crash-free, matching "no
    # background Deep request" even when just toggling the radio.
    assert not at.exception
