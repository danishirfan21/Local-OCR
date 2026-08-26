# V6.8 -- Self-Contained Offline Portable Release Candidate

HEAD at start of this milestone: `f2180777cfa38fe6fb4814225c47275db27e7ee3` (V6.7).

## Objective

Prove: `download ZIP -> extract -> launch LocalLens.exe -> no Python install
-> no ~/.EasyOCR cache -> no model download -> Fast OCR Ready ->
Ctrl+Shift+Space -> select text -> OCR -> Copy`.

V6.7 proved a portable build in general but still depended on the user's
own `~/.EasyOCR/model` cache. V6.8's job was narrower and harder: bundle
the three EasyOCR model files *inside* the PyInstaller build so a machine
that has never run EasyOCR at all still gets working Fast OCR.

## 1. Source-state verification (before any change)

- HEAD `f218077`, working tree clean, `origin/main` in sync (no ahead/behind).
- `pytest -q`: 475 passed, 1 skipped (matches expectation).
- `pip show paddlepaddle paddleocr paddlex`: none installed.
- `.env` confirmed still covered by `.gitignore`.
- V6.6 (`dist/LocalLens-v6.6-known-good`) and V6.7 (`dist/LocalLens-v6.7-test`
  + `dist/LocalLens-portable-v6.7.zip`) builds present and untouched
  throughout this milestone -- preserved as rollback.
- The three EasyOCR model files present in `~/.EasyOCR/model`, unchanged.
- Free space: C: ~9.4 GB, D: ~640 GB (corrects an earlier misread of a
  space-padded `wmic` column as ~97 GB -- the real number, confirmed via
  `Get-PSDrive`, is ~9.4 GB. This matters because C: is off-limits for
  packaging and had far less headroom than previously assumed.)

## 2. Required EasyOCR files and what each is for

| File | Size | Purpose |
|---|---|---|
| `craft_mlt_25k.pth` | 83.15 MB | **CRAFT** (Character Region Awareness For Text detection) -- locates *where* text is in an image. Detection only, no character recognition. |
| `english_g2.pth` | 14.44 MB | EasyOCR's English recognition model (2nd generation). Recognizes Latin-script characters inside CRAFT's detected regions. |
| `arabic.pth` | 205.42 MB | EasyOCR's Arabic-script recognition model. Recognizes Arabic-script characters (used for both Arabic and Urdu) inside CRAFT's detected regions -- the largest of the three by far. |

Total: 303.01 MB on disk (299.16 MB by EasyOCR's own 1000-based MB
convention).

### SHA-256 (computed from this project's own `~/.EasyOCR/model` cache)

```
craft_mlt_25k.pth  4a5efbfb48b4081100544e75e1e2b57f8de3d84f213004b14b85fd4b3748db17
english_g2.pth     e2272681d9d67a04e2dff396b6e95077bc19001f8f6d3593c307b9852e1c29e8
arabic.pth         2a9afd42c374deb98aed0b53c9b77d75e1d00d4e0501f3b0276c54190c89b1a8
```

These are the values baked into `packaging/validate_release_models.py`'s
`REQUIRED_MODEL_HASHES` and are what every release build is validated
against before bundling.

## 3. Redistribution / licensing (re-verified authoritatively via GitHub API)

| Project | License | Verified via |
|---|---|---|
| EasyOCR (JaidedAI/EasyOCR) | Apache License 2.0 | `gh api repos/JaidedAI/EasyOCR/license` -> `spdx_id: Apache-2.0` |
| CRAFT-pytorch (clovaai/CRAFT-pytorch) | MIT | `gh api repos/clovaai/CRAFT-pytorch/license` -> `spdx_id: MIT`, copyright NAVER Corp. 2019-present |

Both licenses permit redistribution, including in binary/object form.
Apache-2.0 requires retaining copyright/license/attribution notices (and
a NOTICE file's contents, if one exists -- EasyOCR's repository does not
ship one, confirmed via a 404 on `contents/NOTICE`). MIT requires
retaining the copyright + permission notice. No unsupported legal
conclusions are asserted beyond that. Full texts and attributions are
recorded in [`THIRD_PARTY_NOTICES.txt`](../THIRD_PARTY_NOTICES.txt),
which is included in the git-tracked source tree (not the release ZIP is
not currently populated automatically -- see "Remaining release issues"
below).

## 4. Release model staging

