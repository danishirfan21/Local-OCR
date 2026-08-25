# V6.2: background utility -- tray, global hotkey, Settings

Builds on `docs/V6_DESKTOP_FRAMEWORK_DECISION.md`'s PySide6 shell (V6.1:
Open Image -> Fast OCR -> result -> Copy). This phase turns that shell into
a background utility: a system tray icon, a global Windows hotkey, close-
to-tray window behavior, and a minimal Settings dialog. Region capture
itself (the actual point of a screenshot utility) is explicitly deferred
to V6.3 -- V6.2 only proves the lifecycle plumbing a real capture feature
will need.

## Package layout

```
desktop/
  app_controller.py   DesktopApplication -- owns everything, decides what
                       each tray/hotkey action means
  tray.py              TrayController -- QSystemTrayIcon + menu, signals only
  hotkey/
    shortcut.py         pure text <-> Win32 RegisterHotKey parameter mapping
    win32_adapter.py     the actual RegisterHotKey/UnregisterHotKey calls +
                          QAbstractNativeEventFilter bridge (Windows-only)
    manager.py            platform-abstracted wrapper around the adapter
  settings.py           AppSettings -- QSettings wrapper, UI prefs only
  settings_dialog.py     Settings window (shortcut editor + Gemini status)
  icon.py                a generated placeholder tray/window icon
  logging_setup.py       lightweight event-only logging
  main_window.py         (V6.1, extended) + hide_to_tray_enabled/closeEvent
  main.py                entry point, now builds DesktopApplication
```

## Application controller

`DesktopApplication` (`desktop/app_controller.py`) is the single lifecycle
owner -- `MainWindow` stays a plain result-display widget (plus the one
piece of window-level behavior it has to own itself: hide-vs-close, since
that's a `closeEvent` override, not something a separate controller object
can intercept). Everything else -- what "Capture" means, what Quit does,
hotkey registration, Settings -- lives in the controller, not scattered
across widgets. This was a deliberate reaction to V6.1's `MainWindow`
already starting to accumulate responsibilities it shouldn't grow further.

## Tray

`QSystemTrayIcon` via `TrayController` (`desktop/tray.py`). Menu: Capture /
Open Local Lens / Settings / Quit, plus click/double-click on the tray
icon itself also opens the window (a small nicety on top of the required
menu items). The controller connects each menu action to what it actually
does:

- **Capture** (V6.2): no region-selection logic exists yet, so this just
  brings Local Lens to the front and logs "capture requested -- region
  capture not implemented until V6.3." This proves the tray-action wiring
  now so V6.3 only has to swap in real capture logic behind the same
  signal, not build new plumbing.
- **Open Local Lens**: shows/restores/raises/activates the main window.
- **Settings**: opens `SettingsDialog`.
- **Quit**: the only path that actually terminates the app (see
  "Shutdown" below).

The tray icon is a small placeholder drawn at runtime (`desktop/icon.py`,
a `QPainter`-rendered circle+letter) rather than an external asset file --
no icon-pack download, no branding decision made prematurely, and a
missing/corrupt icon file can never crash startup because there is no
file to be missing.

## Window close behavior

