"""Backend capability/status model.

The UI and CLI should ask "what's available and why" through this module
rather than probing `try: import paddleocr` / env vars ad hoc in multiple
places. Keeps "not installed" (a local package is missing), "not
configured" (no remote provider set up), "unreachable" (configured but the
network/host didn't respond), and "authentication failed" (configured and
reachable, but rejected) as distinct, non-confusable states.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BackendMode = Literal["local", "remote"]


@dataclass(frozen=True)
class BackendStatus:
    name: str
    available: bool
    mode: BackendMode
    reason: str | None = None


def fast_backend_statuses() -> list[BackendStatus]:
    """Statuses for the Fast-mode local engines. EasyOCR is always required;
    PaddleOCR is optional and Fast mode must work without it."""
    from local_lens.engines.easyocr_engine import EasyOCREngine  # noqa: F401

    statuses = [BackendStatus(name="easyocr", available=True, mode="local")]

    try:
        from local_lens.engines.paddleocr_engine import PADDLEOCR_AVAILABLE
    except ImportError:
        PADDLEOCR_AVAILABLE = False

    statuses.append(
        BackendStatus(
            name="paddleocr",
            available=PADDLEOCR_AVAILABLE,
            mode="local",
            reason=None if PADDLEOCR_AVAILABLE else "not installed (optional -- Fast mode works without it)",
        )
    )
    return statuses


def table_backend_status() -> BackendStatus:
    try:
        from local_lens.tables.paddle_table_extractor import TABLE_EXTRACTION_AVAILABLE
    except ImportError:
        TABLE_EXTRACTION_AVAILABLE = False

    return BackendStatus(
        name="paddleocr_table",
        available=TABLE_EXTRACTION_AVAILABLE,
        mode="local",
        reason=None if TABLE_EXTRACTION_AVAILABLE else "not installed (table extraction unavailable locally)",
    )


def legacy_local_deep_status() -> BackendStatus:
    """The old local-PaddleOCR-VL path (local_lens/engines/paddleocr_vl_engine.py).
    Kept for environments that explicitly opt into the heavy local stack
    (e.g. a cloud/dev box); never required for normal Deep Analyze use."""
    try:
        from local_lens.engines.paddleocr_vl_engine import PADDLEOCR_VL_AVAILABLE
    except ImportError:
        PADDLEOCR_VL_AVAILABLE = False

    return BackendStatus(
        name="paddleocr_vl_local",
        available=PADDLEOCR_VL_AVAILABLE,
        mode="local",
        reason=None if PADDLEOCR_VL_AVAILABLE else "not installed (optional legacy heavy backend, not required)",
    )


def deep_backend_status() -> BackendStatus:
    """Status of the configured remote Deep Analyze provider (BYOK)."""
    from local_lens.deep_analysis.config import describe_deep_provider_config

    return describe_deep_provider_config()
