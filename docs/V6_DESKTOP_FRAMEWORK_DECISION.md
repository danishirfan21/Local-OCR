# V6 desktop framework decision: PySide6 replaces Tauri

`docs/V6_DESKTOP_ARCHITECTURE.md` is **superseded** by this document. It is
kept for decision history, not as the active plan. The trigger: this
machine's `C:` drive has a hard, non-negotiable capacity constraint that
makes local MSVC Build Tools + Windows SDK installation unsafe (see that
document's own toolchain-footprint research), and that constraint is now
treated as permanent, not a temporary disk-cleanup problem to solve. Tauri
2 on Windows cannot compile without a local MSVC linker — no amount of
`--installPath` redirection changes that; the Windows SDK and VS Installer
shared components are hard-coded by Microsoft to land on `C:` regardless.

## Decision: PySide6 (Qt 6), single Python process

```
PySide6 desktop UI (Python)
        |
        | direct function calls, no IPC boundary
        v
OCRService / EasyOCR / GeminiDeepProvider  (unchanged, existing code)
```

No Rust. No MSVC. No Windows SDK. No sidecar process. No JSON-lines IPC
protocol to design, version, and keep in sync across two languages. The UI
and the OCR core run in the same Python process, in the same `.venv` this
project already has on `D:`.

## Decision matrix

| Criterion | Tauri + Python sidecar | PySide6 |
|---|---|---|
| Local compiler requirement | Rust + MSVC + Windows SDK (blocked on this machine) | None — pure Python wheels |
| C: dependency | Windows SDK + VS Installer shared components hard-coded to C:, ~2-4GB unavoidable | None beyond ordinary pip package files, which install into the D:-based `.venv` |
| Reuse Python core | Yes, via IPC (sidecar imports `local_lens` unchanged) | Yes, direct import, same process |
| IPC complexity | A versioned JSON-lines protocol to design, implement on both sides, and keep in sync | None — no IPC boundary exists |
| Screenshot overlay | Would need a Rust capture crate (`windows-capture`) + a Tauri overlay window | `QScreen.grabWindow()` + a frameless translucent `QWidget` overlay, both in Qt's own API surface |
| Global hotkey | `@tauri-apps/plugin-global-shortcut` (official, well-supported) | No first-class Qt API; implemented via `ctypes` + Win32 `RegisterHotKey` + `QAbstractNativeEventFilter` — small, dependency-free, Windows-native |
| Tray | Official Tauri tray API | `QSystemTrayIcon`, first-class, well-documented, works on all supported Windows versions |
| RTL/Urdu | Would need React text-direction handling from scratch | Qt has built-in bidi/RTL text layout (`Qt::LayoutDirection`, `QTextOption`) — mature and already used by many Qt apps for Arabic-script text |
| UI polish | React + CSS, more customization ceiling long-term | Qt Style Sheets (QSS) — less flexible than CSS but entirely sufficient for a compact utility window, restrained modern styling achievable |
| Installer size | Small Rust binary + WebView2 (already on Windows) + bundled Python sidecar (the actual large part either way) | Bundled Python + PySide6 (~150-250MB for Qt itself) + EasyOCR/PyTorch (the large part either way) |
| Packaging complexity | Two toolchains to freeze (Rust binary + Python sidecar via PyInstaller/Nuitka) | One toolchain (PyInstaller/Nuitka on the single Python app) |
| Startup | Sidecar spawn + IPC handshake before first use | Direct import, no subprocess handshake |
| Memory | Two processes (Tauri/WebView2 + Python sidecar) | One process |
| Development speed | Blocked entirely on this machine right now | Can start immediately |
| Cross-platform potential | Strong (Tauri's actual design goal) | Fine — Qt is genuinely cross-platform too, just not this project's current scope |

Tauri is not a bad framework — the matrix reflects this machine's specific,
current constraint (no local MSVC), not a claim that Tauri is worse in
general. The product goal is "ship a fast Windows screenshot utility
without exhausting this laptop," and on this machine, right now, PySide6 is
categorically the lower-risk path: it removes an entire compiler toolchain
and an IPC boundary that were only there to serve a UI framework choice,
not a product requirement.

## Remote-build Tauri: evaluated and rejected for now

Building Windows Tauri artifacts on `windows-latest` GitHub Actions runners
(or a separate Windows VM with MSVC) is technically possible and was
seriously considered. Rejected for V6 because the core problem it doesn't
solve is **daily local development** — every UI tweak, every capture-overlay
bug, every DPI edge case would need a push-and-wait CI round-trip to see
running on Windows at all, since there's no way to `cargo run`/`tauri dev`
locally without the same missing MSVC linker. That's not a packaging
inconvenience, it's a fundamentally worse development loop for a UI-heavy,
iteration-heavy phase of work. PySide6 runs and hot-reloads locally, today,
with zero additional toolchain installation risk. Remote-build Tauri stays
a theoretical fallback if PySide6 turns out to have a real blocker (none
were found in this evaluation), not something to build against now.

## Feasibility findings (PySide6 covers the full requirement list)

- **Frameless/compact result panel, always-on-top**: `Qt.FramelessWindowHint`
  / `Qt.WindowStaysOnTopHint` window flags — standard, well-documented Qt
  window flags.
- **System tray**: `QSystemTrayIcon`, first-class on Windows, confirmed via
  Qt's own docs (`doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html`).
- **Global hotkey**: Qt has no built-in cross-application global shortcut
  API (`QShortcut` is app-focus-scoped only). The smallest robust approach
  on Windows is `ctypes`-based `user32.RegisterHotKey` combined with a
  `QAbstractNativeEventFilter` subclass that intercepts `WM_HOTKEY` in
  Qt's native event loop — no extra dependency (`ctypes` is stdlib), no
  large automation framework (explicitly avoiding packages like `keyboard`,
  which installs a global low-level keyboard hook and has a worse security/
  AV-flagging profile than a single registered hotkey ID).
- **Screen capture**: `QScreen.grabWindow(0)` captures a full monitor;
  `QGuiApplication.screens()` enumerates monitors with `geometry()`
  (logical) and `devicePixelRatio()` (DPI) per screen — sufficient for the
  product's needs. `mss` (pure-Python + ctypes, zero heavy dependencies)
  is the documented fallback if Qt's own capture proves insufficient for
  any edge case (e.g. capturing content Qt's own compositor excludes) —
  not needed unless that's actually hit.
- **Translucent fullscreen selection overlay + mouse-drag rectangle**: a
  frameless, `Qt.WindowTransparentForInput`-free `QWidget` with
  `Qt.WA_TranslucentBackground`, custom `paintEvent` for the darkened
  background + selection rectangle, and `mousePressEvent`/
  `mouseMoveEvent`/`mouseReleaseEvent` for the drag — standard Qt overlay
  pattern.
- **DPI/multi-monitor**: `QScreen.devicePixelRatio()` gives the
  logical-to-physical conversion factor per monitor; Qt's own coordinate
  system already separates logical (widget/mouse events) from physical
  (pixmap) coordinates, which is less error-prone than reimplementing that
  conversion by hand across a Rust/React IPC boundary as the Tauri plan
  would have required.
- **Clipboard**: `QGuiApplication.clipboard()`, first-class Qt API.
- **File dialog**: `QFileDialog`, first-class Qt API.
- **RTL/Urdu**: Qt's text layout engine has built-in bidi support
  (`Qt::LayoutDirection`, per-widget `QTextOption` direction) — this is
  more mature out of the box than building RTL handling in a web UI from
  scratch.
- **Tables/code blocks**: `QTableWidget`/`QTableView` for structured table
  display with copy/export actions; a monospace `QPlainTextEdit` (read-only)
  for code, matching the existing "no rewriting, preserve whitespace
  exactly" rule from `docs/V5_GEMINI_DEEP.md`.
- **Settings**: a plain `QDialog` with `QSettings`-backed persistence
  (Qt's built-in cross-platform settings storage, backed by the Windows
  registry on Windows) — no extra dependency.
- **Background OCR without freezing the UI**: `QThread` (or `QRunnable` +
  `QThreadPool`) running `OCRService.process()` off the GUI thread, results
  delivered back via Qt signals — the standard, documented Qt worker-thread
  pattern. EasyOCR's model construction happens lazily on the worker
  thread on first use, same lazy-construct-and-cache pattern the codebase
  already uses elsewhere, so the GUI thread never blocks on model load.

## Single process vs. a separate worker process

Evaluated per item 9. **Single process, `QThread` workers — no separate
Python worker process.**

- EasyOCR/PyTorch inference is not GIL-bound in the way that matters here:
  the heavy work happens inside PyTorch's own C++/native tensor operations,
  which release the GIL during computation, so a `QThread` running
  `OCRService.process()` does not block Qt's event loop even though
  Python's GIL exists.
- A crash inside EasyOCR (e.g. a malformed image causing a hard native
  crash) would be process-isolated with a separate worker process; this is
  the main real argument *for* a subprocess. It's not chosen for V6 because
  it reintroduces the exact IPC-boundary complexity (serialization,
  lifecycle, health protocol) that switching away from Tauri was meant to
  eliminate, for a failure mode (native crash mid-recognition) that has not
  been observed as a real problem in this project's EasyOCR usage so far.
  Worth revisiting only if it actually happens in practice.
- Packaging is simpler with one process (one PyInstaller/Nuitka target
  instead of two), startup is faster (no subprocess spawn + handshake),
  and there is materially less code to write and maintain.

## Disk footprint (verified before install — see conversation)

`.venv` is at `D:\Local OCR\.venv`; `pip install` writes there. PySide6
wheels total roughly 150-250MB (Qt 6's core + widgets + gui modules are the
bulk of it) — this lands entirely on `D:`, same as every other dependency
this project already has installed. `TEMP`/`TMP` were redirected to a
`D:`-based directory for the install process only (not globally) to keep
pip's extraction scratch space off `C:` as well.

## Revised V6 milestone plan

- **V6.1** (done): desktop shell — launch, open an existing image
  file, run Fast OCR via a `QThread` worker, display the result, Copy.
  No hotkey, no capture, no tray yet — proves the shell + worker-thread +
  `OCRService` integration in isolation, same "validate one thing at a
  time" discipline the original Tauri plan specified.
- **V6.2** (done): system tray + global hotkey (`RegisterHotKey` + native
  event filter) + close-to-tray + a minimal Settings dialog. See
  `docs/V6_2_TRAY_HOTKEY.md`.
- V6.3 (next): screenshot capture + region-selection overlay.
- V6.4: compact result popup near cursor/hotkey location.
- V6.5: Gemini Deep Analyze wired into the desktop shell (reusing
  `build_production_gemini_provider` and the same explicit-consent flow
  `docs/V5_GEMINI_DEEP.md` already established for Streamlit).
- V6.6: Settings dialog + visual polish pass.

Packaging (PyInstaller/Nuitka spike) stays deferred until after the shell
is proven, per the same reasoning `docs/V6_DESKTOP_ARCHITECTURE.md` already
gave for not front-loading packaging experiments.

## What stays true from the superseded document

The IPC-contract *thinking* (a stable, flattened, versioned projection of
`DocumentResult` rather than exposing raw Python object internals) still
applies conceptually to the boundary between `OCRService` and the Qt UI
layer, even though there's no process/IPC boundary anymore — the desktop
UI code should still go through a thin, explicit result-mapping function
rather than reaching into `DocumentResult` internals ad hoc from widget
code. The credential-boundary rule (Gemini key never touches UI-owned
storage beyond `local_lens.env_file`/Windows Credential Manager, never
logged) is unchanged. The capture-lifecycle privacy rule (temp file
deleted after OCR unless the user explicitly exports) is unchanged. Scope
discipline (no chat/RAG/history/accounts/sync in V6) is unchanged.

## Streamlit

`app.py` remains the local dev/test UI, unchanged and not removed. The
desktop client becomes the flagship once its own workflow is verified —
same rule as before, just with a different UI framework underneath.