`MainWindow.hide_to_tray_enabled` (default `False`, set `True` by the
controller once tray mode is active) controls `closeEvent`: when `True`,
the X button hides the window instead of closing it
(`event.ignore(); self.hide()`); when `False` (only during the
controller's own `quit()`), the close proceeds normally. `QApplication`'s
`quitOnLastWindowClosed` is also explicitly set `False` at startup, since
the app's actual lifecycle owner is the tray icon, not "is any window
open" -- otherwise hiding the last window via the X button could still
trigger an implicit app-wide quit depending on Qt's bookkeeping.

## Global hotkey

Default: **`Ctrl+Shift+Space`** -- chosen specifically to avoid
`Win+Shift+S` (Windows' own Snipping Tool) and common IDE/browser
bindings. Stored in exactly one place: `desktop/hotkey/shortcut.py`'s
`DEFAULT_SHORTCUT`.

### Why `ctypes` + `RegisterHotKey`, not a third-party library

No new dependency. `keyboard` and `pynput` install global low-level
keyboard hooks (broader capability than needed, worse AV-flagging
profile); `pywin32` is a large dependency for what's really one Win32 API
pair. `ctypes` is stdlib and `user32.RegisterHotKey`/`UnregisterHotKey`
are exactly the right shape for "register one specific key combination,
get told when it fires."

### Architecture

```
Windows WM_HOTKEY
  -> QAbstractNativeEventFilter subclass (desktop/hotkey/win32_adapter.py)
  -> GlobalHotkeyManager.triggered signal (desktop/hotkey/manager.py)
  -> DesktopApplication._on_hotkey_triggered (desktop/app_controller.py)
```

No polling, no busy loop. `RegisterHotKey(hwnd=None, ...)` registers the
hotkey against the *calling thread's* message queue rather than a specific
window handle; Qt's Windows event dispatcher (`QEventDispatcherWin32`)
pumps the whole thread message queue regardless, so the native event
filter still sees the resulting `WM_HOTKEY` message. This avoids needing
to dedicate a window purely to catch one message.

### Three-layer split (for testability)

1. `hotkey/shortcut.py` -- pure text parsing (`"Ctrl+Shift+Space"` ->
   Win32 modifier flags + virtual-key code), zero Windows API calls, zero
   platform check. Unit-tested directly
   (`tests/test_hotkey_shortcut.py`): the three example sequences from the
   task (`Ctrl+Shift+Space`, `Ctrl+Alt+L`, `Alt+Shift+L`), function keys,
   digits, the Windows/Meta modifier, and rejection of empty input, a bare
   key with no modifier, unparseable text, and multi-key chords.
2. `hotkey/win32_adapter.py` -- the actual `ctypes.windll.user32` calls
   and the `QAbstractNativeEventFilter` subclass. Only ever imported when
   `sys.platform == "win32"` (see `manager.py`) -- CI runs on
   `ubuntu-latest`, so nothing outside that guarded import path may touch
   it, and it has no test file of its own (would need a real Windows
   message loop; exercised instead by the live manual verification below).
3. `hotkey/manager.py` -- `GlobalHotkeyManager`, the platform-abstracted
   wrapper the controller actually talks to. On non-Windows platforms (or
   when a fake `adapter` is injected, as every test does) it never touches
   `ctypes.windll` at all. Lifecycle logic (register/unregister,
   re-registration-on-change, failure signal emission) is fully unit-
   tested (`tests/test_hotkey_manager.py`) against a `FakeAdapter`, per
   item 26/28's "mock native registration for lifecycle tests, do not make
   CI depend on real desktop hotkeys."

### Registration failure

If Windows rejects the hotkey (another app already owns that combination),
`GlobalHotkeyManager.registration_failed` fires with a specific message;
the controller shows it on `MainWindow`'s (normally hidden)
`shortcut_status_label` rather than crashing or silently doing nothing.
Tray and the rest of the UI stay fully functional. Changing the shortcut
in Settings to something that also fails to register **restores the
previously-working shortcut** rather than leaving nothing registered
(`DesktopApplication._on_settings_requested`, tested in
`tests/test_app_controller.py`).

### Unregistration

`GlobalHotkeyManager.unregister()` -> `Win32HotkeyAdapter.unregister()` ->
`UnregisterHotKey`, called on: re-registration (a new `register()` call
always unregisters first), and `DesktopApplication.quit()`. No stale
registration is left behind in either the normal shortcut-change path or
on app exit.

## Settings

Minimal, per the task's explicit "do not add fifteen future toggles yet":

- **Global shortcut**: a `QKeySequenceEdit` (captures the key combination
  directly rather than requiring the user to type `"Ctrl+Shift+Space"` by
  hand), live-validated against `hotkey/shortcut.py`'s `parse_shortcut()`
  on every change -- the OK button disables and a message explains why
  whenever the current selection isn't a valid single-combination,
  modifier-bearing, supported-key shortcut.
- **Deep Analyze status**: "Gemini configured" / "Gemini not configured",
  read via the existing `local_lens.deep_analysis.production
  .production_gemini_configured()` + `local_lens.env_file.load_env()` --
  the same functions the CLI's `doctor`/`providers` commands use. Never
  displays the key value itself.
- **Privacy reminder**: static text, "Fast stays on-device. Deep sends the
  selected image to Gemini." -- no live Gemini call happens from this
  dialog.

### Storage boundary (settings vs. secrets)

`AppSettings` (`desktop/settings.py`) wraps `QSettings("Local Lens",
"Local Lens")` -- on Windows this lands under
`HKEY_CURRENT_USER\Software\Local Lens\Local Lens`. It stores **only** UI
preferences (today: the shortcut string; window geometry is a natural
future addition, not implemented yet). It must never hold
`LOCAL_LENS_GEMINI_API_KEY` or any other secret -- production credential
handling is completely unchanged from V5
(`local_lens/deep_analysis/production.py` + `local_lens/env_file.py`,
real env -> project `.env` -> not configured). `docs
/V6_DESKTOP_FRAMEWORK_DECISION.md`'s credential-boundary section already
flagged Windows Credential Manager as the eventual production-packaging
target for the key itself -- still not implemented, still not V6.2's job.

Every test that touches `AppSettings` passes an explicit `backing=
QSettings(<tmp_path>/settings.ini, QSettings.IniFormat)` so the test suite
never reads or writes the real registry path
(`tests/test_desktop_settings.py`, `tests/test_app_controller.py`).

## Application identity

`QApplication.setApplicationName("Local Lens")` /
`setOrganizationName("Local Lens")`, set once in `desktop/main.py` before
constructing `DesktopApplication` -- this is what makes the `QSettings`
path above predictable (`QSettings()` with no explicit backing reads the
org/app name from the `QApplication` instance).

## Shutdown lifecycle (`DesktopApplication.quit`)

In order: unregister the hotkey -> if an OCR worker is currently running,
request interruption and wait up to 3s for it to finish (not a forceful
kill -- `QThread.wait()` blocks until natural completion or the timeout;
EasyOCR itself doesn't check `isInterruptionRequested()` mid-inference, so
in practice this is a bounded wait, not a hard cancel, which is the
"handle safely, keep this simple" behavior the task asked for rather than
introducing real cancellation support) -> hide the tray icon -> disable
`hide_to_tray_enabled` and close the main window for real -> `app.quit()`.
Verified live (see below) that no orphan `python.exe` process remains
after this path runs.

## Logging

`desktop/logging_setup.py`, one named logger (`local_lens.desktop`).
Logs only event names: startup, tray available/unavailable, hotkey
registered/registration failed/triggered, capture requested, shutdown.
Never logs the Gemini key, `.env` contents, OCR text, or image/screenshot
bytes -- callers only ever pass short, generic status strings.

## Manual verification (live, on this Windows machine)

Run via a short script that constructed `DesktopApplication` on the real
(non-offscreen) Qt platform and auto-quit after 500ms:

- Tray icon actually became visible (`tray_icon.isVisible()` -> `True`
  once shown -- confirms real `QSystemTrayIcon.isSystemTrayAvailable()`
  on this machine, distinct from the offscreen-platform unit tests where
  it's correctly `False`).
- `GlobalHotkeyManager.is_supported` -> `True` (real Win32 adapter
  constructed).
- The real default shortcut (`Ctrl+Shift+Space`) registered successfully
  with **live** Windows (`RegisterHotKey` returned success, no conflict on
  this machine) -- `shortcut_status_label` correctly stayed hidden (no
  warning).
- `main_window.close()` hid the window rather than exiting the process
  (`isVisible()` -> `False`, process still alive) -- close-to-tray
  confirmed live, not just via the unit tests' offscreen `QWidget.close()`
  call.
- Reopening via the controller's `_show_main_window()` (the same path the
  tray's "Open Local Lens" and the hotkey handler both call) correctly
  restored visibility.
- `controller.quit()` logged `shutdown`, and the Python process exited
  cleanly -- confirmed via `ps` immediately afterward that no orphaned
  process remained.

Not verified live in this pass (would require an actual interactive
desktop session watched by a human, not a scripted headless run): the
Settings dialog's on-screen key-capture interaction, and a genuine
already-claimed-shortcut conflict (there was nothing on this dev machine
already bound to the default). Both are covered by unit tests instead
(`tests/test_settings_dialog.py`'s programmatic `setKeySequence()` calls,
and `tests/test_hotkey_manager.py`/`test_app_controller.py`'s
failure-path tests using a `FakeAdapter` configured to reject
registration).

## Known limitations

- Only one hotkey slot exists (`Win32HotkeyAdapter._HOTKEY_ID = 1`) --
  fine for V6.2's single "Capture" action; would need an id-per-action
  scheme if a future version adds more than one global shortcut.
- Non-Windows platforms: `GlobalHotkeyManager.is_supported` is `False`
  and registration always fails with a clear message; there is no macOS/
  Linux hotkey implementation (out of scope, this project is
  Windows-first per its own stated scope).
- "Capture" is a placeholder in V6.2 -- it does not capture anything yet,
  intentionally (V6.3's job).
- No "start minimized" setting yet (task explicitly deferred this).
- No window-geometry persistence yet (only the shortcut is persisted
  today; `AppSettings` is structured to add more keys later without
  changing its call sites).
