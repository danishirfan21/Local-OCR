# 🔍 Local Lens

**Private AI for everything on your screen.**

Local Lens is a local-first screenshot and document intelligence tool,
moving from "OCR that dumps text" toward:

**Capture → Understand → Act**

> Take a screenshot → Local Lens figures out what it is (plain text, code, a
> table, Urdu, ...) and how best to read it → you get the right export/action
> for that content, with the reasoning visible, not hidden.

The GitHub repo is still `Local-OCR`; the app itself is **Local Lens**.

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

**Testing**: 98+ unit tests (mocked engines/extractors — `FakeEngine` in
`tests/test_engines.py` — no model downloads), covering models, hashing,
reconstruction (including a mixed-Urdu/English fixture), classification
(text + geometry signals), routing, input-type heuristics, script detection,
text normalization, table parsing, CSV/Markdown export, timing, and
benchmark metrics themselves.

**Benchmarking**: a real corpus (`benchmarks/corpus.py`) — 11 synthetic,
safe-to-commit fixtures across English, Urdu, mixed, short-UI, tables, and
code — scored with CER, WER, normalized similarity, latency, and (for
tables) row/column/cell accuracy, written to `benchmarks/results/*.json`.
See [benchmarks/README.md](benchmarks/README.md) for the corpus's known
limitations (notably: this environment's Pillow lacks `raqm` text shaping,
so rendered Urdu fixtures use isolated letterforms, not joined script).

## Experimental (not in the production path)

**PaddleOCR-VL** (`experiments/paddleocr_vl/`) — PaddlePaddle's ~0.9B
vision-language document-parsing model, evaluated against the same
benchmark corpus for a like-for-like comparison with EasyOCR/PaddleOCR.
Not imported by `local_lens/` or `app.py` anywhere. See that directory's
README for setup and results, and the "PaddleOCR-VL findings" section of
the V3 implementation report for measured numbers and their status
(measured-locally vs. upstream-claim vs. not-tested).

## Roadmap (not built)

- Production PaddleOCR-VL integration, if the experiment's results justify it
- Formula/equation recognition
- Layout-aware, multi-column reading order (current reconstruction is a
  deterministic single-pass heuristic, isolated in `reconstruction.py` so it
  can be swapped for a real layout model)
- Local LLM Q&A / reasoning over captured screenshots
- CLI, REST API, and MCP server interfaces on top of the existing
  `local_lens/` core (the architecture is already Streamlit-independent for
  this reason)
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
 app.py (Streamlit UI only) ────────▶ ├── engines/            OCREngine interface + backends
 │                                    ├── tables/             TableExtractor interface + backend
 ▼                                    ├── preprocessing/       None / Auto / High-contrast
 UI / export                          ├── reconstruction.py   bbox-based reading order
                                       ├── classification.py   text/code/table (text + geometry)
                                       ├── timing.py            per-stage latency
                                       ├── export.py            txt / markdown / csv / json
                                       └── services/ocr_service.py   orchestrates all of the above
```

`app.py` only handles layout, session state, and Streamlit caching. Every
OCR/document-understanding decision goes through `local_lens/`, which has no
Streamlit import anywhere — a CLI, a FastAPI service, an MCP server, or a
future desktop shell can call `OCRService.process(...)` directly.

`streamlit run app.py` is the canonical entrypoint. `streamlit run
ocr_app.py` still works too (a one-line compatibility shim).

## PaddleOCR

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

- OCR and table extraction run entirely on your machine — no image or
  extracted text is sent anywhere by this app.
- **Model weights download from the internet on first use** of a given
  engine/pipeline (EasyOCR, PaddleOCR, the table pipeline, and the
  experimental PaddleOCR-VL all fetch pretrained weights the first time
  they're used, then cache locally under `~/.paddlex/official_models/` or
  EasyOCR's own cache dir). One-time per engine/pipeline, not ongoing.
- No telemetry, analytics, or external logging in this repo.
- We don't claim "nothing ever leaves your machine" as a blanket statement
  — the first-run download is real network activity. The claim is scoped
  to what's actually true: your images and extracted text.

## Installation

```bash
git clone https://github.com/danishirfan21/Local-OCR.git
cd Local-OCR
python -m venv .venv
.venv\Scripts\activate   # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
streamlit run app.py
```

Optional PaddleOCR + table extraction: see [PaddleOCR](#paddleocr) above.
Platform-specific setup notes are in [Setup.md](Setup.md).

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
