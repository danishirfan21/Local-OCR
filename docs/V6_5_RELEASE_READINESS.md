# V6.5 — Settings polish + release-readiness + safe packaging research

Scope: make the desktop app feel like a complete first-release product
(Settings depth, startup behavior, auto-copy) and determine the safest
Windows distribution strategy -- without building a heavyweight installer
or running a packaging build. `docs/V6_4_RESULT_UX.md` covers the capture
-> result-popup -> Deep Analyze workflow this milestone builds on top of.

## Repository-state fix found during verification

Before starting V6.5 work, verifying the V6.4 HEAD (`d075c5d`) turned up a
real bug: `desktop/warmup_worker.py` imports `warmup_fast_engine` from
`desktop/ocr_service_factory.py`, but that function existed only in the
working tree -- it was never actually `git add`ed in any of the four V6.4
commits. A clean checkout of `d075c5d` would fail with an `ImportError` the
moment the warm-up worker's thread started. Fixed as the first commit of
this milestone (`desktop/ocr_service_factory.py`, `warmup_fast_engine`).

## Settings architecture

`desktop/settings.py`'s `AppSettings` remains the single QSettings-backed
store for **UI preferences only** -- it must never hold
`LOCAL_LENS_GEMINI_API_KEY` or any other secret; that boundary is
unchanged from V6.2. Four new preferences were added, all with safe
defaults so an existing user's `.ini`/registry state upgrades cleanly:

| Key | Default | Meaning |
|---|---|---|
| `start_with_windows` | `False` | HKCU Run key registration is active |
| `auto_copy_fast_result` | `False` | Copy Fast text to clipboard automatically |
| `show_result_popup` | `True` | Show the result popup after a capture |
| `close_popup_after_copy` | `False` | Hide the popup after any Copy click |

`QSettings` round-trips booleans as native `bool` on the real Windows
registry backing but as the strings `"true"`/`"false"` on the INI backing
tests use -- `AppSettings._bool()` normalizes both so callers never see
the difference.

The Settings dialog (`desktop/settings_dialog.py`) is grouped into
**General** (shortcut + Restore Default + Start with Windows + Auto-copy),
**Behavior** (show popup + close-after-copy, the latter disabled and
cleared whenever the popup itself is off), and **Deep Analyze** (Gemini
status + privacy text + API-key setup guidance). Deliberately excluded,
per this milestone's explicit scope: an OCR-engine dropdown, benchmark
settings, a provider zoo, model tuning, history controls, and
account/subscription controls -- `tests/test_settings_dialog.py` has a
guard test asserting none of those widgets exist.

Shortcut conflict/validation feedback is unchanged from V6.2: the dialog
validates the key combination locally (modifier required, supported key,
no multi-key chords) and shows the reason inline; an actual registration
conflict with another application is only discoverable at
`RegisterHotKey()` time, so that failure surfaces as the existing
main-window warning banner after the dialog closes, with the previously
working shortcut automatically restored (`app_controller.py`'s
`_on_settings_requested`, unchanged logic from V6.2/V6.4).

## Startup: "Start Local Lens with Windows"

