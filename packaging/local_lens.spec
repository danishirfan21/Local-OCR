# PyInstaller spec for the Local Lens desktop app (V6.6 packaging smoke
# test -- see docs/V6_6_PACKAGING_SMOKE_TEST.md for the full record of
# what this build was for and what it proved/didn't prove).
#
# onedir, not onefile: a onefile build re-extracts its full payload (this
# app is ~1.6-2.0GB, dominated by torch/PySide6/OpenCV) to a temp
# directory on every single launch, which is slow and raises AV
# suspicion for no benefit here -- see
# docs/V6_5_RELEASE_READINESS.md's packaging-comparison section.
#
# Build from the repo root with D:-only temp/build paths, e.g.:
#   $env:TEMP = "D:\DevTools\Temp"; $env:TMP = "D:\DevTools\Temp"
#   .venv\Scripts\python.exe -m PyInstaller packaging\local_lens.spec `
#       --distpath "D:\Local OCR\dist" --workpath "D:\Local OCR\build\pyinstaller"
#
# No icon file is bundled -- desktop/icon.py draws the tray/window icon
# at runtime, so there is no .ico asset to reference here (see item 18's
# "current runtime-generated icon is adequate for a first release").
#
# No credentials, no .env, and no EasyOCR model weights are referenced by
# this spec -- see the model-strategy section of
# docs/V6_6_PACKAGING_SMOKE_TEST.md for why model weights are
# deliberately NOT bundled in this smoke-test build.

import sys
from pathlib import Path

block_cipher = None

REPO_ROOT = Path.cwd()
ENTRY_SCRIPT = str(REPO_ROOT / "desktop" / "main.py")

# Conservative, evidence-based hidden imports -- added because a first
# packaged-run failure showed each one was missing, not speculatively.
# See docs/V6_6_PACKAGING_SMOKE_TEST.md's "PyInstaller warnings" section.
hiddenimports = [
    "easyocr",
    "cv2",
]

a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Paddle must never come back through packaging archaeology (item 38)
    # -- it is not installed in this venv, but excluding it explicitly
    # documents the intent even though PyInstaller can only ever bundle
    # what's actually importable.
    excludes=["paddle", "paddleocr", "paddlex"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocalLens",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed -- item 9: no terminal window for the real app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LocalLens",
)
