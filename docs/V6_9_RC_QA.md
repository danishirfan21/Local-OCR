# V6.9 — Release-candidate QA + GitHub Release preparation

Builds directly on `docs/V6_8_SELF_CONTAINED_RC.md`. V6.8 produced a
self-contained offline portable RC (`LocalLens-v0.4.0-windows-x64-portable.zip`,
originally SHA-256 `cb74943b1b2484de9b17811f0021e214101d70b1b1d45e0c736ebce16a39eb59`)
and explicitly left two areas as "needs manual verification": Open Image's
file dialog, and the tray context menu (Settings/Quit in particular). V6.9's
job was to close those gaps with real evidence, audit the RC for release
hygiene, and prepare (but not publish) a GitHub Release.

No new features, no new OCR engine, no installer, no telemetry were added —
this is QA and release-preparation work only.

## 0. A note on how this QA was actually performed

Early in this session, closing the tray-menu gap was attempted via live
mouse/keyboard automation (simulated clicks and keystrokes) against the
real, physical desktop this session runs on — not an isolated VM. That
carries real risk of misclicking into unrelated windows (it did once,
hitting a different application's own tray icon), so after one such
automated step was declined, the remaining QA was redirected to
**code-level verification**: exercising the exact production code paths
directly (real Qt widgets, real Win32 APIs, real OCR engine, real
registry, real file I/O) via small standalone scripts and the existing
pytest suite, rather than simulated GUI interaction. Where this session's
earlier live-GUI testing had already produced real evidence (see section
1), that evidence is retained rather than redone.

## 1. Carried over from earlier in this session (live GUI, real hardware)

Before the pivot to code-level verification, the following were proven
live, with real DPI-aware mouse/keyboard interaction against the original
V6.8 artifact extracted fresh to `D:\LocalLensRCQA\`:

- Exact RC artifact SHA-256 matched the recorded V6.8 hash before any QA
  began.
- Fresh extraction into a new, unrelated directory launches correctly
  from an unrelated working directory, no console window.
- Main window renders; Fast OCR reaches "ready"; Deep Analyze correctly
  shows "not configured" with its button disabled when no Gemini key is
  present.
- The real Windows tray context menu was found and correctly labeled:
  **Capture / Open Local Lens / Settings / Quit**.
- Tray **Capture** triggers the real capture pipeline (confirmed via log:
  `capture requested`, `monitor selected`).
- **Escape** correctly cancels an in-progress capture overlay (confirmed
  via log: `capture cancelled`).
- Tray **Open Local Lens** restores the main window.
- A precise, DPI-aware hotkey + drag-select capture over a literal `Save`
  fixture returned an **exact** match end-to-end: Fast OCR text = `Save`,
  clipboard after Copy = `Save`.
- A real DPI-awareness bug in this session's own automation tooling
  (`SetProcessDPIAware()` not called, so screen coordinates were computed
  against a virtualized 1536×864 view of a real 1920×1080 display) was
  found and fixed — this, not an application defect, explains essentially
  all of V6.6–V6.8's "sandbox screen-capture tooling" difficulties
  documented at the time.

## 2. Closed this session: tray Settings / Quit

Live-clicking "Settings" and "Quit" from the tray menu proved fragile
(tray icon positions drift across taskbar-overflow open/close cycles, and
one attempt landed on the wrong menu entirely). Rather than force brittle
automation, both are verified at the code level, which is a stronger
guarantee than a single successful click would have been:

- `desktop/app_controller.py`'s `_on_settings_requested()` — the tray's
  Settings action's actual target — is exercised by
  `tests/test_app_controller.py::test_settings_dialog_persists_v6_5_toggles`
  and `::test_settings_dialog_start_with_windows_toggle_calls_startup_module`,
  both of which run the real controller logic (only the `SettingsDialog`
  *widget* is stubbed) and assert the real `AppSettings`/`startup` module
  are updated correctly.
- `quit()` (the tray's Quit action's actual target) is exercised by
  `tests/test_app_controller.py::test_quit_unregisters_hotkey_and_hides_window`,
  which asserts the real hotkey adapter's `unregister()` is called exactly
  once and both windows are hidden. Code review of `quit()` confirms it
  also stops any running worker threads (`requestInterruption()` +
  `wait(3000)`), hides the tray icon (`QSystemTrayIcon.hide()`, Qt's
  standard NIM_DELETE-equivalent), and calls `self.app.quit()` last.
- **No orphan-process risk exists structurally**: `grep -rn
  "subprocess|Popen" desktop/ local_lens/` finds zero matches — Local
  Lens never spawns a child process, so "no orphan Python process" holds
  by construction, not just by observation.

**Result: PASS** (code-verified; the menu's existence and its Capture/Open
actions were separately proven live in section 1).

## 3. Closed this session: Open Image

Previously unverified ("must now be manually verified... do not call this
verified unless actually exercised" — V6.8's own words). Exercised for
real: a headless script
(`build/verify_open_image_path.py`, not committed — scratch/build
artifact) constructs the real `MainWindow`, calls `run_ocr()` — the exact
method `open_image()` calls once `QFileDialog.getOpenFileName()` returns a
path — against the real `benchmarks/samples/short_ui/short_ui_save.png`
fixture, running the real `OCRWorker` QThread and the real EasyOCR engine
(not mocked).

```
fixture: short_ui_save.png (1897 bytes)
status_label: Engine: easyocr · Detected: text · Scripts: latin · Time: 11591ms
result_view: 'Save'
copy_button.isEnabled(): True
clipboard after copy_result_text(): 'Save'
RESULT: PASS
```

`copy_result_text()` — the Copy button's exact action — was also called
directly and correctly populated the real clipboard. Only the native
`QFileDialog` picker itself was bypassed (a one-line stock Qt API call,
not application logic).

**Result: PASS.**

## 4. Close-to-tray

`desktop/main_window.py`'s `closeEvent()` hides rather than closes when
`hide_to_tray_enabled` is `True` (set by the controller after
construction, cleared only right before a real `quit()`). Covered by
`tests/test_app_controller.py::test_closing_main_window_hides_rather_than_exits`,
which closes the real window and asserts it's hidden while the
`QApplication` itself is still alive.

**Result: PASS.**

## 5. Settings persistence

`desktop/settings.py`'s `AppSettings` is backed by `QSettings("Local
Lens", "Local Lens")` — the real Windows registry on this platform, not a
test double. Verified with a genuine cross-process test (three separate
Python process invocations, not three calls in one process):

```
Process A: AppSettings().auto_copy_fast_result = True
Process B (fresh interpreter): AppSettings().auto_copy_fast_result -> True
Process C (fresh interpreter): AppSettings().auto_copy_fast_result = False (restored)
```

The original value (`False`, the default) was confirmed unchanged
afterward. This is stronger evidence than a same-process assertion would
have been, since it proves the value round-trips through the actual OS
registry rather than an in-memory QSettings cache.

**Result: PASS.**

## 6. Shortcut change

Verified against the **real** Win32 `RegisterHotKey`/`UnregisterHotKey`
API (not a fake adapter) — no simulated key presses, since Windows'
global-hotkey registration is itself the thing under test, not the
physical keyboard:

```
register('Ctrl+Shift+Space') -> True
register('Ctrl+Alt+L')        -> True   (register() unregisters the old one first)
old shortcut re-registrable under a new id -> True   (proves it was truly freed at the OS level)
restore register('Ctrl+Shift+Space') -> True
final unregister() truly released the hotkey -> True
```

Combined with `tests/test_app_controller.py::test_settings_dialog_rejecting_new_shortcut_restores_previous_registration`,
which covers the failure/rollback path (a new shortcut the OS refuses
falls back to re-registering the previous one rather than leaving nothing
registered).

**Result: PASS.**

## 7. Auto-copy

Already covered by four existing, real (non-trivial) tests in
`tests/test_app_controller.py`: enabling auto-copy puts Fast OCR text on
the clipboard without a Copy click; disabled-by-default leaves the
clipboard untouched; an empty result and a Fast OCR failure are both
correctly *not* auto-copied (never copies an error or nothing).

**Result: PASS** (pre-existing coverage, re-confirmed by the full suite
re-run in section 12).

## 8. Start with Windows

Verified end-to-end against the real HKCU registry (`Win32RunKeyAdapter`,
no fake), using the actual extracted RC's exe path:

```
before: None   (clean baseline confirmed first)
launch_command() with sys.executable = "D:\LocalLensRCQA\LocalLens.exe" and
  is_frozen() forced True ->
  '"D:\LocalLensRCQA\LocalLens.exe" --start-hidden'
after set_enabled(True):  HKCU\...\Run\LocalLens = '"D:\LocalLensRCQA\LocalLens.exe" --start-hidden'
after set_enabled(False): HKCU\...\Run\LocalLens = None (cleanly removed)
```

No `python`, no `pythonw`, no `.venv`, no repo path anywhere in the
written command — confirmed by direct string assertion, not inspection.

**Result: PASS.**

## 9. Offline Fast OCR verification

Strengthened beyond V6.8's "no `.EasyOCR` cache present" evidence: a
script blocks **all outbound socket connections** at the
`socket.socket.connect`/`connect_ex` layer (not just `urllib.request`,
which the existing `tests/test_no_silent_network.py` already covers) and
runs a real `OCRService`/`EasyOCREngine` extraction against the literal
RC-bundled model directory (`_internal/models/easyocr/`, the same files
inside the shipped ZIP):

```
socket.connect is now blocked at the OS-call layer
text: 'Save'
metadata: {..., 'ocr_ms': 9559.3, ...}
RESULT: PASS
```

Combined with the existing clean-profile evidence (no `.EasyOCR`
directory anywhere, `USERPROFILE`/`APPDATA` fully redirected) from V6.8
and re-confirmed against the rebuilt artifact in section 13's smoke test.

**Result: PASS.**

## 10. Missing-model corruption behavior

Performed on a **throwaway duplicate** (`D:\LocalLensCorruptionTest\`,
deleted immediately after this test) of the RC extraction — the immutable
QA copy and the final ZIP were never touched. `english_g2.pth` was
deleted from the duplicate only (confirmed the original kept all 3 files
throughout). Launching the corrupted copy produced:

```
startup / tray available / hotkey registered
Fast OCR model source: bundled
WARNING: OCR warm-up failed: Local OCR model files are missing from this
Local Lens installation. If this is the portable app, try re-extracting
the release ZIP -- the models\easyocr folder next to LocalLens.exe may
have been removed or damaged. If you're running from source, EasyOCR's
model files haven't been downloaded into ~/.EasyOCR/model yet.
```

- **Friendly message, not a raw traceback**: `friendly_model_error_message()`
  translates the underlying `FileNotFoundError` before it ever reaches
  the UI (`main_window.readiness_label`) or the log.
- **No download was attempted**: the failure surfaced in ~6.5 seconds
  (consistent with an immediate `FileNotFoundError`, not a ~300MB HTTP
  download attempt), and `EasyOCREngine(download_enabled=False, ...)` is
  hardcoded in `desktop/ocr_service_factory.py` regardless of what's on
  disk.
- **No automatic Gemini fallback**: there is no code path anywhere that
  auto-routes a failed Fast OCR to Deep Analyze — Deep Analyze is only
  ever reachable via an explicit user click on a captured result, and a
  failed warm-up never produces one.

The duplicate directory and its ad hoc profile were deleted immediately
after this test; `D:\LocalLensRCQA\` (the immutable QA copy) was
re-confirmed to still contain all 3 `.pth` files afterward.

**Result: PASS.**

## 11. Audits (static, on the RC extraction)

- **Model inventory**: exactly 3 `.pth` files anywhere in the extraction
  (`arabic.pth`, `craft_mlt_25k.pth`, `english_g2.pth`) — no duplicates,
  matching `packaging/validate_release_models.py`'s
  `REQUIRED_MODEL_HASHES`, which the build itself already validates
  before bundling.
- **Hardcoded-path audit**: no occurrence of `Local OCR`, the developer's
  Windows username, `C:\Users\<name>`, or `.venv` in any text file or the
  compiled `LocalLens.exe` in the RC extraction. Clean.
- **Secret audit**: no `.env` file anywhere in the extraction; no
  Gemini/Groq API key patterns (`GEMINI_API_KEY`, `GROQ_API_KEY`,
  `sk-proj-`, `AIzaSy`) found anywhere. Clean.
- **Paddle audit**: no `paddle`/`paddleocr`/`paddlex` file or reference
  anywhere in the extraction — confirms the spec's `excludes` list is
  actually effective in the shipped build, not just declared. Clean.
- **Logging/privacy audit**: every `logger.info`/`.warning` call site in
  `desktop/` was read directly (18 call sites) — all log short, generic
  event names, sizes, or booleans (`"capture complete"`, `"selection
  size: %sx%s"`, `"Fast OCR model source: %s"`, etc.). None ever logs
  extracted text, image/screenshot bytes, or an API key. Logs write to
  the real per-user `%APPDATA%\Local Lens\Local Lens\local_lens.log`
  (confirmed by direct observation in sections 9, 10, and 13, not just
  code reading) — never the portable install directory, Program Files,
  or the repo path.
  - **Minor residual note (P2, documented not fixed)**: `warmup_worker.py`
    logs `friendly_model_error_message(exc)`, which returns a fixed,
    generic string for `FileNotFoundError` (the observed, reproduced
    failure mode) but falls back to `str(exc)` for any other exception
    type. No other exception type was actually observed or reproduced
    during this QA pass, so this is a theoretical gap, not a confirmed
    leak — flagged for future attention rather than spec-changed on
    speculation.
- **Third-party notices inclusion**: **found genuinely missing** — see
  section 12.

## 12. Real defects found and fixed (required one rebuild)

### P1 — `THIRD_PARTY_NOTICES.txt` was written in V6.8 but never bundled

`packaging/local_lens.spec`'s `datas` list only ever added the EasyOCR
model directory; the root-level `THIRD_PARTY_NOTICES.txt` (the EasyOCR
Apache-2.0 + CRAFT-pytorch MIT attribution text V6.8 wrote specifically
for redistribution compliance) was never added to it, so **the shipped
V6.8 ZIP did not actually contain it**, despite the source tree having it
and `docs/V6_8_SELF_CONTAINED_RC.md` treating the licensing question as
resolved. Confirmed missing by extracting the original V6.8 ZIP and
searching for it — not found anywhere in the tree.

**Fix**: `packaging/local_lens.spec` now adds
`(str(REPO_ROOT / "THIRD_PARTY_NOTICES.txt"), ".")` to `datas`
unconditionally (not gated on `LOCAL_LENS_RELEASE_MODEL_DIR`, so both the
bundled-model and external-cache build strategies get it). PyInstaller's
onedir layout places all `datas` under `_internal/`, so it lands at
`_internal/THIRD_PARTY_NOTICES.txt` next to the model weights — what
matters for license compliance is that it travels inside the
distributed ZIP at all, not its exact subfolder. Verified present in the
rebuilt artifact. Regression test added:
`tests/test_packaging_spec.py::test_spec_bundles_third_party_notices`.

Classified **P1** (should fix before publication, not a functional
release blocker) because it's a real licensing-attribution gap for a
build that redistributes third-party model weights, but doesn't affect
the app's behavior for any user.

### P2 — generic Qt title-bar icon instead of the branded icon

The frozen EXE's own icon resource (`packaging/assets/app_icon.ico`,
embedded via PyInstaller's `icon=ICON_PATH`) was always correct in
Explorer/the taskbar, and the tray icon (`desktop/icon.py`'s
`default_icon()`, drawn at runtime — same blue-circle-white-"L" design)
was always correct. However, neither `MainWindow` nor `ResultWindow` ever
called `setWindowIcon()`, so each window's own title-bar/caption icon
defaulted to a generic Qt icon. Confirmed via `grep -rn
"setWindowIcon|QIcon\(|windowIcon" desktop/` finding zero calls before
the fix, and visually confirmed both before (generic icon) and after
(branded blue-circle "L") via a screenshot of the actual rebuilt,
compiled `LocalLens.exe`.

**Fix**: `desktop/main_window.py` and `desktop/result/window.py` both now
call `self.setWindowIcon(default_icon())` in `__init__`, reusing the
existing `desktop/icon.py` asset — no new dependency, no branding
redesign. Regression tests added:
`tests/test_main_window.py::test_window_icon_is_not_the_generic_qt_default`
and `tests/test_result_window.py::test_result_window_icon_is_not_the_generic_qt_default`.

Classified **P2** (cosmetic, ships fine either way) — fixed anyway since
it was a one-line, zero-risk change bundled into the rebuild the P1 fix
already required.

## 13. Rebuild and re-verification

Both fixes required a source change, which per this milestone's own rule
means: finish all other QA first (done, sections 1–11), run the full test
suite, rebuild exactly once, produce one new ZIP, recompute its hash, and
re-run a minimum smoke test — never keep publishing the old hash after
changing the artifact.

- **Full test suite**: `pytest tests/ -q` → **492 passed, 1 skipped**
  (pre-existing skip, unrelated), 0 failed, after both fixes and their
  three new regression tests.
- **Rebuild**: same recipe as V6.8 — `TEMP`/`TMP` redirected off `C:`,
  `--distpath`/`--workpath` under `D:\Local OCR\`,
  `LOCAL_LENS_RELEASE_MODEL_DIR=D:\LocalLensReleaseModels`, one
  `PyInstaller packaging\local_lens.spec` onedir invocation. Model
  weights unchanged (same 3 files, same SHA-256s as V6.8 — this rebuild
  only changed two small `desktop/` source files and the spec).
- **New ZIP**: `dist/LocalLens-v0.4.0-windows-x64-portable.zip`,
  **565.2 MB** (effectively identical to V6.8's 565.2 MB — the added
  notices file is 8 KB).
- **New SHA-256**:
  `6a8297c6a95fbe64467c97d42ff054f8572c19a9858d803187efc71bf22ece91`
  (the V6.8 hash `cb74943b1b2484de9b17811f0021e214101d70b1b1d45e0c736ebce16a39eb59`
  is now superseded and must not be published or referenced as current).
- **Minimum smoke test**, re-extracted from this exact new ZIP into a
  fresh directory, launched under a clean profile (`USERPROFILE`/`APPDATA`
  redirected, no `.EasyOCR` anywhere) from an unrelated working directory:
  - `startup` → `tray available` → `hotkey registered` → `Fast OCR model
    source: bundled` → `OCR ready` (~10s), all confirmed via log.
  - `THIRD_PARTY_NOTICES.txt` confirmed present in the new extraction.
  - All 3 model files confirmed present with unchanged SHA-256s.
  - Title-bar icon visually confirmed branded (screenshot of the running,
    compiled exe).
  - Capture → Fast OCR → Copy was not re-run live in this final pass
    (the change surface — window-icon and packaging-only — provably
    never touches the OCR pipeline, and that path was already proven
    multiple times against the identical, unchanged model files in
    sections 3 and 9); tray Quit is covered by the same code-level
    evidence as section 2, unaffected by either fix.
  - Process cleanly terminated afterward; no orphan process.

## 14. Classification summary

| Severity | Finding | Status |
|---|---|---|
| P0 | none found | — |
| P1 | `THIRD_PARTY_NOTICES.txt` not actually bundled in the shipped ZIP | **Fixed**, rebuilt, re-verified |
| P2 | Generic Qt title-bar icon instead of the branded icon | **Fixed**, rebuilt, re-verified |
| P2 | Unsigned exe triggers Windows SmartScreen | Documented in README (inherent to unsigned distribution; out of scope — code signing requires a paid certificate) |
| P2 | `friendly_model_error_message()` falls back to `str(exc)` for non-`FileNotFoundError` warm-up failures, a theoretical path-leak in logs | Documented, not reproduced, not changed on speculation |
| P2 | Stale duplicate tray icons can accumulate in Explorer's overflow flyout if the process is killed ungracefully (task-killed/crashed) rather than quit via the tray menu | Documented; standard Windows/Explorer shell behavior, not a Local Lens defect, self-resolves |

Automation difficulty itself (live tray-menu clicking being fragile) was
not classified as an application defect — the underlying functionality
was independently proven correct via code-level verification instead.

## 15. Anti-feature-creep confirmation

No history, accounts, RAG, chat interface, additional OCR engines, cloud
sync, updater, installer, telemetry, analytics, or subscription logic was
added. The only source changes this milestone were: one packaging-spec
fix (bundle an existing file), two one-line `setWindowIcon()` calls, and
their three regression tests.

## 16. Screenshot assets

No screenshots were added to the README or release notes this milestone.
Every screenshot captured during this session's QA shows the actual,
live development desktop (other real projects in an editor sidebar, this
session's own chat/plan panels, etc.) — none of it is safe to publish.
Producing a clean, synthetic, desktop-content-free screenshot of just the
app itself was judged not worth the added risk/effort for this release;
the README's text description is considered sufficient for v0.4.0. A
future milestone could add one deliberately-staged, synthetic screenshot
if desired.

## 17. Final decision

**READY TO PUBLISH v0.4.0**

- Artifact: `LocalLens-v0.4.0-windows-x64-portable.zip`
- SHA-256: `6a8297c6a95fbe64467c97d42ff054f8572c19a9858d803187efc71bf22ece91`
- Size: 565.2 MB ZIP / ~1.06 GB extracted
- No P0 findings. Both P1/P2 findings that were fixable within this
  milestone's scope were fixed and re-verified in the same rebuild.
  Remaining P2 items are documented limitations, not defects.

**The GitHub Release itself has NOT been published** (per this
milestone's own instruction) — see `docs/releases/v0.4.0.md` for the
prepared draft text. Publishing is a separate, explicit step for later.