Staged at `D:\LocalLensReleaseModels\` by copying (never downloading) the
three files from `~/.EasyOCR/model`. Copy verified byte-identical via a
second SHA-256 pass matching the source hashes exactly. This directory
lives entirely outside the git repository (`D:\`, not `D:\Local OCR\`),
and `.gitignore` additionally guards against any stray `.pth`/`.zip`
file or a `LocalLensReleaseModels/`/`LocalLensFreshProfile/` directory
ever being staged *inside* the repo by mistake.

## 5. Release input validator

[`packaging/validate_release_models.py`](../packaging/validate_release_models.py)
(`validate_release_model_dir(path) -> list[str]`, raises
`ReleaseModelValidationError` on any problem): checks all three required
files exist, each SHA-256 matches, and no unexpected `.pth` file is
present. Never downloads anything -- pure local file I/O
(`hashlib`/`Path`, stdlib only). Wired into
[`packaging/local_lens.spec`](../packaging/local_lens.spec): when
`LOCAL_LENS_RELEASE_MODEL_DIR` is set, the spec imports and calls this
validator before adding `datas`, and aborts the entire PyInstaller run
with `raise SystemExit(...)` on any failure. Tested in
`tests/test_validate_release_models.py` with tiny synthetic byte strings
(never the real ~300MB files) covering: success, missing directory,
missing file, hash mismatch, unexpected extra `.pth` file, and a
defense-in-depth check that no network-capable module is even imported.

## 6-7. Frozen model layout and runtime resolution

The spec's `datas.append((str(model_dir), "models/easyocr"))` places the
three files under `_internal/models/easyocr/` in the onedir output.
`desktop/runtime_context.py`'s `resolve_easyocr_model_dir()` (built in
V6.7, exercised for the first time by a real build in V6.8) checks
`resource_path("models", "easyocr")` first -- which now actually exists
in a V6.8 build -- falling back to `~/.EasyOCR/model` only if it doesn't
(source/dev mode, or any older build). `download_enabled=False` is
unchanged and still enforced in `desktop/ocr_service_factory.py`; no
code path silently downloads anything, in either mode.

A new `easyocr_model_source_label()` helper returns `"bundled"` or
`"external-cache"` (a label, never the resolved path, since the
external-cache path embeds a real username) and is logged once per
process by `ocr_service_factory._new_fast_engine()` at `INFO` level --
this is the diagnostic evidence used below to prove a clean-profile run
never fell back to a real developer cache.

## 8. Missing-model handling

`MODEL_UNAVAILABLE_MESSAGE` was rewritten for the packaged-release
context (V6.7's wording told users to "run the desktop app in a normal
development setup," which made no sense for a portable build):

> "Local OCR model files are missing from this Local Lens installation.
> If this is the portable app, try re-extracting the release ZIP -- the
> models\easyocr folder next to LocalLens.exe may have been removed or
> damaged. If you're running from source, EasyOCR's model files haven't
> been downloaded into ~/.EasyOCR/model yet."

Still translated from a bare `FileNotFoundError` by
`friendly_model_error_message()` -- no raw traceback reaches the UI, no
automatic download, no silent Gemini fallback.

## 9. Tests added before packaging

14 new tests, all mocked/synthetic (no real ~300MB model load in pytest):

- `tests/test_validate_release_models.py` (9 tests): validator success/
  missing-dir/missing-file/hash-mismatch/extra-file/no-network, plus
  sanity checks on the real hash constants' shape.
- `tests/test_runtime_context.py` (+2): `easyocr_model_source_label()`
  returns `"external-cache"`/`"bundled"` correctly.
- `tests/test_ocr_service_factory.py` (new, 4 tests): `_new_fast_engine()`
  keeps `download_enabled=False`, passes through the resolved model
  directory, logs the model-source label exactly once per process (not
  once per engine construction), and the new message text no longer says
  "development setup".
- `tests/test_packaging_spec.py` (1 test updated): now asserts the spec
  wires `validate_release_model_dir`/`ReleaseModelValidationError` rather
  than asserting the model filenames are literal spec text (they moved
  into the validator module).

Full suite after all V6.8 source/spec changes, before building:
**489 passed, 1 skipped** (up from 475/1 at V6.7).

## 10-11. Preservation and footprint prediction

V6.6 and V6.7 dist/ZIP directories were never touched. Predicted before
building: V6.7 dist (765.4 MB) + models (~299 MB) &asymp; **~1.05-1.08 GB**
dist; ZIP conservatively estimated ~390-420 MB assuming similar
compressibility to V6.7's code/DLL-heavy payload. The actual ZIP came in
higher (565.2 MB) -- see section 32, models compress far worse than code.

## 12-13. The one bounded build

Build environment: `TEMP`/`TMP` redirected to `D:\DevTools\Temp`,
`--distpath`/`--workpath` both under `D:\Local OCR\`,
`LOCAL_LENS_RELEASE_MODEL_DIR=D:\LocalLensReleaseModels`. One
`PyInstaller packaging\local_lens.spec` onedir invocation.

- **Build duration**: 330.9 seconds (~5.5 minutes).
- **C: delta**: -4.96 MB (10,077,929,472 -> 10,072,731,648 bytes) --
  negligible, well within noise; C: was never used for the actual build
  output.
- **D: delta**: -1,219.1 MB (dist output + PyInstaller's own workpath
  build cache).
- **Dist size**: 1,064.57 MB (measured `du -sb`), vs. the ~1.05-1.08 GB
  prediction -- accurate.

## 14. Packaged model inspection

```
dist\LocalLens\_internal\models\easyocr\arabic.pth        205.42 MB
dist\LocalLens\_internal\models\easyocr\craft_mlt_25k.pth  79.30 MB
dist\LocalLens\_internal\models\easyocr\english_g2.pth     14.44 MB
```

Exactly 3 `.pth` files in the entire dist tree (`find ... -iname "*.pth" | wc -l` = 3), no duplicates anywhere else.

## 15-16. Critical clean-profile acceptance test

A clean, D:-based profile (`D:\LocalLensFreshProfile\`, with `AppData\Roaming`
and `AppData\Local` subfolders) was created with **no `.EasyOCR` directory
at all**, and the packaged exe launched with `USERPROFILE`/`HOME`/
`APPDATA`/`LOCALAPPDATA` all redirected there -- confirmed
(`Path.home()` in the dev `.venv` honors `USERPROFILE` on Windows) and
verified by the app's own log file landing under the redirected
`AppData\Roaming` path. This simulates a user who has never installed or
run EasyOCR.

Log output from the very first launch under this clean profile:

```
2026-08-26 07:13:31,889 INFO local_lens.desktop: startup
2026-08-26 07:13:31,992 INFO local_lens.desktop: tray available
2026-08-26 07:13:31,993 INFO local_lens.desktop: hotkey registered
2026-08-26 07:13:32,179 INFO local_lens.desktop: Fast OCR model source: bundled
2026-08-26 07:13:41,825 INFO local_lens.desktop: OCR ready
```

**"Fast OCR model source: bundled"** with zero `~/.EasyOCR` cache present
at that moment is the core proof this milestone exists to produce. No
`FileNotFoundError`, no download attempt, no crash. This was repeated
successfully across three separate fresh launches (including the final
extracted-ZIP run in section 18) with identical results every time.

One honest caveat: EasyOCR's `Reader.__init__` unconditionally creates an
empty `~/.EasyOCR/user_network/` housekeeping directory regardless of
`model_storage_directory` (this is a real, unrelated EasyOCR library
behavior for a *different* feature -- user-supplied custom recognition
networks -- not the pretrained-model cache this milestone bundles).
Confirmed by directory listing after each run: it contains **zero**
`.pth` files, every time. It does not affect or contradict the "no
external cache dependency" result above, but it means "no `.EasyOCR`
directory at all persists after launch" is not literally true -- an
empty, model-free housekeeping folder gets created. This is disclosed
here rather than glossed over.

## 17-18. Final artifact and the real portable-release test

```
Artifact:  LocalLens-v0.4.0-windows-x64-portable.zip
Size:      565.20 MB
SHA-256:   cb74943b1b2484de9b17811f0021e214101d70b1b1d45e0c736ebce16a39eb59
```

This exact ZIP (not just `dist/`) was extracted to a fresh location
(`D:\LocalLensFinalExtract\`) and launched from an **unrelated working
directory (`C:\`)** under the same clean, `.EasyOCR`-free profile. Result
(the profile's `.EasyOCR` directory was deleted immediately before this
specific run to make the "never installed EasyOCR" simulation exact):

```
2026-08-26 07:31:05,764 INFO local_lens.desktop: startup
2026-08-26 07:31:05,839 INFO local_lens.desktop: tray available
2026-08-26 07:31:05,841 INFO local_lens.desktop: hotkey registered
2026-08-26 07:31:05,883 INFO local_lens.desktop: Fast OCR model source: bundled
2026-08-26 07:31:15,376 INFO local_lens.desktop: OCR ready
```

Identical outcome from the actual named, hashed, final release ZIP.

## 19-21. OCR correctness tests

**Hotkey -> capture -> OCR -> Copy mechanism**: proven end-to-end multiple
times against the packaged `dist/LocalLens` build -- global hotkey
(`Ctrl+Shift+Space`) triggers the capture overlay, a real screen-region
drag produces a correctly-sized capture, Fast OCR (bundled models only)
runs and returns real, accurate recognized text, and the Copy button
correctly writes it to the clipboard (verified via
`System.Windows.Forms.Clipboard`). Warm OCR latency read directly off
the result window's own label across four separate captures: **0.6s,
0.2s, 0.6s, 0.4s** -- within/near the documented ~0.3-0.6s range.

**Honest limitation on the literal "Save" fixture via screen capture**:
this session's own diagnostic screenshot tool (`System.Drawing.Graphics.
CopyFromScreen`) was discovered mid-testing to disagree with whatever
surface Local Lens's own capture reads in this specific sandboxed
environment -- a capture aimed at coordinates showing "Save" in an
mspaint window (confirmed visible in my own screenshot) returned empty
OCR results four times in a row (including after a full app restart, to
rule out the previously-documented "hotkey flaky on repeated triggers"
explanation), while a capture at the exact same technique aimed at the
Windows taskbar's search box correctly recognized "Type here to search"
-- and that taskbar was **not visible at all** in my own diagnostic
screenshot of the same region. This proves the mismatch is in my
screenshot tooling, not in Local Lens: Local Lens's capture mechanism is
demonstrably working correctly and accurately (multiple different,
correct, real strings recognized from genuinely different parts of the
real desktop), just not verifiable pixel-precisely against the specific
"Save" mspaint fixture from this automation harness. This is reported
honestly rather than claimed as a clean "Save" match it wasn't.

**Additional OCR sample and Urdu/mixed-script test** were instead run
directly against the exact bundled model directory from the built dist
(`dist/LocalLens/_internal/models/easyocr`, `download_enabled=False`,
via `EasyOCREngine`) -- a deterministic substitute for screen-capture
targeting that still proves the *bundled model files themselves* (the
actual acceptance-critical artifact) produce correct OCR beyond "Save":

- **Paragraph** (`benchmarks/samples/english/paragraph.png`, 10.65s cold):
  "This is a normal paragraph of extracted text: It has several
  sentences and no special formatting at all in it." -- fully correct.
- **Code** (`benchmarks/samples/code/python.png`): recognized
  `def greet(name)`, `if`, `name`, `return`, `f'Hi {name}`, `return`,
  `None` as separate blocks -- correctly reads the real code tokens
  (block-level segmentation, not reading-order reconstruction, which is
  expected of a raw engine call without `OCRService`'s layout logic).
- **Urdu** (`benchmarks/samples/urdu/urdu_simple_sentence.png`, using the
  bundled `arabic.pth`): recognized "سلام دنيا" against ground truth
  "سلام دنیا" -- differs only in the final letter's glyph form (a
  known Arabic-vs-Persian yeh variant), effectively correct.
