# 🔍 Local Lens

## What is Local Lens?

Local Lens is a Windows desktop utility that lets you press a shortcut,
select anything on your screen, and turn it into usable text. Press
**`Ctrl+Shift+Space`**, drag a box around a paragraph, a line of code, a
table, a chat message, a menu, a scanned document — anything visible on
your screen — and Local Lens reads it back to you as real, selectable,
copyable text in a couple of seconds.

It runs as a small icon in your system tray. No accounts, no cloud upload
required to use it, no subscription. Grab the portable ZIP, run the exe,
press the shortcut.

**Capture → Read → Copy.**

## Download

The latest release is **v0.4.0**, a self-contained Windows portable build
— no installer, no separate Python setup, no internet connection required
to run Fast OCR.

1. Download `LocalLens-v0.4.0-windows-x64-portable.zip` from the
   [Releases page](https://github.com/danishirfan21/Local-OCR/releases)
   (~565 MB download; ~1.06 GB once extracted — most of that is the
   bundled OCR model weights and the Python/Qt runtime, so Fast OCR works
   completely offline out of the box).
2. Extract the ZIP anywhere (Desktop, Downloads, an external drive — it
   doesn't need to sit next to the source code or a Python install).
3. Run `LocalLens.exe` inside the extracted folder.
4. The app appears in your system tray. The first launch takes a few
   extra seconds to warm up the local OCR engine ("Starting local OCR…" →
   "Fast OCR ready").
5. Press `Ctrl+Shift+Space` anywhere on your screen, drag a box around
   something, and the extracted text appears in a small popup with a
   Copy button.

**A note on Windows SmartScreen:** the executable isn't code-signed (that
requires a paid certificate), so Windows may show an "Unknown publisher"
warning the first time you run it. Local Lens doesn't ask you to disable
Windows Defender, SmartScreen, or any other security feature to use it —
if you see that warning, it's expected for an unsigned indie build, not a
sign something is wrong; check the SHA-256 checksum published with the
release if you want to confirm the file wasn't tampered with in transit.

Local Lens moves from "OCR that dumps text" toward:

**Capture → Understand → Act**

> Take a screenshot → Local Lens figures out what it is (plain text, code, a
> table, Urdu, ...) and how best to read it → you get the right export/action
> for that content, with the reasoning visible, not hidden.

**Fast when local OCR is enough. Deep when structure matters.** Fast mode
stays on-device; Deep mode is explicitly cloud-assisted — see below. Local
Lens does not claim to be "fully private AI" now that Deep Analyze exists;
it claims exactly what's true for each mode, stated plainly.

The GitHub repo is still `Local-OCR`; the app itself is **Local Lens**.

## Features at a glance

- **Global capture shortcut** (`Ctrl+Shift+Space` by default, changeable
  in Settings) — works from anywhere, no need to switch to Local Lens
  first.
- **Fast OCR, fully offline** — English and Urdu out of the box, powered
  by a locally-run OCR engine with its model weights bundled directly
  into the portable build. Typically returns a result in a few seconds.
- **Handles more than plain paragraphs** — code snippets (monospaced,
  whitespace preserved), simple tables, and mixed Urdu/English text.
- **Optional Deep Analyze** — for complex layouts and documents where
  Fast OCR isn't enough, you can opt in (per capture, with a privacy
  notice shown first) to send the image to Google's Gemini API using
  your own API key. Nothing is sent anywhere unless you explicitly click
  this button.
- **System tray app** — stays out of your way; Capture, Open, Settings,
  and Quit are all one right-click away.
- **Auto-copy and popup controls** — optionally skip the manual Copy
  click, or close the result popup automatically after copying.
- **Start with Windows** (optional, off by default) — launches quietly
  into the tray on login, no console window.

## Privacy, in plain terms

- **Fast OCR never leaves your machine.** No image, no extracted text, no
  usage data is sent anywhere — this is enforced in code and tested
  (`tests/test_no_silent_network.py` fails the build if a Fast-mode code
  path ever opens a network connection).
- **Deep Analyze is the one exception, and it's opt-in every time.**
  Clicking "Deep Analyze ✨" sends the captured image to Google's Gemini
  API using your own API key. You see a privacy disclosure the first time
  in a session before it's sent. If you never click that button, nothing
  is ever sent to Gemini or anywhere else.
- **No accounts, no telemetry, no analytics, no update checks.** Local
  Lens doesn't phone home for any reason.