Implemented in `desktop/startup.py` as a **user-level HKCU Run key entry**
(`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, value name
`LocalLens`) -- never HKLM, never requires Administrator. This was chosen
over a Startup-folder shortcut because it needs no `.lnk` file management
and is the mechanism Windows itself documents for this exact use case;
both were evaluated and either would have satisfied the "user-level,
no Administrator" constraint.

Platform access is isolated behind a small `RegistryAdapter` protocol
(mirroring the existing hotkey adapter pattern in
`desktop/hotkey/win32_adapter.py`) so `tests/test_startup.py` exercises
the real enable/disable/is-enabled policy against a fake in-memory
adapter -- no test ever touches the real user registry.

**Launch command** (`launch_command()`): resolves differently for a
future packaged build vs. today's development checkout, per items 32/33:

- Frozen (`sys.frozen`, a future PyInstaller build): `"<exe path>" --start-hidden`.
- Development: `cmd /c cd /d "<repo root>" && "<pythonw.exe>" -m desktop.main --start-hidden`
  -- `pythonw.exe` (not `python.exe`) is used when a sibling exists in the
  same directory as `sys.executable`, so no console window flashes at
  login (item 5); `cmd /c cd /d` sets the working directory, since a
  Run-key value has no separate "start in" field and `python -m
  desktop.main` needs the repo root on the import path.

**Disable never touches other startup entries** -- `set_enabled(False)`
only ever deletes the `LocalLens` value, using `winreg.DeleteValue`
guarded by `except FileNotFoundError: pass` so disabling an
already-disabled state is a harmless no-op.

**Live verification performed** (item 35, reverted immediately after):

```
before:        None
launch_command(): cmd /c cd /d "D:\Local OCR" && "D:\Local OCR\.venv\Scripts\pythonw.exe" -m desktop.main --start-hidden
after enable:   cmd /c cd /d "D:\Local OCR" && "D:\Local OCR\.venv\Scripts\pythonw.exe" -m desktop.main --start-hidden
is_enabled():   True
after disable:  None
is_enabled():   False
```

Independently confirmed clean afterward with `reg query
"HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v LocalLens`, which
correctly reported the value not found. No reboot was performed or needed
-- registration was verified via direct registry read, not by triggering
an actual login.

## Start-minimized / `--start-hidden`

`desktop/main.py` checks for the literal flag `--start-hidden` in
`sys.argv` and passes `start_hidden=True` into `DesktopApplication`, which
skips the `main_window.show()` call at the end of `__init__` -- the tray
icon still appears and the global hotkey still registers normally, so the
app is fully functional, just not visually intrusive at login. Manual
launches (no flag) behave exactly as before: the main window shows.

One consistent flag name is used everywhere it appears: the startup
command (`desktop/startup.py`), `main.py`'s parsing, and the constructor
parameter are all named `start_hidden`/`--start-hidden` -- no second name
(`--background`) was introduced alongside it.

## Auto-copy

`desktop/app_controller.py`'s `_on_fast_ocr_succeeded` checks
`settings.auto_copy_fast_result` and `result.text` (truthy check, so an
empty string never copies) before writing to the clipboard -- an OCR
*failure* never reaches this method at all (`_on_fast_ocr_failed` is a
separate signal handler), so errors are structurally excluded, not
special-cased. Deep results are never auto-copied; that remains a
separate, undesigned future decision per this milestone's own scope note.
Default is `False`. The result popup stays visible after an auto-copy
unless `close_popup_after_copy` is also enabled.

## Close-after-copy

`ContentPane` now emits a `copied` signal from every copy action (Copy,
Copy Code, Copy Table, Copy Markdown); `ResultWindow` re-emits it as a
single `text_copied` signal wired from both the Fast and Deep tabs. The
app controller hides the popup on `text_copied` only when
`close_popup_after_copy` is enabled -- default `False`, exactly as the
task specified ("do not enable by default"). This turned out simple
enough to implement in full rather than defer.

## Main window ("home" surface)

`MainWindow` now carries a **Capture Now** button (emits the same
`capture_requested` signal the hotkey and tray route through --
`app_controller._start_capture`), a shortcut display line, a readiness
label ("Starting local OCR…" -> "Fast OCR ready", updated from the
existing background warm-up worker's `finished_warmup` signal -- no
EasyOCR-specific text anywhere), and a Deep Analyze configured/not
line. It still doubles as the Open-Image result view from V6.1; the
flagship capture -> result path renders in the separate `ResultWindow`
(V6.4), unchanged.

## Deep key storage decision

**Decision: `ENV ONLY FOR V6`** (item 36). `LOCAL_LENS_GEMINI_API_KEY`
via `.env` (development) or a real environment variable remains the only
supported credential path this milestone; the Settings dialog shows
Gemini configured/not-configured plus guidance text, with no key-entry
field.

Rationale, weighed against the alternative (Windows Credential Manager,
via a `keyring` dependency or the raw Win32 Credential API):

- **No packaged build exists yet.** This milestone explicitly does not
  execute a packaging build (item 27); a secure-storage UI's main value
  -- letting a packaged end user avoid hand-editing `.env` -- has no
  audience until V6.6+ actually ships a build.
- **New dependency risk right before packaging research.** `keyring`'s
  Windows backend pulls in `pywin32`, which itself has had packaging
  friction with PyInstaller historically; adding it the same milestone
  that's evaluating packaging tools conflates two research questions.
- **Direct `winreg`-based custom Credential Manager access** (skipping
  `keyring`) is possible but nontrivial to get right securely (DPAPI
  encryption semantics) -- not something to improvise under this
  milestone's "straightforward and lightweight only" bar (item 10).

This is deferred, not abandoned: the natural point to add it is once
V6.6+ produces a real packaged build and packaged users actually exist.
`.env` support is unmodified and remains fully valid for development, per
item 11.

## Privacy copy

Unchanged in substance from V6.4, restated per item 13's exact wording in
the Settings dialog: "Fast OCR runs entirely on this device." /
"Deep Analyze sends the selected image to Google's Gemini API." The
free-tier data-use caveat from V6.4's privacy *dialog* (shown once per
session before the first Deep Analyze call) is intentionally not
duplicated in Settings -- Settings shows the two-line summary only, so
the full caveat isn't lost but also isn't repeated in two places.