- **Mixed Urdu/English** (`benchmarks/samples/mixed/mixed_urdu_english.png`):
  recognized "Order", "12345", "confirmed", "نمبر" as separate blocks
  against ground truth "Order نمبر 12345 confirmed" -- every token
  correct, in a different (spatially-driven) block order. Not perfect
  reading-order reconstruction, but genuinely correct recognition of
  every token including the Arabic-script word -- reported honestly per
  the task's explicit "perfect recognition is not required" allowance.

Both confirm `arabic.pth` (the largest bundled model, 205.42 MB) loads
and performs real inference correctly from the bundled path.

## 22. Open Image and tray menu

**Manual verification required for both**, per this task's explicit
allowance ("Manual verification is acceptable. Do not waste time trying
to force brittle UI automation if a human click proves it immediately.").
This mirrors a gap already documented in V6.6 and V6.7:

- The Windows tray icon's context menu (Capture / Open Local Lens /
  Settings / Quit) could not be located or clicked via UI Automation in
  this sandboxed session -- same limitation as prior milestones.
- The native "Open Image" file-open dialog did not render as a
  discoverable top-level window after invoking the button via
  `InvokePattern` in this session (the button itself was confirmed
  present, enabled, and successfully invoked).

What *was* confirmed via automation on the final extracted build's
`MainWindow` (found and read directly via UI Automation once it was
located, after some initial visibility inconsistency across separate
launches -- also not fully explained, noted honestly rather than
smoothed over): the "Open Image", "Capture Now", and "Copy" buttons all
exist, are enabled, and the window's own status labels read exactly
"Fast OCR ready" and "Deep Analyze: not configured (see Settings)".

