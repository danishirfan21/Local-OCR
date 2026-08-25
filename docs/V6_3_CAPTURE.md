# V6.3: screenshot capture + region selection

Builds on `docs/V6_2_TRAY_HOTKEY.md`'s background utility (tray, global
hotkey, close-to-tray, Settings). This phase implements the actual
screenshot workflow -- the central Local Lens interaction:

```
Ctrl+Shift+Space -> screen dims -> drag a rectangle -> Fast OCR -> result -> Copy
```

Both the global hotkey and the tray's "Capture" action now trigger this
workflow (previously placeholders that just showed the main window).

## Package layout

```
desktop/capture/
  geometry.py        pure coordinate math -- normalization, logical <->
                      physical DPI conversion, bounds clamping, minimum-
                      size rejection. No Qt widgets, no Windows API.
  screen_capture.py    monitor-under-cursor selection + QScreen.grabWindow
  overlay.py            CaptureOverlay -- the fullscreen selection widget
  image_convert.py       QImage/QPixmap -> PNG bytes (lossless)
  controller.py           CaptureController -- orchestrates one capture
```

## Why `QScreen.grabWindow`, not `mss`

Evaluated per the task's explicit "add another dependency only if Qt's own
capture path proves insufficient." It didn't prove insufficient:
`QGuiApplication.screenAt()` + `QScreen.grabWindow(0)` handled monitor
selection and screen capture correctly in live testing on this machine,
including the real 125%-DPI case (see "DPI handling" below). No new
dependency was added this phase.

## Capture flow

```
hotkey / tray Capture
  -> CaptureController.start()
      -> hide Local Lens windows
      -> short settle delay (see "known issue" below)
      -> screen_under_cursor() -> QScreen.grabWindow(0)
      -> CaptureOverlay shown fullscreen on that monitor
      -> user drags a rectangle (or presses Escape)
      -> overlay emits selection_made(PixelRect) or cancelled
  -> controller crops the screenshot, converts to PNG bytes
  -> MainWindow shown, run_ocr(png_bytes) -- same entry point Open Image uses
```

`DesktopApplication._start_capture()` (`desktop/app_controller.py`) is the
single entry point both the hotkey and tray's Capture action call --
exactly one capture workflow, not two parallel implementations.

## Monitor selection

`screen_under_cursor()` prefers the monitor the mouse is currently on
(`QGuiApplication.screenAt(QCursor.pos())`), falling back to the primary
screen if that ever returns `None` (e.g. a momentary gap between
monitors). This machine has a single monitor, so only the fallback path
and the coordinate math for a hypothetical second monitor are covered by
tests rather than live-verified multi-monitor behavior -- see "Known
limitations."

## Region overlay

`CaptureOverlay` (`desktop/capture/overlay.py`): frameless, translucent,
always-on-top (`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
Qt.Tool`), sized to exactly the target monitor's logical geometry,
crosshair cursor. Renders the captured screenshot as its background,
dimmed (`alpha 120/255`) everywhere except the current drag rectangle,
which stays undimmed with a thin colored border and a live `width x
height` label. No toolbar, no settings -- purely a snip-and-go
interaction, per the task's explicit scope.

- **Selection**: mouse press starts the drag, mouse move updates it live,
  mouse release confirms -- any drag direction (top-left-to-bottom-right
  or any of the other three) is normalized correctly
  (`geometry.normalize_rect`).
- **Minimum size**: selections under 10x10 (logical) pixels are treated as
  an accidental click and ignored -- the overlay stays open rather than
  emitting a near-empty crop.
- **Escape**: cancels immediately, no OCR, no screenshot retained.
- **Reentrancy**: `CaptureController.start()` is a no-op if a capture is
  already active -- a second hotkey press mid-selection cannot stack a
  second overlay.

## DPI handling

Verified **empirically**, not assumed, on this machine (single monitor,
125% Windows scaling):

