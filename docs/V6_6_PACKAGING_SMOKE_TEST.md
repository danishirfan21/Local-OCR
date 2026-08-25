# V6.6 — bounded PyInstaller onedir portable-build smoke test

Goal: prove `clean packaged executable -> launch -> tray -> hotkey ->
capture -> Fast OCR -> result -> Copy` works **without Python installed
separately**, on this machine's permanent `C:`-space constraint, with
exactly one PyInstaller invocation. Not a polished release -- see
`docs/V6_5_RELEASE_READINESS.md` for the packaging research this
milestone executes on.

## Repository-state verification

Before packaging anything, HEAD (`54ad456` at the start of this
milestone) was verified from a real clean checkout, not the working
tree: `git archive HEAD | tar -x` into a scratch directory, then
importing `desktop.ocr_service_factory.warmup_fast_engine` and
`desktop.warmup_worker.WarmupWorker` directly from that extraction. This
specifically re-checks the V6.5-discovered class of bug (a function used
by one module but never actually committed) against the *current* HEAD,
not just re-trusting the earlier fix. Import succeeded cleanly.

Full suite: 440 passed, 1 skipped at the start of this milestone (before
this milestone's own additions), run via
`D:\Local OCR\.venv\Scripts\python.exe` -- the bare `python` on `PATH`
resolves to a different, non-project interpreter without PySide6
installed, so all commands in this document explicitly use the project
venv.

## PyInstaller: research, install, and disk impact

Not previously installed. Researched as lightweight before installing:
PyInstaller ships a small pure-Python wheel plus prebuilt Windows
bootloader binaries -- it does not compile anything itself, so it has no
compiler/MSVC/Windows-SDK requirement, unlike the packaging tools ruled
out in V6.5 (Nuitka).

Installed into `D:\Local OCR\.venv` only, with `pip install
--no-cache-dir` (pip's cache directory itself resolves to
`C:\Users\danis\AppData\Local\pip\cache`, so `--no-cache-dir` was used
specifically to keep the install from writing there):

```
pip install --no-cache-dir pyinstaller
```

Installed: `pyinstaller==6.22.2`, plus `altgraph`, `pefile`,
`pywin32-ctypes`, `pyinstaller-hooks-contrib` (all pure-Python/wheel,
no compiled extension requiring a local build step).

**Disk impact of the install**: C: free space unchanged (7.848GB before
and after, to three decimal places). D: free space dropped by 10.6MB.
Confirms the install landed entirely on `D:`.

## D:-only build configuration

Before installing or building, per-process (not global)
`$env:TEMP`/`$env:TMP` were set to `D:\DevTools\Temp`, and
`D:\Local OCR\build`, `D:\Local OCR\dist`, `D:\Local OCR\packaging` were
created explicitly. The actual build invocation passed `--distpath`/
`--workpath` explicitly rather than relying on the spec's defaults:

```powershell
$env:TEMP = "D:\DevTools\Temp"; $env:TMP = "D:\DevTools\Temp"
.venv\Scripts\python.exe -m PyInstaller packaging\local_lens.spec `
    --distpath "D:\Local OCR\dist" `
    --workpath "D:\Local OCR\build\pyinstaller" `
    --noconfirm
```

pip's cache directory (`C:\Users\danis\AppData\Local\pip\cache`) was
confirmed to be on `C:` before installing -- handled with
`--no-cache-dir` as noted above, rather than redirecting the cache
itself (simpler for a one-time install).

## Spec architecture (`packaging/local_lens.spec`)

- **Entry point**: `desktop/main.py` directly (not a new packaging-only
  entry file -- it already works both as `python -m desktop.main` for
  development and as a PyInstaller script target, since `desktop/` and
  every subpackage has an `__init__.py` PyInstaller's analyzer can
  resolve `from desktop.app_controller import ...` through). The
  Streamlit app (`app.py`) is never referenced.
- **Mode**: `onedir` (`COLLECT`, not a single-file `EXE`), `console=False`
  (windowed) from the start -- see "Console behavior" below for why a
  separate console-mode diagnostic build wasn't needed.
- **No icon file**: `desktop/icon.py` draws the tray/window icon at
  runtime (a generated circular "L"); there is no `.ico` asset for the
  spec to reference. An eventual `.exe`-icon `.ico` export is a future
  packaging-polish item, not a V6.6 requirement.
- **`datas=[]`**: no bundled data files. No `.env`, no model weights, no
  QSS/asset files exist in this project's desktop code (verified: only
  `.py` files exist under `desktop/` and `local_lens/` besides
  `__pycache__`).
- **`excludes=["paddle", "paddleocr", "paddlex"]`**: explicit intent
  documentation -- Paddle is not installed in this venv (confirmed
  throughout V4-V6), so PyInstaller could never have bundled it anyway,
  but the exclusion makes the intent explicit and machine-checkable (see
  `tests/test_packaging_spec.py`).
- **`hiddenimports=["easyocr", "cv2"]`**: added because PyInstaller's
  static import analysis doesn't always see `easyocr`'s own lazy/dynamic
  imports (it's imported lazily inside `_get_reader()`, not at module
  top level) -- confirmed necessary by the build's own warnings, not
  guessed. No other hidden imports were needed: PySide6, torch,
  torchvision, numpy, and PIL all resolved automatically through
  PyInstaller's built-in hooks (`hook-torch.py`, `hook-PySide6.*`, etc.,
  visible in the build log). Item 14's "do not dump the entire `.venv`
  into `hiddenimports`" -- only two entries were added, both justified.
- No credentials, real `.env`, or personal file-system paths are
  referenced anywhere in the spec (`tests/test_packaging_spec.py`
  enforces this statically).

## Windowed mode and logging (items 9-10, decided in advance)

Went straight to a windowed (`console=False`) build rather than doing a
console-mode diagnostic build first: `desktop/logging_setup.py` was
already hardened in V6.6's preparatory commit (before this build) to (a)
guard the console `StreamHandler` behind a `sys.stderr is not None`
check -- a `--windowed` build has `sys.stdout`/`sys.stderr` as `None`,
and the previous unconditional `StreamHandler()` would have crashed the
first time anything logged -- and (b) always attach a small rotating
file handler under Qt's `AppDataLocation`. This meant one windowed build
was sufficient and diagnosable, per item 9's own preference ("if one
windowed build can be diagnosed through file logging, prefer one
build").

## Model strategy for this smoke test (important, re-stated)

**External existing EasyOCR model cache**, not bundled weights --
deliberate, matching the task's explicit preference to avoid duplicating
~300MB into every test build while validating packaging *mechanics*.
`desktop/runtime_context.py`'s `easyocr_model_directory()` documents (but
is not yet wired into the OCR call path) the seam for a future bundled
resource; `local_lens/engines/easyocr_engine.py`'s
`download_enabled=False` (added in this milestone's prep commit, before
this build) is what actually protects against a silent download if the
external cache is ever missing on a given machine -- a missing model now
raises a caught, translated `"Local OCR model files are unavailable."`
message (`desktop/ocr_service_factory.py`'s `friendly_model_error_message`)
instead of either crashing or silently downloading. This was not
re-verified with the cache artificially removed in this milestone (the
real cache was left untouched, per the task's explicit "do not delete
the real EasyOCR model directory" instruction) -- the guard itself has
unit-test coverage (`tests/test_easyocr_download_guard.py`) using a fake
`easyocr` module, which is enough to prove the wiring without touching
real model files.

**No model weights were bundled, duplicated, or newly downloaded by this
milestone.** Confirmed post-build: `find dist/LocalLens -iname "*.pth"`
returns nothing.

## The one bounded build

Ran exactly once. No `--onefile` build was made, no exploratory rebuilds.

- **Duration**: 489.4 seconds (~8.2 minutes).
- **`build\pyinstaller` size**: 155.3 MB (intermediate analysis
  artifacts -- `PYZ`, `warn-*.txt`, `xref-*.html`, etc.).
- **`dist\LocalLens` size**: 862 MB.
- **Disk delta for the build itself**: D: free space dropped by
  ~1.0GB (862MB dist + 155MB build, consistent). **C: free space was
  unaffected** (7.846GB before, 7.851GB after -- a 5MB *increase*, pure
  OS-level noise, not a build side effect).

## Packaged executable launched independently (item 25)

```
dist\LocalLens\LocalLens.exe
```

launched directly via `Start-Process` (not `python ...`) -- proving
independence from the development interpreter. `Get-Process` confirmed:
process alive, `MainWindowTitle = "Local Lens"`, **no console window**
(the windowed build worked as intended), `Responding = True`.

## Startup smoke test (item 26)

The rotating log file (resolved via Qt's real `AppDataLocation`, this
session's sandboxed path:
`...\LocalCache\Roaming\Local Lens\Local Lens\local_lens.log`) recorded,
from the actual frozen process:

```
startup
tray available
hotkey registered
OCR ready          <- ~11.9s after startup (cold EasyOCR construction,
                       consistent with V6.4's measured 9.9-12.7s range)
```

A screenshot of the real desktop (`System.Drawing` screen capture, not a
mock) confirmed the main window rendered exactly as designed: shortcut
display, Capture Now / Open Image / Copy buttons (Copy correctly
disabled with nothing captured yet), "Fast OCR ready" readiness label,
"Deep Analyze: not configured (see Settings)" status, and the Open-Image
placeholder text -- all real V6.5 UI, rendering correctly from inside the
frozen executable.

## Hotkey + capture + Fast OCR + Copy smoke test (items 27-29)

`Ctrl+Shift+Space` was triggered via a real synthetic keyboard event
(`SendKeys`/`SendInput`, not a mocked call) with the cursor positioned
over the running app. A screenshot immediately after confirmed the
capture overlay activated (the screen visibly dimmed) -- proving the
real Win32 `RegisterHotKey` -> `WM_HOTKEY` -> `QAbstractNativeEventFilter`
chain works end-to-end in the frozen build, not just in `pytest`'s fake
adapter.

A real mouse drag-select (`mouse_event` down/move/up) over visible
on-screen text produced a result popup showing:

```
✓ Read locally · 0.3s
```

with the actual recognized text rendered in the Fast tab (correctly
classified as code content, given monospace styling), and the Deep
Analyze button correctly disabled (Gemini not configured). The 0.3s
figure is a real, measured warm-path timing from the frozen build,
matching V6.4/V6.5's ~0.3-0.6s dev-mode measurement -- confirming the
warm-up worker's effect carries over into the packaged build. The log
file's timestamps for this exact sequence (`capture requested` ->
`monitor selected` -> `selection size: 140x30` -> `capture complete` ->
`OCR completed`) independently corroborate the screenshot evidence.

**Deviation from the task's exact script**: the intended test used the
`short_ui_save.png` fixture (opened in an image viewer) so the captured
text would be the literal word "Save". This session's sandboxed
automation could not reliably call `SetForegroundWindow` to bring another
app in front of the running Local Lens window (a known Windows
restriction on synthetic foreground-window changes from a background
process) -- so the actual capture happened over the real, distinct
on-screen text at that moment, not the "Save" fixture specifically. The
captured/recognized text differed from "Save" as a direct consequence,
but the mechanism under test -- hotkey to overlay to region-select to Fast
OCR to popup -- is identical regardless of which real on-screen text was
selected, and is what this test actually verifies.

**Copy**: clicked via UI Automation's `InvokePattern` on the "Copy Code"
button (pixel-coordinate `SendInput` clicks were unreliable at hitting
this specific window in this sandboxed session -- the earlier hotkey
and drag-select *did* register via raw input injection, so input
delivery itself works; button hit-testing specifically did not, so UI
Automation's accessibility-tree-based invocation was used instead, which
is arguably a more robust test than a pixel click anyway). Clipboard was
seeded with a sentinel string beforehand and confirmed to contain the
exact popup text afterward -- a genuine, verified proof that Qt
clipboard access works correctly inside the frozen build.

## Open Image smoke test (item 30, partial)

Clicking "Open Image" opened Qt's native file dialog correctly -- titled
"Open Image", defaulting to the project directory, with the correct
`Images (*.png *.jpg *.jpeg *.webp *.bmp)` filter -- confirming Qt's
native Windows file-dialog integration works inside the frozen build.
Typing a specific file path into the dialog's filename field and
confirming the resulting OCR result was **not completed**: this
session's UI Automation had trouble targeting the Explorer-hosted common
dialog's filename `ComboBox` reliably (one attempt landed on an
unrelated file-list rename textbox instead, triggering a harmless
"invalid filename character" validation dialog, which was dismissed
safely with no file renamed). The dialog was closed cleanly via
`WM_CLOSE` afterward with no side effects.

**This is a gap in this session's live-automation coverage, not a known
app defect**: `MainWindow.open_image()` calls the exact same
`OCRWorker`/`build_fast_service()` code path already proven working by
the capture test above, and is covered by existing automated tests
(`tests/test_desktop_smoke.py`,
`test_completed_capture_shows_result_popup_and_runs_fast_ocr`-style
controller tests). Recommended as a specific follow-up if a future
milestone has better GUI-automation tooling available.

## Tray lifecycle smoke test (item 31, partial)

**Close-to-tray**: sent a real `WM_CLOSE` message to the main window's
native handle. Verified via `IsWindowVisible()`: the window became
invisible; via `Get-Process`: the process remained alive and
`Responding = True`; via the log file: no `shutdown` line was written
(only `quit()` logs that). This is exactly the intended close-to-tray
behavior, verified against a real Win32 window handle, not a Qt-internal
assertion.

**Open Local Lens / Settings / Quit via the tray icon's own context
menu**: not exercised live -- clicking a specific system-tray icon
requires locating its exact pixel position in the notification area's
overflow flyout, which is materially more fragile to automate reliably
than the app's own windows and was judged not worth the same
trial-and-error already spent on the file dialog. The process was
instead terminated directly (`Stop-Process`) to end the smoke test.
**No orphan processes**: confirmed via `Get-Process -Name LocalLens`
returning nothing afterward, and `Get-Process -Name python,pythonw`
showing only this environment's own unrelated Python processes (never
anything spawned by `LocalLens.exe`) -- consistent with the
single-process architecture (no Python sidecar to leak).

## Settings smoke test (item 32) and startup-registration packaged path (item 33)

Not exercised through live dialog interaction, for the same reason as
Open Image's file dialog (diminishing returns on this session's
available automation reach vs. risk of an unintended side effect).
Verified instead at the module level, against the **real packaged exe
path**:

```python
sys.frozen = True
sys.executable = r"D:\Local OCR\dist\LocalLens\LocalLens.exe"
desktop.startup.launch_command()
# -> '"D:\\Local OCR\\dist\\LocalLens\\LocalLens.exe" --start-hidden'
```

Confirms the frozen branch resolves to the packaged `.exe` path directly
-- never `python.exe`/`pythonw.exe`, never a repo path -- exactly item
20's requirement. `tests/test_startup.py::test_launch_command_frozen_mode_points_at_the_packaged_exe`
makes this a permanent regression test. The real registry was not
touched with this frozen value (V6.5 already live-verified the
underlying registry read/write/delete mechanics against the dev-mode
command; this milestone only needed to prove the frozen *command string*
resolves correctly, which does not require a real registry write).

## Gemini / Deep Analyze (item 34)

**No real Gemini call was made.** The running packaged app's own status
line read "Deep Analyze: not configured (see Settings)" and the result
popup's Deep Analyze button was visibly disabled -- both driven by the
real (unconfigured, in this session) environment, not a mock. This
confirms the production `production_gemini_configured(load_env())` path
resolves correctly inside a frozen build (path/env resolution differs
subtly for frozen vs. dev code, and this proves it isn't broken).

## Missing-model simulation (item 35) -- not performed live

Per the task's explicit instruction not to delete the real EasyOCR
model directory, and given the guard's logic is already fully unit-
tested against a fake `easyocr` module
(`tests/test_easyocr_download_guard.py`), no live simulation of a
missing model cache was attempted against the packaged exe. The guard
(`download_enabled=False` plus `friendly_model_error_message`) is
identical code whether frozen or not -- packaging doesn't change this
logic's behavior, so the existing unit coverage is the appropriate proof
here.

## Unexpected model-download guard (item 36)

Structurally guarded (see "Model strategy" above) and unit-tested.
**Not** re-verified against a live network-blocked run in this
milestone -- V6.4's existing `test_capture_and_fast_ocr_make_zero_network_calls_until_deep_clicked`
already proves Fast OCR makes no network call when models are present;
this milestone's `download_enabled=False` change specifically closes the
one remaining gap (models *absent*) with a fast, direct unit test rather
than a live-network-blocked packaged run.

## Dist footprint analysis (item 37)

Top contributors inside `dist\LocalLens\_internal`:

| Component | Size |
|---|---|
| torch | 310.0 MB |
| cv2 (OpenCV) | 137.9 MB |
| PySide6 | 91.6 MB |
| pyarrow | 74.6 MB |
| scipy | 57.4 MB |
| numpy (+ `.libs`) | 26.6 MB |
| scipy.libs | 19.3 MB |
| pandas | 16.1 MB |
| PIL | 12.8 MB |
| torchvision | 11.6 MB |

**Total measured `dist\LocalLens`: 862 MB** -- narrower than
V6.5's estimated 1.6-2.0GB range, because that estimate was based on the
*entire* `.venv` (which also holds Streamlit/benchmark-only packages);
PyInstaller's actual import-graph analysis pulled in a materially
smaller set.

**A real, actionable finding**: `pyarrow` (74.6MB), `scipy` (57.4MB +
19.3MB libs), and `pandas` (16.1MB) were pulled in even though
`desktop/main.py`'s own import graph never touches them directly -- they
arrived transitively (most likely via `scikit-image`, an EasyOCR
dependency, and/or a PyInstaller hook that aggressively includes an
optional integration once a package is merely importable). Together
these are **~167MB (~19% of the build) that a future milestone could
likely trim** with a more surgical `excludes=` list, once verified the
app still runs correctly without them. Not addressed in this milestone
per item 23's "avoid change one import -> rebuild 2GB -> repeat" --
documented here as a concrete, evidence-based V6.7+ candidate rather
than guessed at.

## Paddle-in-dist check (item 38)

```
find dist/LocalLens -iname "*paddle*"   -> no results
```

The build log's own warnings file additionally shows PyInstaller
*recognized and explicitly excluded* Paddle rather than silently
skipping it:

```
excluded module named paddle - imported by einops._backends (delayed), einops.layers.paddle (top-level)
excluded module named paddleocr - imported by local_lens.engines.paddleocr_engine (optional), ...
```

Paddle did not return through packaging archaeology.

## Dev-junk check (item 39)

No `local_lens`/`desktop` test files, no `benchmarks/` corpus, no
`.git`, no `.env`, and no project documentation were bundled. A search
for `test_*`/`*.git*` inside `dist/` only turned up files that ship
*inside* the `torch` and `pyarrow` third-party wheels themselves (their
own internal test-utility headers/modules, e.g.
`pyarrow/include/arrow/csv/test_common.h`) -- normal, expected package
contents, not anything from this project.

## Secret audit (item 40)

- No `.env` file anywhere under `dist/` or `build/`.
- Targeted search for `LOCAL_LENS_GEMINI_API_KEY=<value>` and Google API
  key-shaped strings (`AIza...`) across `dist/`: no matches.
- The key *name* `LOCAL_LENS_GEMINI_API_KEY` does not even appear in any
  PyInstaller build-metadata text file (`warn-*.txt`, the analysis
  `.html` cross-reference).
- The repository's own real `.env` (used for this developer's local
  Deep Analyze testing) was independently confirmed to exist at the repo
  root but was never referenced by the spec, never included in `datas=`,
  and was not copied into `dist/` -- confirmed by direct filesystem
  search, not just by absence of a `datas` entry.

## Portable ZIP (item 41, optional -- created)

D: had ample free space (>640GB) and TEMP/TMP stayed redirected, so one
ZIP was created:

```
dist\LocalLens-portable-v6.6-smoketest.zip
```

- **Size**: 322.2 MB (compressed from 862MB, ~37% of the unpacked size).
- **Duration**: 67.3 seconds.

This is a smoke-test artifact demonstrating the onedir -> ZIP path works
mechanically, not a release candidate -- see "Known limitations" below.

## No installer built (item 42)

No MSI/NSIS/Inno Setup/WiX/`setup.exe` wrapper was created or
attempted, matching V6.6's explicit scope.

## SmartScreen / Defender (item 43)

**Not observed/triggered in this smoke test.** The executable was
launched directly via `Start-Process` from an already-trusted local
PowerShell session, which does not carry the "mark of the web" zone
identifier that triggers SmartScreen's "Windows protected your PC"
prompt -- that check specifically applies to files that arrived via a
browser download or another zone-tagged transfer (e.g. email, network
share from an untrusted zone). A locally-built executable launched from
where it was built does not exercise this path. This is expected and
consistent with V6.5's documented expectation that an *unsigned,
downloaded* copy will trigger SmartScreen on first run for an actual
end user -- this smoke test simply didn't reproduce that specific
distribution-time condition, and no certificate was purchased or is
planned (unchanged from V6.5).

## PyInstaller warnings review (item 45)

`build\pyinstaller\local_lens\warn-local_lens.txt`: 781 lines, of which
761 are `missing module named ...` entries -- PyInstaller's standard
noise for large scientific-Python dependency trees (torch, scipy) noting
optional/conditional/platform-specific imports it couldn't statically
resolve, explicitly documented by PyInstaller itself as not necessarily
meaning anything is broken. Spot-checked: these are all either
conditional imports for platforms this build doesn't target (e.g. Linux-
only paths in `torch.distributed`) or genuinely optional integrations
(e.g. `scipy.sparse.SparseEfficiencyWarning`, an optional warning class).
None were classified as a real missing-module problem -- the live smoke
test actually running Fast OCR successfully (real EasyOCR inference, not
mocked) is stronger evidence than the warnings list alone. Not every
warning was individually fixed, per item 45's own instruction.

## Disk-safety final check (item 52)

| | Before this milestone | After this milestone | Delta |
|---|---|---|---|
| C: free | 7.848 GB | 7.837 GB | -11 MB (OS-level noise, not build-related) |
| D: free | 644.975 GB | 643.640 GB | -1.335 GB (pyinstaller install 10.6MB + build/dist ~1.0GB + zip 322MB) |

**C: stayed effectively stable throughout this entire milestone** --
PyInstaller install, the one build, and the portable ZIP all landed on
`D:` as designed. No compensating cleanup of `C:` was ever needed or
performed.

## Final decision (item 53)

**PORTABLE BUILD VIABLE.**

The packaged executable independently launches, registers a real global
hotkey, captures the screen, runs real (non-mocked) Fast OCR via the
external EasyOCR model cache, displays a working result popup, and
copies to the real Windows clipboard -- all without Python installed
separately and with zero `C:` impact. The two gaps in this milestone's
live verification (Open Image's file-path entry, tray-context-menu
Settings/Quit) are automation-session limitations specific to this
sandboxed test environment, not evidence of an app defect -- both paths
run byte-identical Python code to what's already covered by 463 passing
automated tests, and packaging introduces no code branching for either
of them.

## Known limitations

- `pyarrow`/`scipy`/`pandas` (~167MB combined) are bundled despite not
  being imported by the desktop app directly -- a concrete size-reduction
  candidate for V6.7+, not chased down this milestone (see "Dist
  footprint analysis").
- Open Image's file-selection flow and the tray context menu's
  Open/Settings/Quit actions were not exercised through live GUI
  automation this milestone (see the relevant sections above for why and
  what already covers them).
- No icon (`.ico`) has been created for the `.exe` itself yet -- the
  taskbar/Explorer icon for `LocalLens.exe` is currently whatever
  PyInstaller's own default is, since `desktop/icon.py`'s generated icon
  only applies to the in-app tray/window icon, not the file icon.
- The portable ZIP (322MB) was produced as a smoke-test artifact, not a
  vetted release: it wasn't extracted-and-relaunched from a second
  location to confirm the extracted copy behaves identically (a
  reasonable V6.7 check before treating it as a real release candidate).
- SmartScreen/Defender behavior for a genuinely downloaded/zone-tagged
  copy remains unverified (see above) -- expected to trigger per V6.5's
  documented reasoning, but not reproduced here.

## Cleanup (item 49)

`dist\LocalLens\` (862MB) and the portable ZIP were kept, not deleted.
`build\pyinstaller\` (155.3MB of intermediate analysis artifacts) was
also kept for this report's own evidence trail (the warnings file and
cross-reference HTML live there) -- explicitly not deleted, since nothing
about this milestone requires reclaiming that space and D: has ample
room. Both directories are gitignored (`dist/` and `build/` were already
in `.gitignore` before this milestone).

## Git handling (item 50)

Committed: `packaging/local_lens.spec`, the new tests, this document,
and the source fixes made in preparation (frozen-path helper, windowed-
safe logging, no-silent-download guard -- see the "V6.6 prep" commit).
**Not committed**: `dist/`, `build/`, the portable ZIP, or any packaged
binary -- all already excluded by the existing `.gitignore`.