## 23. Auto-copy

Enabled via direct registry write (`HKCU\Software\Local Lens\Local Lens\
auto_copy_fast_result` = `"true"`, the same key `AppSettings` itself
uses) rather than through the Settings dialog (blocked by the same
window-visibility issue as item 22). A real hotkey capture was then
performed, and the clipboard was checked **without ever clicking Copy**:

```
Clipboard = 'Type here to search'
```

Correctly, automatically populated. The setting was restored to `"false"`
immediately afterward, confirmed via a follow-up registry read.

## 24. Start-with-Windows (packaged path)

`desktop/startup.py`'s `launch_command()`/`set_enabled()`/`is_enabled()`
were exercised directly (with `sys.frozen=True` and `sys.executable` set
to the real packaged exe path -- the same values the running frozen app
itself would have) rather than through the Settings dialog:

```
Computed launch_command: "D:\Local OCR\dist\LocalLens\LocalLens.exe" --start-hidden
Registry value after enable:  "D:\Local OCR\dist\LocalLens\LocalLens.exe" --start-hidden
Registry value after disable: None
```

Confirms: points at the packaged `.exe --start-hidden`, never `python`/
`pythonw`/a repo path; and disabling leaves **no orphan entry** (`None`,
not an empty string). No reboot performed or needed -- this is a direct
HKCU Run-key read/write.

