# V6: Desktop client architecture (Windows-first)

This document is the architecture audit and decision record for turning Local
Lens into a native Windows screenshot-intelligence utility, built alongside
(not instead of) the existing Streamlit prototype. It covers the
Tauri/Python boundary, the IPC contract, capture strategy, DPI handling,
credential strategy, and packaging plan. It also records the toolchain/disk
plan and the current blocker on MSVC installation (see "Toolchain and disk
safety" below) — this document was written to be actionable even while that
blocker is unresolved.

## Why Streamlit isn't the flagship anymore, but isn't deleted

The Streamlit app (`app.py`) proved the product decisions (Fast vs. Deep,
explicit consent, Gemini production wiring — see `docs/V5_GEMINI_DEEP.md`).
It remains the local dev/test UI and is not being removed. The desktop
client is a new, separate surface that reuses the same Python core
(`local_lens/`) rather than a rewrite.

## Architecture decision

```
Tauri desktop UI (React/TypeScript)
        |
        | JSON-lines over stdio (persistent process)
        v
Python sidecar (local_lens.sidecar)
        |
        v
OCRService / EasyOCR / GeminiDeepProvider  (unchanged, existing code)
```

**Chosen: Option A variant — a persistent local Python sidecar process,
addressed over stdin/stdout JSON-lines, spawned and owned by Tauri.**

### Options considered

| Option | Startup cost per capture | Packaging | IPC complexity | Process lifetime | Verdict |
|---|---|---|---|---|---|
| A. Persistent Python sidecar (stdio) | One-time, at app launch | One Python process to bundle | Low (JSON lines) | Long-lived, Tauri-managed | **Chosen** |
| B. Spawn `local-lens` CLI subprocess per request | EasyOCR cold-load every capture (seconds, and materially worse once Deep/table extraction is warm-cached in-process) | Same binary as A | Very low (argv + stdout) | One-shot | Rejected: repeated cold starts defeat the "instant OCR" product goal |
| C. Persistent local HTTP service | One-time | Same as A, plus a port | Medium (HTTP client, port conflicts, needs a security story for localhost) | Long-lived | Rejected for V6: no benefit over stdio for a single-consumer desktop app, adds a port to manage/secure |
| D. Rewrite OCR integration in Rust | N/A | N/A | N/A | N/A | Rejected: EasyOCR/PaddleOCR, script detection, Urdu normalization, and the Gemini provider are mature, tested Python — reimplementing in Rust duplicates working code for no product benefit, explicitly out of scope per the task |

Option B was the default naive approach and is explicitly what this decision
avoids: EasyOCR's construction cost (model load) is the exact problem this
project already worked around once in the Streamlit app via `@st.cache_resource`-style
warm reuse. A per-capture subprocess throws that away on every hotkey press.
Option C's HTTP transport was considered mainly for debugability, but for a
single desktop process talking to a single local sidecar it adds attack
surface (a local port) and lifecycle complexity (bind failures, port
conflicts) with no corresponding benefit over line-delimited JSON on a pipe
Tauri already owns and can kill cleanly. Option A additionally avoids
reintroducing multi-provider/network complexity — the sidecar imports
exactly the same `local_lens` package the CLI and Streamlit app already use.

## IPC contract (protocol_version 1)

Newline-delimited JSON on the sidecar's stdin/stdout. One request per line,
one response per line, in the order requests arrive (the sidecar processes
requests serially — OCR is CPU/GPU-bound and the whole point of the
persistent process is a single warm model, not concurrency).

Request:

```json
{"protocol_version": 1, "request_id": "a1b2c3", "operation": "ocr", "mode": "fast", "image_path": "C:\\Users\\...\\tmp\\capture.png", "lang": "en"}
```

Response (success):

```json
{"protocol_version": 1, "request_id": "a1b2c3", "success": true, "result": {"text": "...", "engine": "easyocr", "content_type": "table", "detected_scripts": ["Latin"], "detected_languages": ["en"], "tables": [...], "document_blocks": [...], "timings_ms": {"ocr_ms": 812, "total_ms": 940}}, "error": null}
```

Response (failure):

```json
{"protocol_version": 1, "request_id": "a1b2c3", "success": false, "result": null, "error": {"kind": "deep_auth_error", "message": "Gemini rejected the configured API key."}}
```

Design rules:
- `image_path`, not inline base64 — captures are already written to a temp
  file (see "Capture lifecycle" below); this keeps request lines small and
  avoids a base64 encode/decode on every request.
- The `result` shape is a deliberately flattened, stable projection of
  `DocumentResult` — not `dataclasses.asdict()` dumped raw. The Rust/React
  side must never depend on Python-internal field names or types (e.g. no
  `BoundingBox` dataclass repr) — this is the same "don't expose arbitrary
  Python object representations" rule the task specified.
- `protocol_version` is checked by both sides; a mismatch is a hard error,
  not a best-effort parse.
- Operations: `ping`, `status`, `ocr` (mode: `fast`|`deep`), `shutdown`.
  `deep` requires the caller to have already shown the privacy disclosure —
  the sidecar does not gate consent, Tauri/React does (consistent with the
  Streamlit app's `deep_consent_given` pattern).
- The sidecar never initiates a Gemini request on `ping`/`status`/startup —
  Deep stays request-driven, matching V5's "never automatic" rule.

## Sidecar lifecycle

```
Tauri app launch
  -> spawn python -m local_lens.sidecar (D: DevTools rustup/cargo unaffected; this is the project's own .venv)
  -> send {"operation":"ping"}
  -> expect {"success":true,"status":"ready"} within a bounded timeout
  -> UI shows "Local OCR starting..." until ready, never a frozen window
```

- EasyOCR construction happens **lazily, on first `ocr` request**, not at
  `ping` time — `ping`/`status` must return immediately so the UI can show
  "Ready" for hotkey/capture availability without forcing a model load the
  user hasn't asked for yet. This mirrors the existing engine modules'
  lazy-construct-and-cache pattern (`paddleocr_engine.py` et al.).
- On sidecar crash (pipe closed unexpectedly / process exit), Tauri detects
  it, shows "OCR unavailable," and offers one automatic restart attempt; a
  second crash within a short window stops auto-restarting and requires a
  manual "Retry" action — never an infinite respawn loop.
- `shutdown` is sent (or the process is killed) when the Tauri app exits, so
  no orphan Python process survives app close — this is a hard requirement,
  not a nice-to-have, since a leaked EasyOCR process on a low-disk/low-RAM
  laptop is exactly the failure mode this project's safety rules exist to
  prevent.

## Capture lifecycle and privacy

```
hotkey -> capture region -> write to a per-run temp file
        -> sidecar OCR request (image_path)
        -> sidecar responds
        -> temp file deleted (unless user explicitly exports/saves)
```

Captures are never written to a permanent location by default. The temp
directory is process-scoped (a subdirectory under the OS temp dir, cleaned
on both successful OCR and on error) — this needs an explicit cleanup test
in Rust (delete-after-use, delete-on-app-exit-for-any-leftovers).

## Screen capture strategy (Windows-first)

Two options researched:

- **`windows-capture` (Rust crate, Windows Graphics Capture/DXGI)** —
  lower-level, better performance and per-monitor control, actively
  maintained, Windows-native (matches the "Windows 11 first" scope). No
  Electron-style overhead. This is the preferred path for the actual
  region-capture milestone.
- **`tauri-plugin-screenshots`** — simpler integration surface, but
  monitor/window-granularity capture is a worse fit for "drag a rectangle
  anywhere across possibly multiple differently-DPI-scaled monitors,"
  which is the product's actual requirement. Kept as a fallback if
  `windows-capture` integration proves harder than expected within this
  phase.

Decision: prefer `windows-capture` for the real region-selection milestone,
but that milestone is explicitly *not* part of this phase's deliverable
(see "What this phase delivers" below) — evaluating and wiring a capture
crate is deferred until after the sidecar + basic Fast-OCR-on-an-open-file
milestone is proven, per the task's own sequencing ("build this before
screenshot-region selection").

## Global hotkey

Registered via Tauri 2's official `@tauri-apps/plugin-global-shortcut`
(current stable Tauri 2 plugin, not a Tauri 1-era API). Candidate default:
`Ctrl+Shift+Space` — chosen specifically to avoid `Win+Shift+S` (owned by
Windows' own Snipping Tool; Local Lens must not hijack it, per explicit
product scope) and other common IDE/browser bindings. The exact default
still needs a collision check against commonly-installed Windows software
before being finalized in the Settings milestone. If registration fails
(already claimed by another app), the UI must show "Shortcut unavailable.
Choose another shortcut in Settings." rather than silently failing or
crashing — this becomes a Settings-surface requirement once that milestone
starts, not implemented in this phase.

## DPI and multi-monitor (design, not yet implemented)

Selection coordinates from the overlay window are in **logical** pixels;
the captured bitmap is in **physical** pixels. The conversion needs
`physical = logical * (monitor_dpi / 96)`, computed per-monitor (Windows
allows different scale factors per monitor). This becomes a small, unit-
testable Rust function (`logical_to_physical(point, monitor_scale)`) once
the capture/overlay milestone starts — documented here so the milestone
doesn't have to rediscover the requirement from scratch.

## Credential boundary

The Gemini API key stays server-side in the Python sidecar exactly as it
does today (`LOCAL_LENS_GEMINI_API_KEY`, resolved via
`local_lens/env_file.py`). React/TypeScript never holds the key — a Deep
request is `{"operation":"ocr","mode":"deep","image_path":...}`; the
sidecar resolves the credential internally, matching item 40's requirement.

For desktop development, `.env` at the repo root continues to work (the
sidecar imports the same `local_lens.env_file.load_env()`). Production
packaging cannot ship a plaintext `.env` in an installer — recommended
target is **Windows Credential Manager** via a small, well-maintained Rust
crate (e.g. `windows-rs`'s `Security::Credentials` bindings, or the
higher-level `keyring` crate which wraps it) so an end user enters their
key once in a Settings UI and it's stored using the OS's own credential
store rather than a file. This is a recommendation for a later packaging
milestone, not implemented in this phase (task explicitly asked for
research, not implementation, here).

## Packaging strategy (research, not implemented this phase)

The open question is "how do we ship Python + EasyOCR without asking users
to install Python." Options, roughly in order of maturity for this use
case:

- **PyInstaller** producing a single sidecar executable, bundled as a Tauri
  "external binary" (sidecar). Most mature, most examples for exactly this
  Tauri pattern. Caution items per the task: PyTorch/EasyOCR pull in large
  hidden imports and can produce a multi-hundred-MB to >1GB executable;
  first-run antivirus/Defender false-positive risk on an unsigned bundled
  exe is real and should be planned for (code signing eventually); startup
  time of a PyInstaller-frozen EasyOCR process needs to be measured before
  committing.
- **Nuitka**: potentially smaller/faster output than PyInstaller for
  numeric-heavy code, less battle-tested for EasyOCR/PyTorch specifically;
  worth a small spike later, not now.
- **Requiring a user-installed Python**: rejected as a shipped-product
  requirement (explicitly ruled out by the task) — acceptable only for
  this repo's own development flow via `.venv`, never for an end-user
  installer.

No packaging experiment was run in this phase — building a PyInstaller
bundle of EasyOCR/PyTorch repeatedly during iteration is exactly the kind
of multi-GB-temp-artifact activity item 45 says to defer on this laptop's
current disk budget. This is documented as the next research spike, not
attempted here.

## Toolchain and disk safety

Repository is on `D:` with hundreds of GB free; `C:` has a hard, narrow
budget (~6GB free at the time of this work, itself only slightly recovered
from the original disk-exhaustion incident that created this project's
safety rules).

- **Rust**: installed via `rustup-init.exe` with `RUSTUP_HOME=D:\DevTools\rustup`
  and `CARGO_HOME=D:\DevTools\cargo` (both pre-set as persistent user
  environment variables before this phase started). Verified after install:
  `rustc 1.98.0` / `cargo 1.98.0`, both toolchain and registry entirely
  under `D:\DevTools`, zero bytes written to `%USERPROFILE%\.rustup` or
  `%USERPROFILE%\.cargo`. Measured disk delta: `C:` unchanged (6.11GB free
  before and after), `D:` −0.59GB. This is exactly the intended outcome.
- **MSVC Build Tools / Windows SDK**: **not installed in this phase.** See
  the toolchain footprint plan delivered in-conversation for the full
  component/size breakdown and the reasoning for pausing here — in short,
  the Windows SDK and the shared Visual Studio Installer components have a
  well-known Microsoft limitation where they cannot be fully redirected off
  `C:` regardless of `--installPath`, and the realistic unavoidable
  `C:` footprint plus installer working-space headroom does not fit
  safely within the currently available ~6GB with the requested 10GB
  post-install safety margin. Recommendation: free additional `C:` space
  before installing, using the disk-audit plan also delivered
  in-conversation (temp files, browser caches, npm/pip cache relocation,
  old installers, Windows Update cleanup — deliberately excluding personal
  files, EasyOCR models, project files, and any system-directory changes).
- **Cargo build output**: once a `desktop/src-tauri` project exists, set a
  project-local `CARGO_TARGET_DIR` (e.g. `desktop/src-tauri/target` is
  already under `D:\Local OCR`, so no extra configuration is strictly
  required — the repo's own location on `D:` already keeps `cargo build`
  output off `C:` by default; an explicit `CARGO_TARGET_DIR` env var is a
  belt-and-suspenders option, not documented as mandatory here since it
  isn't needed given the repo's location).
- **npm**: Node/npm already installed (v20.19.4 / 10.5.2) via nvm4w; npm's
  cache currently resolves to `C:\Users\<user>\AppData\Local\npm-cache` and
  measured ~1.6GB, one of the candidate categories for the manual C:
  cleanup pass before an MSVC install. Not relocated automatically in this
  phase (manual cleanup commands were provided separately, not executed);
  `desktop/node_modules` itself will live under `D:\Local OCR\desktop`
  regardless, so it does not threaten `C:` either way.

## What this phase delivers vs. defers

This phase (per the task's own "do NOT immediately code the whole desktop
app" instruction) delivers the architecture decision and this document.
Actual desktop scaffolding (the `desktop/` Tauri+React project, the Python
sidecar module, and the first "open an image -> Fast OCR -> result" runnable
milestone) is the next step, gated on the MSVC toolchain decision above
since a Tauri Rust project cannot compile without it. Screenshot capture,
global hotkey, region-selection overlay, tray icon, and Settings UI are
explicitly out of scope for this phase (per the task's own sequencing:
milestone 1 first, capture second).

## Scope discipline

Not part of this phase or product: chat, RAG, OCR history database,
accounts, sync, subscriptions, MCP, browser-extension integration, AI
explanations/translation/summarization. V6 is capture -> OCR -> optional
Deep, nothing more.
