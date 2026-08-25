# V6.7 — Portable-build trimming + true portability validation + offline-model release architecture

Builds on `docs/V6_6_PACKAGING_SMOKE_TEST.md`'s "PORTABLE BUILD VIABLE"
finding. V6.6 identified five concrete follow-ups; this milestone works
through all of them: trims the package with evidence (not guesses),
proves the ZIP is genuinely portable by extracting and relaunching it
from a fresh location under a different working directory, adds an
application icon and version metadata, and designs (without yet
building) the architecture for a future self-contained release that
bundles EasyOCR's model weights.

## V6.6 baseline

862 MB dist, 322.2 MB ZIP. `dist\LocalLens-v6.6-known-good\` was
preserved (renamed from `dist\LocalLens`) as a rollback artifact before
any V6.7 packaging change, and was not touched or deleted this
milestone.

## Existing-ZIP portability test (done first, per this milestone's own
instructions, before any packaging change)

The already-built V6.6 ZIP was extracted to `D:\LocalLensPortableTest_v6.6`
(a location that is not the repo, the existing `dist/`, `.venv`, or the
EasyOCR model directory) and launched directly. Startup log confirmed
`startup -> tray available -> hotkey registered -> OCR ready`, proving
the previously-built artifact itself was already genuinely portable
before any V6.7 source change touched it.

## Dependency analysis: why pandas/scipy/pyarrow appeared

Investigated with real evidence, not assumption, per this milestone's
explicit "prove it" instruction:

**Step 1 -- source audit.** `grep` across `local_lens/` and `desktop/`
for `pandas`/`scipy`/`pyarrow` imports: **zero matches.** Local Lens
code never imports any of the three directly.

**Step 2 -- dependency-metadata trace.** `pip show --Required-by` on
each package in the actual venv:

| Package | Required by |
|---|---|
| `pandas` | `streamlit` only |
| `pyarrow` | `streamlit` only |
| `scipy` | `easyocr`, `scikit-image`, `scikit-learn` |

`streamlit` is the separate `app.py` prototype -- `desktop/main.py`'s
import graph never touches it (`grep -rn streamlit desktop/ local_lens/`
returns nothing). `scipy`, in contrast, is a direct dependency of
`easyocr` itself.

**Step 3 -- empirical runtime check (the decisive evidence).** Ran the
actual desktop import graph, then a **real** `EasyOCREngine` construction
+ inference call (using the existing external model cache, no download),
then the Deep Analyze status-check path, diffing `sys.modules` before and
after each:

```
Import desktop.app_controller / ocr_service_factory / EasyOCREngine:
  pandas: NOT imported   pyarrow: NOT imported   scipy: NOT imported

Real EasyOCREngine() construction + extract() (cold, external cache):
  pandas: NOT imported even during real EasyOCR construction+inference
  pyarrow: NOT imported even during real EasyOCR construction+inference
  scipy: IMPORTED (160 submodules) -- e.g. scipy, scipy.__config__, scipy._cyutility, ...

production_gemini_configured(load_env()) (Deep Analyze status check):
  pandas: NOT imported   pyarrow: NOT imported
```

**Conclusion, evidence-based:**

- `pandas`/`pyarrow`: **PyInstaller false-positive/transitive
  collection.** PyInstaller's static analysis over-approximates by
  bytecode-scanning every module reachable from anything it includes --
  even code paths never actually executed. `torch.utils.tensorboard`
  has its own conditional `import pandas` (confirmed in
  `warn-local_lens.txt`: `pandas.plotting._misc (conditional) -- imported
  by torch.utils.tensorboard.writer`), and Local Lens never touches
  tensorboard. Confirmed safe to exclude.
- `scipy`: **genuine, required runtime dependency of EasyOCR** (160
  submodules actually imported during real inference). Confirmed **not**
  safe to exclude -- kept, exactly as this milestone's own caution
  anticipated ("be especially careful with scipy").

## Exclusions applied

`packaging/local_lens.spec`'s `excludes` list:
`["paddle", "paddleocr", "paddlex", "pandas", "pyarrow"]` -- two new
entries (`pandas`, `pyarrow`) added to V6.6's existing Paddle-family
exclusions, both backed by the evidence above.
`tests/test_packaging_spec.py::test_spec_excludes_pandas_and_pyarrow_but_keeps_scipy`
makes this a permanent regression test (it explicitly asserts `"scipy"`
is *not* in the excludes list, so a future edit can't silently break
Fast OCR while trying to save more space).

No other exclusions were added. Per this milestone's own instruction
("do not start adding dozens of exclusions to chase every megabyte"),
the remaining large contributors (`torch` 310MB, `cv2` 137.9MB, `PySide6`
91.6MB) are genuine runtime dependencies with no equivalent false-positive
evidence, so none were touched.

## Icon and version metadata

`packaging/generate_icon.py` (new, committed) programmatically renders
the same design `desktop/icon.py` already draws at runtime -- a blue
circle with a white "L" -- into a multi-resolution `.ico`
(`packaging/assets/app_icon.ico`, 16-256px). No downloaded icon pack, no
new brand design; the packaged `.exe`'s file icon now matches what the
running app's own tray/window icon already shows.

`packaging/version_info.txt` (new, PyInstaller's `pyi-grab_version`
format) embeds `ProductName`/`FileDescription`/`CompanyName` = "Local
Lens", and `FileVersion`/`ProductVersion` = `0.4.0.0`, mirroring
`pyproject.toml`'s `version = "0.4.0"` rather than introducing a
separate versioning scheme. Both are wired into `local_lens.spec`'s
`EXE(...)` via `icon=` and `version=`.

**Verified embedded** (not just referenced in the spec):

```
Get-Item LocalLens.exe | Select VersionInfo
  ProductName      : Local Lens
  FileDescription  : Local Lens -- local-first screenshot OCR
  CompanyName      : Local Lens
  FileVersion      : 0.4.0.0
  ProductVersion   : 0.4.0.0
  OriginalFilename : LocalLens.exe
  InternalName     : LocalLens