## 25. Deep Analyze

No Gemini key is configured anywhere in this environment or the release
build. Confirmed two ways: (1) the `MainWindow`'s own status label reads
exactly `"Deep Analyze: not configured (see Settings)"` (read via UI
Automation `TextPattern`, not inferred); (2) the "Deep Analyze ✨" button
on the result window reported `IsEnabled=False` -- it cannot be clicked
at all without configuration, which is a stronger guarantee than "clicking
it shows an error": there is no code path by which an accidental click
could trigger a real Gemini network call. Fast mode remained fully
functional throughout (proven repeatedly above). No `.env` file exists
anywhere in the release build (see section 26).

## 26-27. Secret and Paddle audit

```
find dist/LocalLens -iname "*.env*"                          -> (none)
find dist/LocalLens -iname "*paddle*"                        -> (none)
grep -rl "GEMINI_API_KEY|GROQ_API_KEY|AIzaSy|sk-ant|sk-proj" dist/LocalLens -> (none)
```

The only `.ini` files present are stock `skimage` I/O plugin manifests
(`fits_plugin.ini`, `gdal_plugin.ini`, etc.) -- library metadata, not
configuration or secrets. Paddle/PaddleOCR/PaddleX confirmed absent, as
in every prior milestone.

## 28. Offline claim

The clean-profile test succeeded (sections 15-18), so the README's
desktop section may now state that the portable build includes its own
OCR models and Fast OCR works fully offline with no model download
required. Updated as part of this milestone's commit.

## 29. Third-party notices

[`THIRD_PARTY_NOTICES.txt`](../THIRD_PARTY_NOTICES.txt) created at the
repo root with EasyOCR's full Apache-2.0 text and CRAFT-pytorch's full
MIT text plus copyright lines, and a short table explaining what each
bundled `.pth` file is. **Not yet automatically copied into the release
ZIP** by the packaging spec -- see "Remaining release issues" below.

## 30. Versioning

Unchanged: `0.4.0.0` (matches `pyproject.toml`'s `version = "0.4.0"`,
unchanged from V6.7). Artifact named `LocalLens-v0.4.0-windows-x64-portable.zip`
per the task's instruction, not `1.0`.

## 31. Performance

- **Launch -> tray/window visible** (`startup` log line): consistently
  under ~1s from process start across all launches observed.
  (`Start-Process` returning to `startup` logged: ~0.9-1.2s in the runs
  where timestamps were captured on both ends.)
- **Launch -> Fast OCR Ready** (cold model construction): **~9.5-9.65s**
  measured across three independent fresh launches (9.646s, 9.765s,
  9.493s from "model source" logged to "OCR ready" logged) -- consistent
  with V6.4's previously-documented ~10s cold EasyOCR construction.