```
screen.geometry()            -> QRect(0, 0, 1536, 864)   logical pixels
screen.devicePixelRatio()    -> 1.25
grabWindow(0).size()         -> QSize(1920, 1080)         physical pixels
grabWindow(0).devicePixelRatio() -> 1.25
```

`QScreen.geometry()` (what the overlay is positioned/sized with, and what
mouse events report coordinates in) is **logical**; the screenshot
`QPixmap` is stored at **physical** resolution. `geometry.py`'s
`logical_to_physical()` multiplies a selection rect by the screen's
`devicePixelRatio()` before cropping
(`CaptureOverlay.crop_physical()`) -- verified both live (a real 125%
capture correctly produced a crop at the expected physical size) and via
unit tests covering 100%, 125%, and 150% mathematically (`tests
/test_capture_geometry.py`), since only one scaling mode is actually
available to test live on this laptop.

### Negative monitor origin / mixed-DPI monitors

Deliberately **not a special case** in this code. The overlay window is
created with `setGeometry(screen.geometry())`, and Qt widget mouse-event
coordinates are always local to the widget (0,0 at its own top-left) --
never global desktop coordinates. A monitor placed left of or above the
primary monitor (negative `geometry().x()`/`.y()`) therefore never enters
`geometry.py`'s functions at all; cropping only ever needs a position
within *that one monitor's own* screenshot pixmap. This invariant is
documented in `geometry.py`'s module docstring and covered by
`test_logical_to_physical_never_depends_on_a_negative_global_origin`.
Each monitor's own `devicePixelRatio()` is read fresh at capture time
(`CaptureOverlay.device_pixel_ratio = screen.devicePixelRatio()`), so a
mixed-DPI multi-monitor setup would use the correct ratio for whichever
monitor was actually captured -- not a single global assumption.

## In-memory screenshot flow (no disk writes)

`QScreen.grabWindow(0)` -> `QPixmap.copy(...)` (crop) -> `QImage.save()`
into a `QBuffer` (`desktop/capture/image_convert.py`) -> raw `bytes`.
Nothing touches disk at any point. **Verified live**: after a full real
capture, no screenshot file existed anywhere under the project directory
or the OS temp directory. PNG (lossless) was used rather than JPEG so OCR
never sees compression artifacts.

## Bridging to OCR

The PNG bytes feed directly into `MainWindow.run_ocr(image_bytes)` --
**the exact same entry point `Open Image` already used** (which reads a
file straight into `bytes`). No refactor of `OCRWorker`/`OCRService` was
needed; both workflows converge on one bytes-based interface. Fast OCR
runs automatically after a selection -- no "Fast or Deep?" prompt, per
this phase's product direction (Fast is the default, Deep stays an
explicit follow-up in a later phase).

## OCR reentrancy

If a capture is requested while a previous OCR job is still running,
`DesktopApplication._start_capture()` refuses to start a second one --
it brings the window to the front, shows "OCR already in progress --
please wait," and does not touch the capture/overlay machinery at all.
Matches the task's explicit "keep it simple" instruction over building
real EasyOCR cancellation.

## Window behavior around capture

- Before capture: `hide_windows()` (bound to `MainWindow.hide`) hides the
  main window so Local Lens doesn't capture itself.
- After a successful selection: the main window is shown/raised/activated
  and immediately starts OCR, showing "Running Fast OCR (local,
  offline)..." (unchanged from V6.1) rather than leaving the user staring
  at nothing.
- After Escape/cancel: the window is only restored if it was visible
  *before* the capture started (`_window_was_visible_before_capture`) --
  a capture triggered while Local Lens was already hidden (e.g. via the
  tray with the window previously closed-to-tray) doesn't force it back
  open just because the user changed their mind about the region.

## Known issue found and fixed during live verification