## Icon and branding

`desktop/icon.py`'s runtime-generated circular "L" placeholder (added in
V6.2) already serves as both the tray icon and the window icon, and
requires no asset file or download. It remains adequate for a first
release; item 18 explicitly rules out spending this milestone on
elaborate branding, and no icon-pack download or custom asset was
introduced. A `.ico` export of this same generated icon for the
eventual `.exe` icon is a packaging-time detail (V6.6+), not a V6.5 one.

## Packaging research

No build was executed this milestone (item 27's default is research +
plan). Options compared for
`PySide6 + EasyOCR + torch + Local Lens`:

| Option | Requires a local C/C++ compiler? | Verdict |
|---|---|---|
| **PyInstaller** | No -- collects already-compiled wheels and ships prebuilt Windows bootloaders; it does not compile anything itself | **Practical candidate** |
| **Nuitka** | Yes -- compiles Python to C, then compiles that C to native code via MSVC or MinGW | **Unsuitable** given the permanent C:/no-MSVC constraint (item 20) |
| **Portable Python distribution** (embeddable Python + manually assembled `site-packages`) | No | Viable but strictly more manual than PyInstaller for the same result -- no advantage found |

**Recommendation: PyInstaller, `onedir` (not `onefile`)**, per items
21-22. `onefile` unpacks its entire payload to a temp directory on every
launch -- for a ~1.5-2GB payload (see below) that means real per-launch
latency and heavy temp-disk churn, plus a materially higher chance of
tripping Windows Defender/SmartScreen heuristics that specifically
target self-extracting single-file executables. `onedir` ships a folder
of files that stay in place between launches; it starts faster and
extracts nothing at runtime.

**Build safety** (item 26): any future PyInstaller invocation must run
with `PYINSTALLER build/dist paths under D:\Local OCR\build` and
`D:\Local OCR\dist`, and both `$env:TEMP`/`$env:TMP` set per-process
(never globally) to a `D:`-based path (e.g. `D:\DevTools\Temp`) before
invoking it, so PyInstaller's own scratch space never touches `C:`.

## Compiler check (item 20/21, restated for clarity)

- PyInstaller: **no compiler required.** Its Windows bootloader ships
  prebuilt in the `pyinstaller` wheel; packaging a project that already
  has working wheels (as this venv does -- `pip show paddlepaddle
  paddleocr paddlex` confirms Paddle was never reinstalled, and every
  desktop dependency is already an installed wheel with no local
  compilation step) requires no MSVC, no MinGW, no Windows SDK.
- Nuitka: **requires a compiler**, ruled unsuitable for local use on this
  machine per the permanent constraint.

## Estimated release size

Measured directly on this machine's `D:\Local OCR\.venv\Lib\site-packages`
(not guessed):

| Component | Size |
|---|---|
| PySide6 | 632.3 MB |
| torch | 432.5 MB |
| cv2 (OpenCV, an EasyOCR dependency) | 148.1 MB |
| numpy (+ `.libs`) | 51.7 MB |
| torchvision | 14.6 MB |
| networkx (a torch dependency) | 14.8 MB |
| Pillow | 15.3 MB |
| easyocr | 15.4 MB |
| **Core desktop-app subtotal** | **~1.32 GB** |
| EasyOCR model weights (`%USERPROFILE%\.EasyOCR`: `craft_mlt_25k.pth` 79.3MB + `english_g2.pth` 14.4MB + `arabic.pth` 205.4MB) | 299.2 MB |
| **Realistic onedir release estimate** | **~1.6-2.0 GB unpacked** |

(The full `.venv` measures ~2.0 GB, but that total also includes
Streamlit-only and benchmark-only dependencies -- `streamlit`,
`pandas`, `pyarrow`, `pydeck`, `modelscope`, `sklearn`/`scipy`/`sympy` --
none of which the desktop app imports; a PyInstaller build driven from
`desktop/main.py`'s actual import graph would exclude those.)

This is **not** a small tray-utility footprint -- torch alone is
~430MB regardless of how compact the UI looks, and that is the accurate
number to plan around, not an aspirational one.

## Model inclusion strategy

Not decided/built this milestone (item 23 explicitly says don't move
models yet) -- documented as a tradeoff for V6.6+:

- **Bundle the 299MB of model weights into the onedir build.** Preserves
  the fully-offline-first UX Local Lens is built around: no network
  access is needed for Fast OCR to work immediately after
  install/extract, consistent with the existing "Fast OCR never makes a
  network call" guarantee already tested (`test_no_silent_network.py`,
  `test_capture_and_fast_ocr_make_zero_network_calls_until_deep_clicked`).
  Costs ~300MB of extra distribution size.
