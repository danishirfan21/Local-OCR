"""Centralizes frozen-vs-development detection and resource/model-cache
path resolution (item 22) -- the only place in the desktop app that reads
`sys.frozen`/`sys._MEIPASS`, so packaging awareness doesn't spread into
app_controller.py, the result window, or anywhere else. No personal
paths are hardcoded anywhere in this module: every path is resolved at
call time from `sys.executable`/`sys._MEIPASS`/`Path.home()`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """True inside a PyInstaller-built executable, False for a normal
    `python -m desktop.main` / `pytest` run."""
    return getattr(sys, "frozen", False)


def app_base_dir() -> Path:
    """The directory containing the running application: the `.exe`'s own
    directory when frozen, the repository root otherwise. Not the same as
    `resource_path()`'s bundle root -- this is for things that live
    *beside* the executable (e.g. a portable `.env`), not bundled data
    files."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Resolves a bundled data-file path for both source-checkout and
    frozen execution. PyInstaller onedir/onefile builds extract (or copy)
    bundled data next to `sys._MEIPASS`; a source checkout resolves the
    same relative path from the repository root. Local Lens currently
    bundles no data files (the tray/window icon is drawn at runtime, see
    desktop/icon.py) -- this exists so a future asset can be added without
    scattering a new frozen-path check somewhere else."""
    base = Path(getattr(sys, "_MEIPASS", None) or app_base_dir())
    return base.joinpath(*parts)


def easyocr_model_directory() -> Path:
    """The user's own EasyOCR development cache (`~/.EasyOCR/model`) --
    where EasyOCR itself defaults to looking, and where both the V6.6 and
    V6.7 builds get their model weights from (see
    docs/V6_6_PACKAGING_SMOKE_TEST.md / docs/V6_7_PORTABLE_OPTIMIZATION.md's
    model-strategy sections). Never hardcodes a specific user's home
    directory -- `Path.home()` resolves per-machine."""
    return Path.home() / ".EasyOCR" / "model"


def resolve_easyocr_model_dir() -> Path:
    """Where Fast OCR should actually look for EasyOCR's model weights --
    the one function every caller should use instead of picking a path
    directly, so packaged-vs-dev model resolution stays centralized here
    (item 18).

    Checks a *bundled* `models/easyocr/` resource directory first (the
    seam for a future release build that ships model weights alongside
    the packaged exe -- see item 19/24), falling back to the user's own
    development cache. No build has ever populated the bundled directory
    as of V6.7 -- it will simply not exist, and this always falls
    through to `easyocr_model_directory()` today. That fallback is not a
    silent-download risk: `local_lens.engines.easyocr_engine`'s
    `download_enabled=False` (wired from desktop/ocr_service_factory.py)
    is what actually prevents a surprise download if the resolved
    directory turns out to be missing or incomplete -- this function only
    decides *where* to look, never whether it's acceptable to fetch
    something that isn't there.
    """
    bundled = resource_path("models", "easyocr")
    if bundled.is_dir():
        return bundled
    return easyocr_model_directory()
