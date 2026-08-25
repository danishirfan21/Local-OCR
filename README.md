# 🔍 Local Lens

**A local-first screenshot and document intelligence tool.**

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
- Native desktop capture workflow
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

## Privacy

- **Fast mode** runs entirely on your machine — no image or extracted text
  is sent anywhere. `tests/test_no_silent_network.py` enforces that opening
  the app, uploading, and Fast extraction never open a network connection.
- **Deep Analyze** sends the selected image to Google's Gemini API (see
  [Deep Analyze](#deep-analyze-gemini-byok)) — it is explicit, opt-in
  (requires clicking a button after seeing a disclosure), and never
  silently triggered. Local Lens does not operate this infrastructure
  itself; you bring your own Gemini API key.
- **Model weights download from the internet on first use** of a local
  engine/pipeline (EasyOCR, and — only if you've opted into
  `requirements-paddle.txt` — PaddleOCR/the table pipeline/legacy local
  PaddleOCR-VL). One-time per engine/pipeline, not ongoing.
- No telemetry, analytics, or external logging in this repo.
- We don't claim "nothing ever leaves your machine" as a blanket statement —
  the claim is scoped precisely: Fast mode is local-only; Deep Analyze is
  not, and says so.

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
