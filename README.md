# 🔍 Local Lens

**Private AI for everything on your screen.**

Local Lens is a local-first screenshot and document intelligence tool. It
started as a small Streamlit + EasyOCR "paste a screenshot, get text" app
(originally called Image Text Extractor / VisionText AI); this repository is
evolving it into a broader document-understanding system, one solid layer at
a time. The GitHub repo is still `Local-OCR` — the app itself is now called
**Local Lens**.

The intended interaction loop is:

**Capture → Understand → Act**

> Take a screenshot → Local Lens figures out what it is (plain text, code, a
> table, ...) → you get the right export/action for that content.

## What actually works today

Only listing what is implemented and verified, not the roadmap:

- **Local OCR** via [EasyOCR](https://github.com/JaidedAI/EasyOCR), no cloud
  API calls for text extraction.
- **Clipboard / Snipping Tool workflow** — copy a screenshot and it's
  auto-detected, or paste with Ctrl+V, or upload a file.
- **Pluggable OCR engines** — EasyOCR today; an optional
  [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) backend behind the
  same interface (see [PaddleOCR](#paddleocr) below for install/status).
- **Language selection** — English and Urdu, normalized through a canonical
  language layer rather than hardcoded per-engine codes (more languages can
  be added in `local_lens/languages.py` without touching the UI).
- **Bounding boxes and confidence are preserved**, not discarded. A "Show
  detected regions" toggle overlays them on the image.
- **Reading-order text reconstruction** — text is grouped into lines by
  vertical position and sorted left-to-right/top-to-bottom, instead of being
  joined into one giant line.
- **Heuristic content classification** — a simple, non-ML classifier labels
  extracted content as text / code / table / unknown, and the export
  buttons shown adapt to that label. This is a heuristic, not a model —
  confidence is reported and deliberately not overstated.
- **Structured exports** — plain text, Markdown, and JSON (JSON includes
  every text block with its confidence and bounding box, not just the
  concatenated string).
- **Optional preprocessing pipeline** — None / Auto / High contrast, PIL-only
  (no OpenCV dependency), conservative by default.

## What is not implemented yet

Table/formula extraction, layout-aware (multi-column) reading order, local
LLM Q&A over screenshots, a CLI/API/MCP server, and a native desktop app are
all **roadmap items**, not current features. See [Roadmap](#roadmap).

## Architecture

```
Input                          local_lens/ (no Streamlit dependency)
 │                              ├── models.py         DocumentResult, TextBlock, BoundingBox
 ├─ uploaded image              ├── engines/           OCREngine interface + backends
 ├─ pasted image                │    ├── easyocr_engine.py
 └─ clipboard screenshot        │    └── paddleocr_engine.py   (optional)
 │                              ├── languages.py       canonical <-> engine-specific codes
 ▼                              ├── preprocessing/     None / Auto / High-contrast
 app.py (Streamlit UI only) ──▶ ├── reconstruction.py  bbox-based reading order
 │                              ├── classification.py  text / code / table heuristic
 ▼                              ├── export.py           txt / markdown / json
 UI / export                    └── services/ocr_service.py   orchestrates all of the above
```

`app.py` only handles layout, session state, and Streamlit caching. Every
OCR/document-understanding decision goes through `local_lens/`, which has no
Streamlit import anywhere — the intent is that a CLI, a FastAPI service, an
MCP server, or a future desktop shell can call `OCRService.process(...)`
directly without depending on Streamlit at all.

`streamlit run app.py` is the canonical way to launch it. `streamlit run
ocr_app.py` still works too — that file is now a one-line compatibility
shim so the old command doesn't break.

## PaddleOCR

A second engine, `local_lens/engines/paddleocr_engine.py`, implements the
same `OCREngine` interface using PaddleOCR's current pipeline API
(`PaddleOCR(lang=...).predict(image)` — not the older `.ocr()` tuple API
from many tutorials, which is legacy in `paddleocr>=3.x`).

It is **not** installed by default — `paddlepaddle` is a large, platform-
specific dependency (separate CPU/GPU wheels). Install it explicitly:

```bash
pip install -r requirements.txt
pip install -r requirements-paddle.txt
```

If it isn't installed, the sidebar disables the PaddleOCR radio option
instead of crashing the app.

**Verified working** on Windows/CPU during this iteration (`paddlepaddle`
3.3.1, `paddleocr` 3.7.0) — with one real bug found and worked around:
PaddlePaddle's CPU (oneDNN/PIR) executor raised
`NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support [...]`
inside the text-detection op on this hardware. `paddleocr_engine.py`
constructs the pipeline with `enable_mkldnn=False`, which avoids the broken
code path (costs some CPU inference speed; correctness of the output was
unaffected in testing). If a future `paddlepaddle` release fixes this
upstream, that flag can be dropped.

First run downloads ~5 small model files (detection, recognition, doc
orientation, unwarping, textline orientation) to `~/.paddlex/official_models/`
— a few tens of MB, one-time.

## PaddleOCR-VL (research only — not integrated)

The longer-term target for document understanding is
[PaddleOCR-VL](https://huggingface.co/PaddlePaddle/PaddleOCR-VL), a ~0.9B
vision-language model aimed at full-page parsing (layout, tables, formulas,
109 languages). It was **investigated, not integrated**, this iteration:

| Question | Finding |
|---|---|
| Install requirements | Separate inference runtime/pipeline on top of `paddleocr`/`paddlepaddle`; pulls model weights from Hugging Face on first use |
| GPU support | Yes — ~2.1GB VRAM at FP16 for the 1.6 model line; ~0.5GB at INT4 |
| CPU support | Yes, but slow relative to GPU |
| Windows compatibility | Not verified in this environment — not attempted this iteration |
| Memory (CPU) | Not benchmarked here; upstream docs suggest it's runnable but they emphasize GPU |
| Table/formula recognition | A core design goal of the model, reported as a strength |
| Urdu support | Listed among its 109 languages, but upstream notes Urdu **ligature/joining output needs improvement** — not production quality out of the box |
| Layout / reading order | Also a core design goal (it's a document-parsing VLM, not a word-level OCR model) |

**Why not this iteration:** it's a materially heavier dependency (its own
model runtime, weight downloads) than adding a second OCR backend, and
forcing it in risked destabilizing the whole app for a feature that isn't
load-bearing yet. `local_lens/engines/` is structured so a
`PaddleOCRVLEngine` can be added later as a third `OCREngine` implementation
without changing `OCRService`, the UI, or the export layer.

## Privacy

- OCR itself runs entirely on your machine (EasyOCR/PaddleOCR are local
  models, not API calls) — no image or extracted text is sent anywhere by
  this app.
- **Model weights download from the internet on first use** of a given
  engine (EasyOCR and PaddleOCR both fetch their pretrained models the
  first time you select them, then cache locally). That is a one-time
  network request per engine/language, not an ongoing one.
- No telemetry, analytics, or external logging is implemented in this repo.
- We do not claim "nothing ever leaves your machine" as a blanket statement,
  because the first-run model download is real network activity — the
  claim is scoped to what it's actually true of: your images and extracted
  text.

## Installation

```bash
git clone https://github.com/danishirfan21/Local-OCR.git
cd Local-OCR
python -m venv .venv
.venv\Scripts\activate   # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
streamlit run app.py
```

Optional PaddleOCR backend: `pip install -r requirements-paddle.txt` (see
[PaddleOCR](#paddleocr) above).

Platform-specific setup notes (clipboard permissions, etc.) are in
[Setup.md](Setup.md).

## Testing

```bash
pip install -r requirements.txt   # includes pytest
pytest tests/ -v
```

Tests mock the OCR engine (`tests/test_engines.py`'s `FakeEngine`) so the
suite runs in well under a second with no model downloads.

## Benchmarks

```bash
python benchmarks/run_benchmark.py
```

A framework, not a tuned suite yet — see [benchmarks/README.md](benchmarks/README.md)
for what it measures today and how to add real samples.

## Roadmap

Future work, explicitly not built yet:

- Table detection → Markdown/CSV/JSON
- Formula/equation recognition
- Mixed Urdu+English document handling, tuned beyond basic language
  selection
- Layout-aware, multi-column reading order (current reconstruction is a
  deterministic single-pass heuristic, isolated in `reconstruction.py` so it
  can be swapped for a real layout model)
- PaddleOCR-VL integration (see above)
- Local LLM Q&A over captured screenshots/documents
- CLI, API (FastAPI), and MCP server interfaces on top of the existing
  `local_lens/` core
- Native desktop capture workflow (Streamlit is a V2 experimentation
  surface, not the long-term shell)
- Semantic screenshot history / search

## License

MIT License.