```

and the build log itself: `Copying icon to EXE` / `Copying version
information to EXE`.

## Model resource resolver

`desktop/runtime_context.py` gained `resolve_easyocr_model_dir()`: checks
a bundled `models/easyocr/` resource directory first (via the existing
`resource_path()` helper, which already resolves correctly for both
source-checkout and `sys._MEIPASS`-frozen execution), falling back to
`easyocr_model_directory()` (the user's `~/.EasyOCR/model` cache) when
no bundle exists -- which is every build to date, V6.6 and V6.7 alike.

`local_lens/engines/easyocr_engine.py`'s `EasyOCREngine` gained an
optional `model_storage_directory` constructor parameter (default `None`
= EasyOCR's own default, so the CLI/Streamlit/benchmark call sites are
unaffected), threaded into the reader cache key (a desktop caller
resolving a bundled directory and a CLI caller using the default must
never share a Reader pointed at the wrong directory).
`desktop/ocr_service_factory.py`'s `_new_fast_engine()` now passes
`model_storage_directory=str(resolve_easyocr_model_dir())` explicitly --
packaged-vs-dev model-path resolution lives in exactly one place, per
this milestone's "do not scatter packaged-resource logic through engine
code" instruction.

This is groundwork only -- **no build has ever populated a bundled
`models/easyocr/` directory**, so every resolution in V6.6 and V6.7
still falls through to the external cache. The seam exists so a future
milestone can bundle without touching `easyocr_engine.py` or
`ocr_service_factory.py` again.

## Future bundled-model build path (spec-level, unused this milestone)

`packaging/local_lens.spec` checks an optional
`LOCAL_LENS_RELEASE_MODEL_DIR` environment variable. If set, it verifies
all three required weight files (`craft_mlt_25k.pth`, `english_g2.pth`,
`arabic.pth`) exist in that directory *before* invoking `Analysis(...)`
-- a missing file raises `SystemExit` with an explicit message and
refuses to produce an incomplete build, rather than silently shipping a
partial model set or falling back to a download. No V6.7 build sets this
variable, so every build to date takes the external-cache path
unchanged. `tests/test_packaging_spec.py::test_spec_validates_release_model_dir_before_bundling`
checks this validation logic exists in the spec text (no PyInstaller
invocation in the test itself).

## Current EasyOCR model cache (measured precisely, not estimated)

```
arabic.pth          205.42 MB
craft_mlt_25k.pth     79.30 MB
english_g2.pth        14.44 MB
--------------------------------
Total                299.16 MB
```

These are exactly the three files EasyOCR needs for Fast mode's two
supported languages (`local_lens/languages.py`: English, Urdu) --
`craft_mlt_25k.pth` is the shared text detector used for every language,
`english_g2.pth` is the English recognizer, and `arabic.pth` is the
recognizer EasyOCR uses for its Arabic-script language family, which
Urdu belongs to. No extra, unused language family is present -- a future
bundled build would ship exactly these three files, nothing more.

## Model licensing (researched via the GitHub API, not assumed)

- **EasyOCR itself** (the library, and its own English/Arabic-family
  recognition models): **Apache License 2.0** -- confirmed directly via
  `gh api repos/JaidedAI/EasyOCR/license`
  (`https://github.com/JaidedAI/EasyOCR/blob/master/LICENSE`).