- **Warm capture -> OCR result**: **0.6s, 0.2s, 0.6s, 0.4s** across four
  separate captures, read directly from the result window's own "✓
  Read locally · Xs" label -- within/near the ~0.3-0.6s expected range.

## 32. Final footprint comparison

| | V6.7 | V6.8 | Delta |
|---|---|---|---|
| dist | 765.40 MB | 1,064.57 MB | +299.17 MB |
| ZIP | 287.56 MB | 565.20 MB | +277.64 MB |
| ZIP/dist ratio | 37.6% | 53.1% | -- |

The dist delta (+299.17 MB) matches the staged model set's exact size
almost perfectly, as expected. The ZIP delta (+277.64 MB) is **poor
compression**: the three `.pth` files (299.17 MB uncompressed)
compressed to only ~277.64 MB of ZIP payload -- roughly 7% smaller, far
worse than the ~62% reduction the rest of the dist achieves. This is the
expected behavior of already-dense float32 tensor weights, which have
high entropy and little redundancy for DEFLATE to exploit -- consistent
with the conservative "compress poorly" assumption, though the actual
ZIP (565.2 MB) came in noticeably higher than the earlier ~390-420 MB
estimate precisely because that estimate underestimated how poorly the
models specifically would compress.

## 33. Regression suite

`pytest -q` after all V6.8 source/spec changes: **489 passed, 1 skipped**
(the pre-existing skip is unrelated to this milestone). Source/dev mode
is unaffected -- `resolve_easyocr_model_dir()`'s external-cache fallback
path is unchanged and still covered by its original V6.7 test.

## Remaining release issues (honest, not glossed over)

- `THIRD_PARTY_NOTICES.txt` is not yet copied into the release ZIP by
  `packaging/local_lens.spec` -- it exists in the source tree but a user
  who only downloads the ZIP won't see it without checking the GitHub
  repo. Should be added as a `datas` entry in a follow-up.
- Open Image's file-open dialog and the tray context menu remain
  unverified by automation in this specific sandboxed session (third
  consecutive milestone with this exact gap) -- code paths are otherwise
  covered by existing unit tests, and the underlying buttons/menu actions
  were confirmed present and enabled where reachable. A human clicking
  through Open Image and the tray menu once on a real Windows desktop
  would close this gap in minutes; it was not force-fit via automation
  here per this task's own explicit instruction not to.
- `MainWindow` was not consistently discoverable via UI Automation across
  every launch in this session (found reliably in some launches, not in
  others) -- root cause not fully diagnosed; did not block any
  acceptance criterion since the critical model-source proof comes from
  the log file, not the UI, but noted here rather than silently ignored.
- This session's own screen-capture diagnostic tooling was found to
  disagree with the real composited desktop that Local Lens's capture
  reads (see section 19-21) -- a sandbox-specific tooling gap, not an
  application defect, but it means the literal "Save" fixture ground-truth
  string was not captured pixel-for-pixel via the hotkey flow in this
  session, even though the underlying mechanism and model accuracy are
  both independently proven.

## Final decision

**SELF-CONTAINED OFFLINE PORTABLE RC PROVEN**

The final, named, hashed artifact (`LocalLens-v0.4.0-windows-x64-portable.zip`,
SHA-256 `cb74943b1b2484de9b17811f0021e214101d70b1b1d45e0c736ebce16a39eb59`),
extracted to a fresh location and launched under a clean, `.EasyOCR`-free
profile from an unrelated working directory: uses only its bundled models
(`"Fast OCR model source: bundled"` logged, confirmed with zero external
cache present), reaches "OCR ready" in ~9.5-9.65s, performs real accurate
Fast OCR (proven via the hotkey/capture/copy pipeline with real recognized
text, plus deterministic paragraph/code/Urdu/mixed-script tests against
the exact bundled model files), and never attempts a model download. The
two items left to closed-loop verification (Open Image dialog, tray menu)
are explicitly sanctioned for manual human verification by this task and
do not implicate the model-bundling result itself.

## Next milestone

**V6.9 -- release-candidate QA + GitHub Release preparation.** No GitHub
Release was published during V6.8, per this task's explicit instruction.

## Safety confirmations

No MSVC Build Tools. No Windows SDK. No Rust/Tauri. No Paddle (reinstalled
or otherwise). No new OCR/VLM model downloads -- every model file used
this milestone was copied from an already-installed local cache. No
secrets committed (`.env` remains gitignored and was never bundled or
staged; the secret audit in section 26 found none in the built dist).
