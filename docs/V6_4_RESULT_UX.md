# V6.4: compact result popup, content-aware presentation, Deep Analyze

Builds on `docs/V6_3_CAPTURE.md`'s capture workflow. This phase replaces
the main-window-centric result flow with a dedicated, compact popup --
the actual flagship interaction Local Lens has been building toward:

```
Ctrl+Shift+Space -> select region -> popup appears -> Fast result -> Copy / Deep Analyze
```

## Popup architecture

```
desktop/result/
  positioning.py     pure placement math (global coordinates, unlike capture/geometry.py)
  window.py            ResultWindow + ContentPane (the actual popup)
  deep_worker.py         DeepWorker -- production Gemini request, off the GUI thread
  privacy_dialog.py       one-per-session Deep consent dialog
```

`ResultWindow` (`desktop/result/window.py`) is a compact, frameless-free
(it keeps a native title bar with a real close button -- simpler than
custom chrome, still reads as compact) `QWidget`, always-on-top while
visible, reused across captures rather than stacked (item 38: a new
capture replaces the previous result via `show_loading()`, which also
clears any stale Deep tab from the prior capture).

`MainWindow` is now secondary (item 35): Open Image, Settings access, and
a development fallback. **Captured-region results never touch it** --
capture goes straight from `CaptureController` to `ResultWindow`.

## Why tabs instead of one static button row

The original mockup showed one row of `Copy / Save / Deep Analyze`
buttons. Once Deep Analyze exists as a *second* result the user can
request without losing the first, a single button row can't express "here
are two different results, each with content-appropriate actions" -- a
table's actions (Copy Table/Markdown) aren't the same as plain text's
(Copy). `ResultWindow` uses a `QTabWidget` with a "Fast" tab (always
present) and a "Deep" tab (added only once a Deep result exists); each
tab is a `ContentPane` with its own content-aware view and matching
buttons. The Deep Analyze button itself stays outside the tabs, at the
bottom, since it's the action that *creates* the Deep tab, not something
that belongs inside either result.

## Content-aware presentation (`ContentPane`)

One reusable widget, not one application per content type (item 13). Uses
`result.metadata["content_type"]` (the existing classifier, unchanged):

- **Text**: editable, selectable `QPlainTextEdit`, preserves line breaks,
  Copy button. Editable specifically per the task's wording -- unlike
  V6.1's read-only main-window view, the popup's plain-text result can be
  lightly edited before copying.
- **Code**: read-only, monospace (`QFontDatabase.SystemFont.FixedFont`),
  no line wrapping, Copy Code. No reformatting, no explanation, no
  correction -- extraction means extraction (item 15).
- **Table**: a real `QTableWidget`, Copy Table (tab-separated, pastes
  cleanly into spreadsheets), Copy Markdown (reuses
  `local_lens.export.export_table_markdown`), Save (CSV via
  `export_table_csv`, or Markdown -- both existing, tested export
  functions, not reimplemented). **Fast mode never fabricates a table
  from a weak classifier hint** -- if `content_type == "table"` but
  `result.tables` is empty (the normal case now that Paddle's table
  extractor is unavailable on this machine), the pane shows a plain-text
  view with an honest hint: "Table-like content detected. Deep Analyze
  can often preserve rows and columns better than Fast OCR." (item 16).
- **Deep table fallback**: production Gemini responses don't populate
  `DocumentResult.tables` either (only the local Paddle pipeline does --
  same fact the benchmark phase discovered and worked around). When a
  Deep result's `content_type == "table"`, `ContentPane` falls back to
  `local_lens.deep_analysis.deep_metrics.parse_markdown_table()` -- the
  same parser the Round 1 benchmark built and validated against real
  Gemini responses -- to build a display-only `TableResult` from the
  reply's markdown, never mutating the actual `DocumentResult`.

## Deep Analyze integration

`DeepWorker` (`desktop/result/deep_worker.py`) is a `QThread`, structurally
identical to `OCRWorker`: builds `build_production_gemini_provider(env=
load_env())` (the exact same `LOCAL_LENS_GEMINI_API_KEY` path the CLI and
Streamlit app use -- **never** the benchmark's
`LOCAL_LENS_BENCHMARK_GEMINI_API_KEY`), runs the same `OCRService.process`
pipeline, and emits `succeeded`/`failed`. Error mapping
(`deep_error_message`) mirrors `app.py`'s Streamlit implementation exactly
(auth/rate-limit/timeout/generic), duplicated intentionally rather than
imported cross-module, since the two UIs shouldn't share a private helper
just to avoid four lines of duplication.