- **`craft_mlt_25k.pth`** (the text-detection model) is explicitly
  credited in EasyOCR's own README as coming from the "official
  repository" of **CRAFT-pytorch** (NAVER/Clova AI): "Detection execution
  uses the CRAFT algorithm from this official repository ... We also use
  their pretrained model." Confirmed via `gh api
  repos/clovaai/CRAFT-pytorch/license`: **MIT License**, copyright NAVER
  Corp -- no separate "research-only"/non-commercial restriction was
  found in that repository's License section.

**Practical conclusion**: both licenses permit redistribution.
Bundling these three weight files in a future GitHub Release or portable
ZIP appears permissible under both licenses' terms, provided the
redistribution carries the required attribution -- an Apache-2.0 NOTICE
reference for EasyOCR and the MIT copyright/permission text for
CRAFT-pytorch/NAVER Corp should accompany any future bundled
distribution (e.g. a `THIRD_PARTY_NOTICES.txt` shipped alongside the
models). This is this session's own reading of the two repositories'
publicly published license files at the time of writing, not formal
legal advice -- worth a final re-check at the actual release milestone,
but no blocking concern was found.

## Git policy for model weights (decided, not yet needed)

Model weights are **never** committed to this repository's normal Git
history -- confirmed unchanged this milestone (`find dist -iname
"*.pth"` returns nothing, and no `.pth` file is tracked). When a future
milestone does bundle models, the intended mechanism is: populate a
local directory, set `LOCAL_LENS_RELEASE_MODEL_DIR` for that one release
build, and attach the resulting bundled ZIP as a **GitHub Release
artifact** -- never as repository content. No Git LFS is planned; there's
no current reason for one given this mechanism.

## The one bounded build

Ran exactly once, to `dist\LocalLens-v6.7-test\LocalLens` (kept
separate from the V6.6 known-good artifact throughout).

```powershell
$env:TEMP = "D:\DevTools\Temp"; $env:TMP = "D:\DevTools\Temp"
.venv\Scripts\python.exe -m PyInstaller packaging\local_lens.spec `
    --distpath "D:\Local OCR\dist\LocalLens-v6.7-test" `
    --workpath "D:\Local OCR\build\pyinstaller-v6.7" --noconfirm