The first live test showed Local Lens's own window text ("Local Lens",
"Open Image", "Copy") leaking into the captured screenshot, even though
`hide_windows()` was called before the grab. Root cause: a zero-delay
`QTimer.singleShot(0, ...)` is one Qt event-loop turn, which is not the
same guarantee as "the Windows compositor (DWM) has produced a new frame
without the now-hidden window in it" -- DWM composites asynchronously and
can lag a hide by a few milliseconds. Fixed by changing the settle delay
from 0ms to a short, fixed `_HIDE_SETTLE_MS = 80` (`desktop/capture
/controller.py`) -- re-verified live afterward with a clean capture
(exact expected text, no leaked UI). This is a bounded, fixed delay, not
the "arbitrary multi-second sleep" the task explicitly ruled out, and it
does not make the interaction feel slower in practice (see latency
numbers below).

## Manual live verification (this Windows machine)

Displayed the existing `benchmarks/samples/short_ui/short_ui_save.png`
fixture full-screen (frameless, exact pixmap size, so its
`frameGeometry()` gave a precise, non-guessed drag target), then drove
the real app end-to-end: simulated hotkey trigger -> real overlay shown on
the real monitor -> real screenshot grab -> a real mouse drag around the
displayed image -> real crop -> real Fast OCR (EasyOCR, CPU).

**Result: `'Save'`** -- exactly the expected text, confirming the entire
in-memory pipeline (grab -> crop at the correct DPI-scaled coordinates ->
PNG encode -> `OCRService.process()` -> EasyOCR) is correct end-to-end,
not just unit-tested in isolation.

**Latency observed** (informal, not benchmarked): overlay visible ~0.23s
after the hotkey signal fires (includes the 80ms settle delay plus the
real screen grab); OCR start after mouse release: ~0.04s (near-instant --
crop + PNG encode + thread spawn). EasyOCR's own inference time (not
part of this phase's scope to optimize) was ~13-14s, consistent with the
CPU-only cold/warm timing already documented for V6.1.

**Verified no screenshot artifact remained** anywhere under the project
directory or the OS temp directory after the capture completed.

## Tests

- `tests/test_capture_geometry.py` -- pure coordinate math: rect
  normalization in all four drag directions, DPI conversion at 100%/125%/
  150%, the negative-origin invariant, bounds clamping, minimum-size
  rejection.
- `tests/test_capture_overlay.py` -- offscreen Qt: frameless/translucent/
  correctly-sized construction, crosshair cursor, drag-and-release
  emitting `selection_made` with the right rect (both drag directions),
  tiny-click rejection, Escape emitting `cancelled`, DPI-scaled cropping.
- `tests/test_image_convert.py` -- width/height/pixel-value round-trip
  through PNG bytes, no channel swap, confirms lossless PNG output (not
  JPEG).
- `tests/test_capture_controller.py` -- mocked `screen_under_cursor`/
  `grab_screen` (no real screen capture in CI): hide-then-overlay flow,
  reentrancy (second `start()` while active is a no-op), selection
  produces valid PNG bytes and tears down the overlay, cancellation tears
  down and emits `cancelled`.
- `tests/test_app_controller.py` (extended) -- hotkey and tray Capture
  both start the same workflow and hide the window; a completed capture
  shows the window and calls `run_ocr` with real PNG bytes (mocked, no
  real EasyOCR run); OCR-in-progress reentrancy is respected; cancellation
  only restores window visibility if it was visible beforehand.

All desktop tests continue to skip cleanly via `pytest.importorskip`
when PySide6 isn't installed (CI stays lightweight-only).

## Known limitations

- Multi-monitor is structurally supported (each monitor's own geometry
  and `devicePixelRatio()` are read fresh, no global assumption) but not
  live-verified -- this machine has one monitor. Covered by unit tests
  for the coordinate math only.
- Only "monitor under the cursor" is implemented for selection; no
  explicit monitor picker if that heuristic guesses wrong.
- No screenshot annotation/editing (crop-only, matches the milestone's
  scope).
- Deep Analyze is not wired into the capture flow yet (Fast only, by
  design for this phase -- V6.4 territory per the task).
- The overlay's size/position label is a plain `QPainter.drawText` call,
  not styled further -- functionality-first per the task's explicit
  "functionality first" instruction for this phase.