- **First-run download** (EasyOCR's own default behavior when models
  aren't present) trims installer size but requires a network connection
  on first use and reintroduces exactly the kind of "quietly phones
  home" behavior this project has been careful to avoid and test against
  for Fast mode specifically.
- **External/optional model directory** adds real complexity (a
  models-path setting, validation, error states) for a benefit -- smaller
  download -- that matters less once portable-ZIP is the distribution
  format (item 29) rather than a size-sensitive installer.

**Leaning: bundle.** Final call deferred to whichever milestone actually
produces a build, so it can be validated against a real onedir output
rather than decided in the abstract here.

## Portable ZIP vs. installer

**Recommendation: portable ZIP** for the first release (item 29).
Rationale: no installer framework to build/maintain, no elevation
prompts, trivially easy to test (extract and run), and appropriate for a
portfolio/early-testing release. The two things a real installer buys --
Start Menu presence and a guided uninstall -- are exactly the two things
V6.5's "Start Local Lens with Windows" already covers a meaningful part
of the value of (an uninstall for a portable-ZIP app just means deleting
the folder, which also removes the Run-key entry if the user unchecks
"Start with Windows" first, or the entry becomes a harmless dangling
Run-key value pointing at a deleted path if they don't -- worth noting as
a known rough edge of the portable-ZIP path, not a blocker).

## Windows SmartScreen reality

An unsigned `.exe` (this project's realistic first-release state, since
no code-signing certificate purchase is in scope) will very likely
trigger a SmartScreen "Windows protected your PC" prompt on first launch,
and may be flagged more aggressively by some antivirus heuristics simply
for being an unfamiliar unsigned binary that bundles a large ML runtime
(torch). This is expected, documented behavior for unsigned Windows
software generally, not something specific to how Local Lens is built --
users click "More info" -> "Run anyway" the first time, and it does not
recur for that binary on that machine. No certificate was purchased and
none is planned in this scope.

## Release settings storage

`AppSettings` is backed by `QSettings(ORGANIZATION_NAME,
APPLICATION_NAME)` (`"Local Lens"` / `"Local Lens"`), which resolves to
`HKEY_CURRENT_USER\Software\Local Lens\Local Lens` on Windows --
independent of the app's install location. Shortcut, startup preference,
and auto-copy all live there and will survive both a packaged app update
(replacing the `.exe`/onedir folder in place) and a portable-ZIP
re-extraction to the same or a different folder, since none of them are
tied to a repo path. Startup registration itself resolves the correct
launch path at *set-enabled* time (`launch_command()`), not at
settings-read time, so it does not need special handling here.

## Development-vs-packaged detection

`getattr(sys, "frozen", False)` (the standard PyInstaller convention) is
used in exactly one place -- `desktop/startup.py`'s `launch_command()` --
to decide whether to write a `.exe` path or a `python -m desktop.main`
command. No other module branches on frozen/dev state; packaging
awareness does not spread into `app_controller.py`, the result window, or
anywhere else in the desktop app (item 33).

## Resource safety tests (item 34)

`tests/test_startup.py` covers enable/disable/is-enabled against a fake
`RegistryAdapter`, that disabling never removes anything but Local Lens's
own value, that disabling an already-disabled state doesn't raise, and
that `launch_command()` builds without touching the registry at all. No
test constructs a real `Win32RunKeyAdapter`. `tests/test_desktop_settings.py`
and `tests/test_settings_dialog.py` cover the four new preferences and
their dialog round-trip using the existing temp-file-`QSettings` /
offscreen-Qt patterns already established in V6.2-V6.4.

## C:/D: build-safety note (forward-looking, no build executed)

Documented for whichever milestone runs the first real PyInstaller
invocation: set `$env:TEMP`/`$env:TMP` to a `D:`-based path *for that one
process only* (not globally, per item 26), and pass `--workpath` /
`--distpath` pointing at `D:\Local OCR\build` / `D:\Local OCR\dist`
explicitly rather than relying on PyInstaller's defaults.