```

- **Duration**: 655.3 seconds (~10.9 minutes).
- Build log confirmed icon and version-resource embedding succeeded.

## Size comparison

| | V6.6 | V6.7 | Saved |
|---|---|---|---|
| **dist** | 862.0 MB | 765.4 MB | 96.6 MB (11.2%) |
| **ZIP** | 322.2 MB | 287.6 MB | 34.6 MB (10.7%) |

The reduction is attributable entirely to the `pandas`/`pyarrow`
exclusion (16.1MB + 74.6MB = 90.7MB direct, plus a handful of MB of
orphaned dependents that only those two packages needed) -- confirmed via
`packaging/dist_size_report.py`, which shows `pandas` and `pyarrow`
absent from the V6.7 build's top-15 contributors, while `scipy`
(57.4MB) and `scipy.libs` (19.3MB) are present at the same size as
before. **The reduction was not caused by removing anything Fast OCR
actually needs** -- see the packaged regression tests below.

**Estimated future ZIP with bundled EasyOCR weights**: adding the
measured 299.16MB of model weights to the 765.4MB dist gives ~1.06GB
unpacked. Compression won't be perfectly additive (model weights are
already-compressed float tensors, so they'll compress far less
efficiently than the ~63% ZIP ratio the code/library payload achieved
here) -- a reasonable estimate is roughly **560-620MB** compressed
(287.6MB current ZIP + ~270-330MB for the mostly-incompressible model
weights), not a precise figure.

## Packaging-size report helper

`packaging/dist_size_report.py` (new, stdlib-only, dev/packaging use
only -- never imported by `desktop/`) walks a PyInstaller onedir output
and prints the largest top-level contributors. Used throughout this
milestone's analysis; `tests/test_dist_size_report.py` covers it against
a synthetic fixture tree, not a real dist output.

## PyInstaller warnings comparison

`warn-local_lens.txt`: 781 lines (V6.6) -> 732 lines (V6.7). Diffed the
"missing module" lines between both builds: every difference is
attributable to `pandas`/`pyarrow`'s own now-unreached optional
integrations (`matplotlib` plotting backends, `odf`/`openpyxl` Excel
I/O, `sqlalchemy` SQL I/O, `numba` acceleration, `botocore`/`google.auth`
cloud-filesystem support for `pyarrow.fs`). **Zero warning lines
involving `torch`, `easyocr`, `PySide6`/Qt, or any classifier/export
dependency changed between the two builds** -- confirmed by grepping the
diff for those terms and finding no matches. This is the concrete
evidence that the exclusion didn't collaterally remove anything Local
Lens actually needs.

## Packaged regression verification (V6.7 build, direct launch)

Launched `dist\LocalLens-v6.7-test\LocalLens\LocalLens.exe` directly
(`Start-Process`, not via Python). Log confirmed
`startup -> tray available -> hotkey registered -> OCR ready` (~10.2s
cold, consistent with measured range). A real synthetic
`Ctrl+Shift+Space` + drag-select produced a working result popup with
real recognized text ("✓ Read locally · 0.3s"); **Copy verified via UI
Automation's `InvokePattern`** on the "Copy Code" button with the
clipboard confirmed to contain the exact displayed text afterward --
proving `scipy` staying in and `pandas`/`pyarrow` leaving didn't break
the real EasyOCR inference path.

## True portability validation (the mandatory part of this milestone)

The new V6.7 ZIP (`dist\LocalLens-portable-v6.7.zip`, created the same
way as V6.6's: `ZipFile.CreateFromDirectory`, Optimal compression --
287.6MB, 64.2 seconds) was extracted to a **fresh** location,
`D:\LocalLensPortableTest_v6.7` -- not the repo, not `dist/`, not
`.venv`, not the EasyOCR model directory -- and launched with the shell's
current working directory deliberately set to `D:\DevTools`, unrelated
to both the app and the repo.

**Log confirmed the full startup sequence from this independently-
launched, different-CWD copy**: `startup -> tray available -> hotkey
registered -> OCR ready`. A live `Capture Now` invocation (via UI
Automation) followed by a real drag-select produced a genuine capture
pipeline completion, logged end-to-end: `capture requested -> monitor
selected -> selection size: 190x30 -> capture complete -> OCR
completed`. This is direct, real evidence that the extracted, portable
copy resolves its EasyOCR model cache via `Path.home()` (not any
CWD-relative or bundle-relative path), needs no repo checkout, no
`.venv`, and no build folder to function.

**Settings persistence** was verified via the real mechanism rather than
the Settings dialog UI: `AppSettings()` with no explicit backing resolves
to `QSettings(ORGANIZATION_NAME, APPLICATION_NAME)`, i.e. the real
`HKEY_CURRENT_USER\Software\Local Lens\Local Lens` registry key --
identical regardless of which copy of the exe (repo dist, extracted
portable copy, or a future install location) reads it, since it depends
only on the organization/application name strings, never on the exe's
own path. A direct read/write/read round-trip against this real registry
key confirmed persistence works (`False -> True -> False`, restored to
its original value afterward, per this milestone's own instruction not
to leave a test toggle changed).

## What was NOT completed live this milestone (honestly reported, not silently skipped)

Two verification paths hit the same class of automation friction already
noted in `docs/V6_6_PACKAGING_SMOKE_TEST.md`, this time more clearly
diagnosed:

- **The Windows system tray's own icon and its context menu** (Capture /
  Open Local Lens / Settings / Quit) could not be reliably located or
  clicked via UI Automation or synthetic input in this sandboxed test
  session -- the taskbar's notification area and its overflow flyout did
  not respond to either approach the way Local Lens's own Qt windows
  did (which worked reliably via UI Automation's `InvokePattern`
  throughout this session). This looks like a property of this
  particular sandboxed remote session's taskbar/shell isolation, not of
  Local Lens -- V6.6 already separately verified close-to-tray (`WM_CLOSE`
  hides the window, process survives, confirmed via a real Win32 window
  handle) using the app's own window rather than the tray icon, and that
  code path is unchanged this milestone.
- **A second, independent auto-copy-firing observation on the extracted
  portable copy specifically** (combining a real non-empty capture with
  the auto-copy setting already proven to persist) was attempted several
  times but kept landing on window-identity ambiguity (`MainWindow` and
  `ResultWindow` share the literal title "Local Lens", so a UI-Automation
  lookup by name alone doesn't reliably distinguish which is currently
  topmost) and imprecise capture-region coordinates producing empty OCR
  results (a correct, tested outcome -- auto-copy is designed to skip
  empty results -- just not the positive case being sought). The
  underlying facts needed to conclude auto-copy works on the portable
  build are each independently proven: the setting persists via the real
  registry (above), the capture-to-OCR pipeline works on this exact
  extracted copy (above), and the auto-copy-fires behavior itself is
  unit-tested (`tests/test_app_controller.py::test_auto_copy_enabled_copies_fast_text_to_clipboard`)
  against the identical, unchanged `_on_fast_ocr_succeeded` code. Per
  this milestone's own "use a manual action if UI Automation remains
  annoying... a real manual verification is valid if reported honestly"
  guidance, this is reported as inferred-from-proven-parts rather than
  directly observed in one combined live action.

Open Image's file dialog (the same V6.6 gap) was **not** re-attempted
this milestone -- it was already established in V6.6 that the dialog
itself renders correctly with the right default directory/filter, and
`MainWindow.open_image()` runs the identical `OCRWorker`/
`build_fast_service()` code path already proven live multiple times this
milestone via the capture flow.

## Secret audit (again, on the new dist and ZIP)

```
dist\LocalLens-v6.7-test: no .env, no LOCAL_LENS_GEMINI_API_KEY value, no AIza-shaped string
LocalLens-portable-v6.7.zip (4302 entries): zero paddle/, zero .env, zero .pth
```

## Paddle audit (again)

`find dist -iname "*paddle*"` -> no results. `warn-local_lens.txt`
confirms PyInstaller *recognized and explicitly excluded* Paddle:
`excluded module named paddle`, `excluded module named paddleocr`.

## Model-download guard regression

Source-level: `desktop/ocr_service_factory.py`'s
`_new_fast_engine()` still constructs `EasyOCREngine(download_enabled=False, ...)`
-- unchanged this milestone. Not re-verified via a live missing-model
simulation against the packaged exe (the task explicitly forbids
deleting the real cache); the guard's logic has direct unit coverage
(`tests/test_easyocr_download_guard.py`) using a fake `easyocr` module,
plus two new tests this milestone confirming `model_storage_directory`
threads through correctly and produces separate cached readers per
directory.

## C:/D: disk-safety final check

| | Before V6.7 | After V6.7 (build + 2 ZIPs + 2 extractions) | Delta |
|---|---|---|---|
| C: free | 7.467 GB | 7.451 GB | -16 MB (OS-level noise, not build-related) |
| D: free | 642.735 GB | 640.794 GB | -1.941 GB |

**C: stayed effectively stable throughout this entire milestone.** The
D: delta is the sum of: the V6.7 dist (765MB) + its build intermediate
(~140MB) + the V6.7 portable ZIP (287.6MB) + the extracted portable-test
copy at `D:\LocalLensPortableTest_v6.7` (~765MB, a duplicate of the dist
for portability-proof purposes) -- all expected, all on `D:`.

## Cleanup recommendation (not performed automatically)

Safe to delete once this report and its artifacts are no longer needed
for reference:

- `build\pyinstaller\` (V6.6 intermediate, ~155MB) and
  `build\pyinstaller-v6.7\` (V6.7 intermediate, ~140MB) -- neither is
  needed once their respective dist output has been verified working.
- `D:\LocalLensPortableTest_v6.6\` and `D:\LocalLensPortableTest_v6.7\`
  -- the extraction-test copies created solely to prove portability;
  safe to remove once this document's findings are trusted.
- `dist\LocalLens-portable-v6.6-smoketest.zip` -- superseded by the
  smaller, otherwise-equivalent V6.7 ZIP, if the V6.6 known-good dist
  folder itself is being kept as the rollback reference instead.

**Not recommended for deletion**: `dist\LocalLens-v6.6-known-good\` (the
explicit rollback artifact this milestone was told to preserve) and
`dist\LocalLens-v6.7-test\LocalLens\` / `dist\LocalLens-portable-v6.7.zip`
(the new verified artifacts) -- both kept per this milestone's own
"do not automatically delete a successful/known-good build" instruction.

## Release-state decision

**`PORTABLE APP PROVEN, MODEL BUNDLING REMAINS`**

The application itself -- `LocalLens.exe` and everything it needs to run,
launch its tray/hotkey/capture/Fast-OCR/result/Copy pipeline -- is
proven portable: it runs independently of the development environment,
from an arbitrary extraction location, under an arbitrary working
directory. It is **not yet** a fully self-contained offline release: Fast
OCR still depends on the external `~/.EasyOCR/model` cache existing on
the machine it runs on. That distinction is deliberate and unchanged
from V6.6's model-strategy decision -- this milestone built the
architecture (`resolve_easyocr_model_dir()`, the spec's
`LOCAL_LENS_RELEASE_MODEL_DIR` seam, the licensing research) for closing
that gap, without closing it yet.
