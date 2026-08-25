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
    """Where Fast OCR looks for EasyOCR's model weights. For the V6.6
    packaging smoke test this intentionally still resolves to the user's
    existing development cache (`~/.EasyOCR/model`) rather than a bundled
    copy -- see docs/V6_6_PACKAGING_SMOKE_TEST.md's model-strategy
    section for why, and item 16 for the future bundled-resource path
    this function is the seam for. Never hardcodes a specific user's home
    directory -- `Path.home()` resolves per-machine."""
    return Path.home() / ".EasyOCR" / "model"