**Sequence**: capture -> Fast result shown immediately -> user clicks Deep
Analyze -> (first time this session) privacy dialog -> Gemini request on a
background thread -> Deep tab appears alongside Fast, which is never
overwritten or removed (item 23). A Deep failure shows the specific error
in the status line and leaves the Fast tab completely untouched
(`test_deep_error_preserves_fast_result_and_reenables_button`).

**The Deep button's enabled state** reflects live configuration
(`production_gemini_configured(load_env())`, checked when the Fast result
lands, no key ever displayed); when disabled, its tooltip says "Set a
Gemini API key in Settings to enable Deep Analyze."

## Privacy

Session-only acknowledgment (`DesktopApplication._deep_privacy_acknowledged`,
a plain Python `bool`, not persisted to `QSettings` -- item 20). The
dialog text is exactly:

> Deep Analyze sends this selected image to Google's Gemini API.
>
> Fast OCR stays on your device.
>
> Google's free-tier API may use submitted content to improve products and
> may involve human review.

Buttons: Cancel / Analyze remotely. Declining makes zero network calls and
leaves `_deep_privacy_acknowledged` false, so the dialog reappears on the
next Deep click. Accepting sets it true for the remaining life of the
process only. Verified: `test_capture_and_fast_ocr_make_zero_network_calls_until_deep_clicked`
(a real `urllib.request.urlopen`-forbidding fixture wraps the entire
capture -> Fast OCR -> popup-shown flow) and
`test_privacy_dialog_only_shown_once_per_session` (two Deep clicks, one
dialog construction).

## The image stays in memory only as long as its popup is open

