# PyInstaller spec for the Local Lens desktop app.
#
# onedir, not onefile: a onefile build re-extracts its full payload to a
# temp directory on every single launch, which is slow and raises AV
# suspicion for no benefit here -- see
# docs/V6_5_RELEASE_READINESS.md's packaging-comparison section.
#
# Build from the repo root with D:-only temp/build paths, e.g.:
#   $env:TEMP = "D:\DevTools\Temp"; $env:TMP = "D:\DevTools\Temp"
#   .venv\Scripts\python.exe -m PyInstaller packaging\local_lens.spec `
#       --distpath "D:\Local OCR\dist" --workpath "D:\Local OCR\build\pyinstaller"
#
# No credentials, no .env, and (by default) no EasyOCR model weights are
# referenced by this spec -- see docs/V6_7_PORTABLE_OPTIMIZATION.md's
# model-strategy section. Every build to date resolves models from the
# user's own ~/.EasyOCR/model cache at runtime (desktop/runtime_context.py's
# resolve_easyocr_model_dir()), not from anything this spec bundles.

import os
import sys
from pathlib import Path

block_cipher = None

REPO_ROOT = Path.cwd()
ENTRY_SCRIPT = str(REPO_ROOT / "desktop" / "main.py")
ICON_PATH = str(REPO_ROOT / "packaging" / "assets" / "app_icon.ico")
VERSION_FILE = str(REPO_ROOT / "packaging" / "version_info.txt")

# Conservative, evidence-based hidden imports -- added because a first
# packaged-run failure showed each one was missing, not speculatively.
# See docs/V6_6_PACKAGING_SMOKE_TEST.md's "PyInstaller warnings" section.
hiddenimports = [
    "easyocr",
    "cv2",
]

# Evidence-based excludes only -- see docs/V6_7_PORTABLE_OPTIMIZATION.md's
# dependency-analysis section for how each was verified, not guessed:
#
# - paddle/paddleocr/paddlex: not installed in this venv at all (Paddle
#   must never come back through packaging archaeology -- item 41).
# - pandas/pyarrow: confirmed via `pip show --Required-by` to be pulled
#   in ONLY by streamlit (which desktop/main.py's import graph never
#   touches), and empirically confirmed absent from sys.modules after a
#   real EasyOCR construction + inference call. PyInstaller's static
#   analysis over-approximates by including torch's own optional,
#   never-executed integrations (e.g. torch.utils.tensorboard's
#   conditional pandas import) -- these two packages are a build-time
#   false positive, not a runtime dependency.
#
# scipy is deliberately NOT excluded here -- the same empirical check
# showed 160 scipy submodules actually get imported during real EasyOCR
# inference (it's a genuine transitive runtime dependency of EasyOCR and
# scikit-image). Excluding it would break Fast OCR.
excludes = ["paddle", "paddleocr", "paddlex", "pandas", "pyarrow"]

# Seam for a release build to bundle EasyOCR model weights instead of
# relying on the external ~/.EasyOCR cache (V6.7 built the seam; V6.8
# actually populates it) -- unused unless LOCAL_LENS_RELEASE_MODEL_DIR is
# explicitly set. When set, the full filename+SHA-256+no-unexpected-files
# validator in packaging/validate_release_models.py must pass; any
# failure aborts the build immediately and explicitly rather than
# silently shipping an incomplete/wrong model set or downloading
# anything. See docs/V6_8_SELF_CONTAINED_RC.md for the exact files this
# checks, their hashes, and why.
sys.path.insert(0, str(REPO_ROOT / "packaging"))
from validate_release_models import ReleaseModelValidationError, validate_release_model_dir

datas = []
_release_model_dir = os.environ.get("LOCAL_LENS_RELEASE_MODEL_DIR")
if _release_model_dir:
    model_dir = Path(_release_model_dir)
    try:
        validate_release_model_dir(model_dir)
    except ReleaseModelValidationError as exc:
        raise SystemExit(
            f"Refusing to produce a bundled-model build: {exc} Unset LOCAL_LENS_RELEASE_MODEL_DIR "
            "to build with the external-cache strategy instead."
        )
    datas.append((str(model_dir), "models/easyocr"))

# Required attribution for the bundled EasyOCR (Apache-2.0) and
# CRAFT-pytorch (MIT) model weights -- both licenses require their notice
# text to travel with a binary redistribution, not just live in the
# source repo. V6.9 RC QA found this file was written (V6.8) but never
# actually added to `datas`, so it never reached the shipped ZIP. Bundled
# PyInstaller's onedir layout puts all `datas` under `_internal/` (same
# as the bundled model weights above) -- what matters for compliance is
# that the file is inside the distributed ZIP at all, not its exact
# subfolder.
_notices_path = REPO_ROOT / "THIRD_PARTY_NOTICES.txt"
if _notices_path.exists():
    datas.append((str(_notices_path), "."))

a = Analysis(
    [ENTRY_SCRIPT],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    icon=ICON_PATH,
    version=VERSION_FILE,
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