- Application logs go to your normal Windows AppData folder (for
  diagnosing crashes) and record only event names — never the text you
  extracted, never a screenshot, never an API key.

## Known limitations (honest, not hidden)

- **Windows only**, x64. There's no macOS or Linux build.
- **English and Urdu** are the two languages Fast OCR is tuned for today.
  Other languages aren't currently supported by the bundled models.
- **Fast OCR is OCR, not an AI reader** — it reads what's visually on
  screen well for clean text and UI, but complex documents, dense tables,
  and unusual layouts are exactly where Deep Analyze (Gemini) does
  measurably better; see the benchmark data linked below.
- **The portable build is large** (~565 MB ZIP, ~1.06 GB extracted)
  because it bundles a full local OCR model set so Fast OCR works
  offline. This is a deliberate trade-off, not an oversight.
- **The executable is unsigned**, so Windows SmartScreen may warn on
  first run (see the Download section above).
- **Multi-monitor setups are structurally supported but not as heavily
  live-tested** as a single-monitor setup — if you hit a capture-region
  issue on a multi-monitor rig, it's a genuine gap worth reporting, not a
  known-and-ignored one.
- **No installer, no auto-update, no uninstaller beyond deleting the
  folder** — this is intentional for this release (see "Do not
  feature-creep" in the project's own release notes); Local Lens also
  writes a small Settings entry to `HKCU\Software\Local Lens` and,
  optionally, one `HKCU` Run-key entry if you enable "Start with
  Windows" — both are removed by turning the relevant setting back off
  before you delete the folder.

## Two modes: Fast (local) and Deep Analyze (Gemini, explicit)

- **Fast** — EasyOCR (optionally PaddleOCR), runs entirely on this device,
  no network call, on by default. Already excellent for clean text, simple
  screenshots, and basic OCR.
- **Deep Analyze** — sends the selected image to Google's Gemini API
  (`gemini-3.1-flash-lite`, frozen and BYOK — see
  [Deep Analyze](#deep-analyze-gemini-byok) below), for cases where it
  measurably helps: complex layouts, tables, and document structure. Never
  auto-triggered — requires an explicit button click, and shows a privacy
  disclosure first. If nothing is configured it shows **"Deep Analyze
  requires a Gemini API key"** and Fast mode is unaffected.

This choice is evidence-based, not a guess: see
[docs/V5_GEMINI_DEEP.md](docs/V5_GEMINI_DEEP.md) for the benchmark data
behind it (`docs/DEEP_PROVIDER_RESULTS.md`) and why Gemini specifically was
chosen as the initial production backend.

Local Lens does not require, install, or bundle PaddlePaddle/PaddleOCR-VL by
default, and self-hosting PaddleOCR-VL has been shelved for now based on
that benchmark data (see `docs/V5_GEMINI_DEEP.md`). The old local-PaddleOCR-VL
path still exists (`local_lens/engines/paddleocr_vl_engine.py`) as an
explicitly optional, resource-intensive legacy backend — see
`requirements-paddle.txt`.

---

# Project internals & development

Everything above this line is the user-facing README. Everything below is
project history, architecture, and developer setup — useful if you're
building from source, contributing, or curious how a specific claim above
was verified.

## Current (implemented and verified this iteration)

**Core pipeline** (`local_lens/`, zero Streamlit dependency):
- Pluggable OCR engines behind a common interface — EasyOCR (default) and
  an optional PaddleOCR backend, both producing a unified `DocumentResult`
  (text, per-block bounding boxes, confidence, detected scripts/languages,
  tables, timings).
- **"Auto" engine routing** (`local_lens/routing/engine_router.py`):
  a heuristic `classify_input()` (EXIF presence, color/edge properties) picks
  screenshot vs. photo vs. document-scan, and routes to the engine that
  benchmarked better for that input type — informed by a real finding from
  this project's own benchmarks (PaddleOCR's document-oriented pipeline
  underperformed EasyOCR on small clean screenshots; see
  [benchmarks/README.md](benchmarks/README.md)). Every routing decision
  carries a human-readable reason, shown in the UI's "Advanced details"
  panel — manual engine selection still works exactly as before.
- **Real table extraction**, not just detection: `local_lens/tables/` wraps
  PaddleOCR's `TableRecognitionPipelineV2` (a separate, table-focused
  pipeline) and returns actual rows/cells, exportable as CSV, Markdown, or
  JSON. Only runs when content classification already suspects a table, and
  its failure never loses the plain OCR result underneath it.
- **Urdu as a first-class language**, not just a selector option:
  Unicode-block script detection (`local_lens/scripts.py`), conservative
  NFC + stray-bidi-character normalization (`local_lens/text_normalization.py`),
  and reading-order reconstruction that already handles mixed Urdu/English
  lines correctly (it sorts by on-screen position, not text direction — see
  that module's docstring for exactly what this does and doesn't fix).
- **Heuristic content classification**, now geometry-aware: table detection
  uses OCR bounding-box column alignment in addition to text/punctuation
  patterns, on top of the existing text/code/table/unknown heuristic.
- **Per-stage performance timing** (`local_lens/timing.py`) surfaced in
  metadata and the UI's Advanced details panel.
- **Structured exports**: TXT, Markdown, and JSON for regular results;
  CSV/Markdown/JSON for tables (via Python's `csv` module, correctly
  handling quotes/commas/Unicode/empty cells).
- Preprocessing pipeline (None/Auto/High-contrast, PIL-only), bounding-box
  overlay visualization (OCR blocks + table regions), clipboard/Snipping
  Tool auto-watch workflow — all carried over from V2.

**UI** (`app.py`, Streamlit): Auto/EasyOCR/PaddleOCR engine selection,
content-aware export actions (code → Download Code/JSON; table → live
dataframe preview + CSV/Markdown/JSON; everything else → TXT/Markdown/JSON),
scoped RTL text-area styling when Urdu is the primary detected language, an
"Advanced details" expander showing routing rationale + per-stage timings,
and graceful degradation — a table-extraction failure shows an inline note
and falls back to plain text rather than losing the result.

**Testing**: 140+ unit tests (mocked engines/extractors/HTTP transport — no
model downloads, no real network calls), covering models, hashing,
reconstruction (including a mixed-Urdu/English fixture), classification
(text + geometry signals), routing, input-type heuristics, script detection,
text normalization, table parsing + cleanup, CSV/Markdown export, timing,
benchmark metrics, the CLI, backend capability reporting, and every Deep
Analyze provider failure mode (timeout/401/403/429/5xx/malformed response)
against a fake HTTP transport.

**Benchmarking**: a real corpus (`benchmarks/corpus.py`) — 11 synthetic,
safe-to-commit fixtures across English, Urdu, mixed, short-UI, tables, and
code — scored with CER, WER, normalized similarity, latency, and (for
tables) row/column/cell accuracy, written to `benchmarks/results/*.json`.
See [benchmarks/README.md](benchmarks/README.md) for the corpus's known
limitations (notably: this environment's Pillow lacks `raqm` text shaping,
so rendered Urdu fixtures use isolated letterforms, not joined script).

**CLI** (`local_lens/cli.py`, `local-lens` entry point via `pyproject.toml`):
`local-lens extract <image> [--mode fast|deep] [--engine easyocr|paddleocr]
[--format text|markdown|json|csv]` and `local-lens doctor` (reports which
backends are available/configured). No Streamlit import anywhere in its
import chain.

**Backend capability model** (`local_lens/backends.py`): `BackendStatus`
distinguishes *not installed* (a local package is missing), *not
configured* (no remote provider set up), and *available*, rather than
probing dependencies ad hoc — the UI's "Model availability" panel and the
CLI's `doctor` command both read from this.

## Deep Analyze (Gemini, BYOK)

As of V5, Local Lens's production Deep Analyze feature is **Gemini only**,
frozen to the exact model measured in a real benchmark
(`docs/DEEP_PROVIDER_RESULTS.md`: 12/12 successful, 12/12 valid structured
output, 0 malformed, 0 hallucinated content, composite score 0.9934):

```env
LOCAL_LENS_GEMINI_API_KEY=
```

Get a key from [Google AI Studio](https://aistudio.google.com/apikey) (see
Google's own docs for current sign-up steps — Local Lens doesn't operate
this infrastructure or issue keys). Copy `.env.example` to `.env` and fill
this in, or set it as a real environment variable — either works
(`local_lens/env_file.py`: real env vars always win over `.env`). Leave it
unset and Deep Analyze simply shows **"requires a Gemini API key"**; Fast
mode is completely unaffected.

**Deep Analyze is never automatic.** Selecting it in the sidebar shows a
privacy disclosure and a button — nothing is sent until you click it:

> Deep Analyze sends this image to Google's Gemini API for processing.
> Google's free-tier API may use submitted content to improve products and
> may involve human review.

That free-vs-paid-tier distinction is real and matters: Google's own terms
treat the free Developer API tier differently from a paid/billed account
(free-tier content may train Google's models and be human-reviewed; paid
is not used for training). Local Lens can't detect which tier your key is
on — set `LOCAL_LENS_GEMINI_TIER=free|paid` to get tier-specific messaging,
or leave it unset for conservative (assume-free-tier) messaging.

If Deep Analyze fails (no key, rejected key, rate limit, timeout, server
error), the UI says so explicitly — it never silently substitutes the Fast
result and calls it a successful Deep result. Your Fast result (already
computed automatically, since Fast is always local/instant) stays visible
in its own section regardless of what Deep does.

**Table handling**: when Gemini identifies a table, Local Lens shows a real
structured preview (not flattened back to plain text) with CSV/Markdown/
JSON export, and handles multiple tables in one image explicitly (a
selector, not a silent pick-the-first-one).

**Under the hood**, Deep Analyze is provider-based
(`local_lens/deep_analysis/`), not hardwired to Gemini specifically — the
`DeepAnalysisProvider` abstraction (same shape as `OCREngine`: `name` +
`extract(image, langs)`) is intentionally still extensible, with adapters
for OpenAI-compatible endpoints, Anthropic, and a self-hosted PaddleOCR-VL
vLLM server already built and tested. **None of those are exposed as
normal UI/CLI choices yet** — only Gemini is, based on actual benchmark
evidence, not a guess. See
[docs/V5_GEMINI_DEEP.md](docs/V5_GEMINI_DEEP.md) for the full architecture,
why Gemini was chosen, why self-hosting PaddleOCR-VL was shelved, and what
would justify revisiting either decision.

**CLI**: `local-lens extract image.png --mode deep --allow-remote` (the
`--allow-remote` flag is required for non-interactive/scripted use — it
prevents a script from unexpectedly uploading an image; Fast mode needs no
such flag, since it never leaves the device:
`local-lens extract image.png --mode fast` just works, no key, no flag, no
internet).

**Failure handling**: timeouts, 401/403, 429, and 5xx each map to a
specific, secret-free error (`local_lens/deep_analysis/base.py`) — the UI
shows the specific failure rather than crashing or pretending Fast is Deep;
the CLI reports a clear non-zero-exit error. No request retries on
401/403 (a bad key won't fix itself on retry); one retry on timeout/429/5xx.

**Privacy**: Fast mode never leaves the device — enforced by
`tests/test_no_silent_network.py`. Deep Analyze sends the selected image to
Google's Gemini API, and only when you explicitly click the button; opening
the app, switching tabs, uploading, and Fast extraction all make zero
network calls, and mode-switching alone (without an image) never triggers
a request either.

**Benchmark/developer tooling stays separate**: `local-lens
benchmark-deep` (Groq/Gemini/OpenAI/Anthropic/Fireworks bake-off machinery)
uses its own dedicated `LOCAL_LENS_BENCHMARK_*` credentials, never the
production `LOCAL_LENS_GEMINI_API_KEY` above, and vice versa — `local-lens
providers` reports both sets distinctly so one is never mistaken for the
other. See [docs/DEEP_PROVIDER_EVALUATION.md](docs/DEEP_PROVIDER_EVALUATION.md),
[docs/REMOTE_BENCHMARK_PLAN.md](docs/REMOTE_BENCHMARK_PLAN.md), and
[docs/DEEP_PROVIDER_RESULTS.md](docs/DEEP_PROVIDER_RESULTS.md) for the full
research/benchmark trail behind the Gemini decision.

## Experimental (not in the production path)

**PaddleOCR-VL** (`experiments/paddleocr_vl/`) — PaddlePaddle's ~0.9B
vision-language document-parsing model, evaluated against the same
benchmark corpus for a like-for-like comparison with EasyOCR/PaddleOCR.
Not imported by `local_lens/` or `app.py` anywhere. See that directory's
README for setup and results, and the "PaddleOCR-VL findings" section of
the V3 implementation report for measured numbers and their status
(measured-locally vs. upstream-claim vs. not-tested).

## Desktop (in progress, Windows-first)

A native Windows desktop client is being built alongside the Streamlit
prototype (which stays the primary dev/test UI until the desktop client's
own workflow is fully proven). Stack: PySide6 (Qt 6), single Python
process, importing `local_lens/` directly -- no Rust/Tauri, no IPC
boundary. See `docs/V6_DESKTOP_FRAMEWORK_DECISION.md` for why,
`docs/V6_2_TRAY_HOTKEY.md` for the tray/hotkey design,
`docs/V6_3_CAPTURE.md` for the capture workflow,
`docs/V6_4_RESULT_UX.md` for the result popup and Deep Analyze,
`docs/V6_5_RELEASE_READINESS.md` for Settings, startup behavior, secret
storage, and packaging research,
`docs/V6_6_PACKAGING_SMOKE_TEST.md` for the portable-build smoke test,
and `docs/V6_7_PORTABLE_OPTIMIZATION.md` for the size trim and
portability validation.

- **V6.1 — Open Image + Fast OCR** ✓ (`desktop/`, run with
  `python -m desktop.main`): open an existing image, run Fast OCR on a
  background thread, view/copy the result.
- **V6.2 — Background utility (tray + global shortcut)** ✓: system tray
  icon (Capture / Open Local Lens / Settings / Quit), a configurable
  global hotkey (default `Ctrl+Shift+Space`, native `RegisterHotKey`, no
  extra dependency), close-to-tray window behavior, and a minimal Settings
  dialog (shortcut editor + Gemini configured/not-configured status).
- **V6.3 — Region capture** ✓: `Ctrl+Shift+Space` (or tray Capture) dims
  the screen, drag a rectangle, and Fast OCR runs automatically on the
  selection (`QScreen.grabWindow` only, no extra dependency, no
  screenshot ever written to disk). DPI-aware (verified live at 125%
  scaling); multi-monitor is structurally supported but not live-verified
  on this single-monitor machine.
- **V6.4 — Result popup + Deep Analyze** ✓: capture now shows a compact,
  reusable popup (not the main window) with a "Reading selection…" state,
  content-aware Fast result (text/code/table, no fabricated table
  structure), and an optional Deep Analyze button that runs the production
  Gemini path on a background thread behind a one-per-session privacy
  prompt -- Fast and Deep results sit in separate tabs, and a Deep failure
  never touches the Fast result. EasyOCR is warmed up in the background at
  startup (~10s cold vs. ~0.3-0.6s warm, measured on this machine).
- **V6.5 — Release readiness** ✓: an expanded Settings dialog (General /
  Behavior / Deep Analyze), user-level "Start Local Lens with Windows"
  (HKCU Run key, no Administrator), a `--start-hidden` startup mode, an
  opt-in "Auto-copy Fast result after capture", an opt-in "Close popup
  after successful copy", a "Capture Now" button and readiness/Deep-status
  indicators on the main window, and packaging research (see
  `docs/V6_5_RELEASE_READINESS.md`) -- no build was executed.
- **V6.6 — Portable Windows build smoke-tested** ✓: a bounded PyInstaller
  `onedir` build (862MB, one invocation, entirely on `D:`) proved
  `LocalLens.exe` launches independently of any installed Python, and a
  live smoke test on the packaged executable confirmed the tray, global
  hotkey, region capture, real Fast OCR (external EasyOCR model cache),
  result popup, and clipboard Copy all work end-to-end -- see
  `docs/V6_6_PACKAGING_SMOKE_TEST.md` for the full record, including
  what wasn't live-verified this round (Open Image's file dialog, the
  tray context menu) and why. Not yet a polished release.
- **V6.7 — Portable build trimmed and independently verified** ✓: the
  packaged build is now 765MB (down from 862MB, via evidence-based
  exclusions -- confirmed safe by tracing actual runtime imports, not
  guessed), carries a real application icon and version metadata, and
  was proven genuinely portable by extracting the ZIP to a fresh
  location and launching it from an unrelated working directory with no
  dependency on the source checkout. Fast OCR still relies on an
  external, on-machine EasyOCR model cache rather than bundled weights --
  see `docs/V6_7_PORTABLE_OPTIMIZATION.md` for the licensing research and
  architecture prepared for closing that gap. Not yet a fully
  self-contained offline release.
- **V6.8 — Self-contained offline portable release candidate** ✓: the
  three EasyOCR model files (`craft_mlt_25k.pth`, `english_g2.pth`,
  `arabic.pth`, ~299MB, SHA-256-validated at build time) are now bundled
  directly into the portable build. **Fast OCR works fully offline** --
  the portable build includes its OCR models, and no model download or
  external `~/.EasyOCR` cache is required. Proven by launching the final,
  named, hashed release ZIP (`LocalLens-v0.4.0-windows-x64-portable.zip`)
  from a fresh extraction under a clean profile with no `.EasyOCR`
  directory at all: Fast OCR reached "ready" using only its bundled
  weights. See `docs/V6_8_SELF_CONTAINED_RC.md` for the full record,
  including the two items still needing manual (non-automated)
  verification -- Open Image's file dialog and the tray context menu.
- **V6.9 — Release-candidate QA + GitHub Release preparation** ✓: closed
  the two items V6.8 left as manual/non-automated (Open Image, the tray
  Settings/Quit actions) with real, exercised evidence rather than
  assumptions; found and fixed two real defects (the shipped ZIP never
  actually included `THIRD_PARTY_NOTICES.txt` despite the spec intending
  it to, and neither window ever set a branded title-bar icon); rebuilt
  once and re-verified after those fixes; and audited the final RC
  extraction for hardcoded developer paths, secrets, and leftover
  Paddle references (all clean). See `docs/V6_9_RC_QA.md` for the full
  record and `docs/releases/v0.4.0.md` for the release notes.

## Roadmap (not built)

- A live remote Deep Analyze provider actually provisioned and verified
  end-to-end (current work is mocked-transport-tested only; needs explicit
  approval to provision paid cloud infrastructure)
- Formula/equation recognition
- Layout-aware, multi-column reading order (current reconstruction is a
  deterministic single-pass heuristic, isolated in `reconstruction.py` so it
  can be swapped for a real layout model)
- Local LLM Q&A / reasoning over captured screenshots
- REST API and MCP server interfaces on top of the existing `local_lens/`
  core (the CLI is now built; the architecture is already
  Streamlit-independent for this reason)
- Semantic screenshot history / search
- Stronger code-block extraction (syntax-aware, not just heuristic)
- Local translation

## Architecture

```
Input                                local_lens/ (no Streamlit dependency)
 │                                    ├── models.py          DocumentResult, TextBlock,
 ├─ uploaded image                    │                      TableCell, TableResult, BoundingBox
 ├─ pasted image                      ├── scripts.py         Unicode script + language inference
 └─ clipboard screenshot              ├── text_normalization.py   conservative Urdu/Arabic cleanup
 │                                    ├── input_analysis.py  screenshot/photo/scan heuristic
 ▼                                    ├── routing/engine_router.py   Auto engine selection + why
 app.py (Streamlit UI) ─────┐        ├── engines/            OCREngine interface + backends
 local_lens/cli.py    ──────┼──────▶ ├── deep_analysis/     DeepAnalysisProvider (remote, BYOK)
                             │        ├── backends.py         capability/status model
 ▼                           ▼        ├── tables/             TableExtractor interface + backend
 UI / export           extract/doctor ├── preprocessing/       None / Auto / High-contrast
                                       ├── reconstruction.py   bbox-based reading order
                                       ├── classification.py   text/code/table (text + geometry)
                                       ├── timing.py            per-stage latency
                                       ├── export.py            txt / markdown / csv / json
                                       └── services/ocr_service.py   orchestrates all of the above
```

`app.py` and `local_lens/cli.py` only handle their own surface (layout/session
state, or argument parsing) — every OCR/Deep-Analyze/document-understanding
decision goes through `local_lens/`, which has no Streamlit import anywhere.
A `DeepAnalysisProvider` has the same shape as `OCREngine` (`name` +
`extract(image, langs) -> DocumentResult`), so `OCRService` runs Fast and
Deep Analyze through the identical code path.

`streamlit run app.py` is the canonical entrypoint. `streamlit run
ocr_app.py` still works too (a one-line compatibility shim).

## PaddleOCR (optional, legacy local heavy backend)

Not required for standard use — Fast mode works fully on EasyOCR alone, and
Deep Analyze is remote (see above). This section only applies if you
deliberately want the local PaddleOCR text engine, local table extraction,
or the legacy local PaddleOCR-VL path, on a machine with disk/RAM to spare
(paddlepaddle + paddleocr + paddlex together can consume several GB — see
`requirements-paddle.txt`).

`local_lens/engines/paddleocr_engine.py` uses PaddleOCR's current pipeline
API (`PaddleOCR(lang=...).predict(image)`, not the legacy `.ocr()` API).
Not installed by default (`paddlepaddle` is large and platform-specific):

```bash
pip install -r requirements.txt
pip install -r requirements-paddle.txt
```

If it isn't installed, the sidebar disables the PaddleOCR option and Auto
routing falls back to EasyOCR with an explanation, instead of crashing.

**Verified working** on Windows/CPU (`paddlepaddle` 3.3.1, `paddleocr`
3.7.0) with one real bug found and worked around: PaddlePaddle's CPU
(oneDNN/PIR) executor raised `NotImplementedError:
ConvertPirAttribute2RuntimeAttribute not support [...]` inside the text
detection op. `enable_mkldnn=False` avoids the broken code path (costs some
CPU speed; output correctness was unaffected in testing). The same
workaround is applied to the table extraction pipeline.

**Table extraction and the PaddleOCR-VL experiment both additionally need**
the `paddlex[ocr]` extra (discovered during this iteration — `PaddleOCRVL`
and `TableRecognitionPipelineV2` raise a clear `DependencyError` without
it):

```bash
pip install "paddlex[ocr]==<paddlex version installed above>"
```

See `requirements-paddle.txt` for the exact comment/version guidance.

## Urdu on Windows: a real encoding bug and its fix

While benchmarking Urdu this iteration, EasyOCR's **first-time** model
download crashed with `UnicodeEncodeError: 'charmap' codec can't encode
character '█'`. Root cause (confirmed via full traceback): EasyOCR's
own download-progress printer (`easyocr/utils.py`) writes a `█` (U+2588)
progress bar character to stdout, and this environment's default Windows
console encoding is `cp1252`, which can't represent it. This is an
upstream EasyOCR/Windows-console issue, not a Local Lens bug, but it
blocks first-time use of *any* not-yet-downloaded EasyOCR language pack on
an affected Windows setup. Fix (verified): run with UTF-8 stdout —

```bash
set PYTHONIOENCODING=utf-8   # Windows cmd
$env:PYTHONIOENCODING="utf-8"   # PowerShell
streamlit run app.py
```

Separately, V2's language mapping had `"ur" -> "urdu"` for PaddleOCR's
engine-specific code, which is wrong — `PaddleOCR(lang="urdu")` raises "No
models are available." The correct code is `"ur"`, identical to EasyOCR's.
Fixed in `local_lens/languages.py` this iteration; see the V3 report for
how it was found (by testing candidate codes directly against the
installed package rather than assuming).

> See "Privacy, in plain terms" near the top of this README for the
> user-facing privacy summary. One detail specific to running from
> source rather than the portable build: **model weights download from
> the internet on first use** of a local engine/pipeline (EasyOCR, and —
> only if you've opted into `requirements-paddle.txt` — PaddleOCR/the
> table pipeline/legacy local PaddleOCR-VL). One-time per engine/pipeline,
> not ongoing, and irrelevant to the portable build, which bundles its
> EasyOCR weights directly.

## Installation

```bash
git clone https://github.com/danishirfan21/Local-OCR.git
cd Local-OCR
python -m venv .venv
.venv\Scripts\activate   # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
streamlit run app.py
```

This installs and runs Fast mode only — no Paddle, no model download beyond
EasyOCR's own first-use cache. Optional PaddleOCR + table extraction: see
[PaddleOCR](#paddleocr-optional-legacy-local-heavy-backend) above. Optional
Deep Analyze: see [Deep Analyze](#deep-analyze-gemini-byok) above.
Platform-specific setup notes are in [Setup.md](Setup.md).

**CLI** (via `pyproject.toml`'s `local-lens` entry point, or `python -m
local_lens.cli`):

```bash
pip install -e .
local-lens doctor
local-lens extract screenshot.png --mode fast
```

## Testing

```bash
pip install -r requirements.txt   # includes pytest
pytest tests/ -v
```

All engine/extractor dependencies are mocked (`FakeEngine`,
`_FailingTableExtractor`/`_WorkingTableExtractor` in `tests/test_engines.py`)
— the suite runs with no model downloads.

## Benchmarks

```bash
python benchmarks/run_benchmark.py
```

See [benchmarks/README.md](benchmarks/README.md) for the corpus, metrics,
and known limitations (Urdu fixture rendering quality in particular).

## License

MIT License.