`DesktopApplication._current_image_bytes` holds the cropped PNG bytes
(already produced entirely in memory by the V6.3 capture pipeline) so Deep
Analyze can reuse the exact same crop Fast OCR used, without a second
capture or any disk write. It's overwritten by the next capture's bytes
when a new one starts (`show_loading()`); nothing is ever persisted (no
history, per this phase's explicit scope limits).

## OCR/Deep reentrancy

`DesktopApplication._is_ocr_busy()` checks `MainWindow`'s Open-Image
worker, the popup's Fast worker, *and* the Deep worker -- a new capture
is refused (logged, silently ignored -- item 40's "keep implementation
simple") while any of the three is running. This is a slightly more
conservative rule than the task's "Fast capture may optionally proceed
if cleanly isolated" -- chosen because `ResultWindow` is a single reused
instance, not one-popup-per-capture, so a Fast capture racing an
in-flight Deep request on the *same* window would corrupt which tab is
being written to.

## Positioning (real bug found and fixed)

`place_popup()` (`desktop/result/positioning.py`) tries below the
selection first, then above, then falls back to centering on the target
monitor -- always clamped to the monitor's bounds. Unlike
`desktop/capture/geometry.py` (deliberately monitor-local, global origin
never enters the math), this genuinely needs **global** desktop
coordinates, including a negative one for a monitor left of/above the
primary -- `CaptureController` now threads the overlay's
`screen_geometry` (global) through a new `CaptureResult` dataclass
(`png_bytes`, `selection_global`, `monitor_global`) instead of emitting
bare bytes. Verified live: popup appeared just below the selection,
fully on-screen, on this machine's single monitor; negative-origin and
edge-clamping behavior is covered by unit tests only (no second monitor
to verify against live).

## Startup OCR warm-up (measured, not assumed)

A bounded experiment (three sequential Fast OCR calls on the same tiny
fixture, same process) measured:

```
call 1 (cold): 9.9s
call 2 (warm): 0.24s
call 3 (warm): 0.28s
```

**Cold EasyOCR reader construction dominates completely** -- inference
itself is fast. `desktop/warmup_worker.py`'s `WarmupWorker` (a `QThread`)
now runs `desktop/ocr_service_factory.py`'s new `warmup_fast_engine()`
(constructs the reader against a tiny synthetic 16x16 image, no file
dependency) in the background as soon as `DesktopApplication` starts,
before any capture. The tray tooltip reflects state
("Local Lens -- starting OCR…" -> "Local Lens -- ready") without exposing
engine internals in the UI (item 12). Warmup is best-effort: if it fails,
a real capture simply pays the cold-construction cost itself, same as
before this phase -- no user-visible error path needed since the outcome
is "a bit slower," not "broken."

**Skippable for tests** (`DesktopApplication(..., enable_warmup=False)`)
-- an earlier version of this phase started the real warmup unconditionally,
which meant every controller-construction test triggered a real ~10s
EasyOCR cold-load in the background; the full desktop suite went from
~1s to ~40s before this was caught and fixed.

## Two real bugs found and fixed during live verification

1. **First capture right after app startup could still leak `MainWindow`
   content**, even with V6.3's 80ms compositor-settle delay -- the main
   window's very first paint hadn't fully settled by the time `hide()` +
   80ms elapsed. Raised to 150ms (`desktop/capture/controller.py`'s
   `_HIDE_SETTLE_MS`); still comfortably under what reads as sluggish
   (see latency numbers below).
2. **A previous capture's `ResultWindow` was never hidden before a new
   capture** -- `hide_windows` only hid `MainWindow`. A live test captured
   a *second* time while the first result popup was still on screen, and
   its own text ("Local Lens", "Read locally 0.5s") leaked into the new
   screenshot. Fixed by `DesktopApplication._hide_all_windows()`, which
   hides both windows before every capture.

Both were re-verified live afterward: a capture immediately at startup,
and a second capture taken while the first result popup was still open,
both produced clean, uncontaminated results.

## Manual live verification (this Windows machine)

Sequence: display `short_ui_save.png` full-screen (frameless, exact
pixmap size) -> real hotkey trigger -> real overlay -> real drag -> real
crop -> real Fast OCR, twice (to measure cold vs. warm) -> Copy -> verify
clipboard -> swap the displayed image to `table_simple.png` -> capture
again.

**Results**: cold capture returned exactly `'Save'` (12.3s, matching the
bounded-experiment cold number); a second, warm capture also returned
exactly `'Save'` in 0.63s; clipboard after Copy exactly `'Save'`; the
`table_simple.png` capture cleanly extracted `'Product Quantity Price /
Keyboard 2 50 / Mouse 25'` (this particular capture's classifier happened
to call it plain text rather than "table" -- not a bug, just this input
didn't trigger the table heuristic; the table-hint path itself is
separately unit-tested against a result whose `content_type` is
`"table"`). No screenshot files existed anywhere afterward.

**Latency observed**: overlay visible ~0.16-0.23s after the hotkey signal
(includes the 150ms settle delay); OCR start is effectively immediate
after mouse release (crop + PNG encode + thread spawn, unchanged from
V6.3). Cold OCR: ~12.3-12.7s (EasyOCR reader construction, matching the
bounded experiment). Warm OCR: ~0.5-0.6s. This is the strongest possible
argument for the warmup worker added this phase -- once warm, the popup
feels close to instant; cold, it's a genuine multi-second wait the
loading state ("Reading selection…") exists specifically to cover.

## Tests

70 new tests across `tests/test_result_positioning.py` (placement math:
below/above/centered fallback, horizontal clamping, negative monitor
origin, a popup exactly the size of the monitor),
`tests/test_result_window.py` (loading/Fast/Deep/error states, all three
content types including the Fast-mode table-hint vs. Deep markdown-table-
fallback distinction, clipboard copy for text/code/table, file export for
text and table via the real export functions, mixed Urdu/English text
preserved exactly with no forced global RTL layout, Escape-hides-not-
closes), `tests/test_deep_worker.py` (error-message mapping for every
documented failure mode, unconfigured-key failure path with the real
`build_production_gemini_provider` forced to `None` so no real credential
is ever consulted), and extensions to `tests/test_app_controller.py`
(hotkey/tray Capture both land on the popup with `MainWindow` no longer
involved, OCR/Deep reentrancy across all three workers, the full privacy-
dialog accept/decline/once-per-session flow with a mocked `DeepWorker`,
and a `urllib.request.urlopen`-forbidding zero-network proof for the
entire capture -> Fast OCR path). All skip cleanly via
`pytest.importorskip` when PySide6 isn't installed.

## Known limitations

- Multi-monitor popup placement is unit-tested only (single monitor on
  this machine, same caveat as V6.3's capture).
- No result history -- dismissing a popup and starting a new capture
  discards the previous result entirely (explicitly out of scope).
- The table hint's local classifier is a heuristic; it will sometimes
  call a real table "text" (as the live table-fixture capture did) or
  vice versa -- this is existing, unchanged `classify()` behavior, not
  something this phase tuned.
- Auto-copy was evaluated per the task's "research only" instruction and
  not implemented -- worth a future Settings toggle, not default-on.
- The privacy acknowledgment resets on every app restart by design
  (session-only); no "remember forever" option exists yet.
