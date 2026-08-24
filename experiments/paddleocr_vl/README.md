# PaddleOCR-VL experiment (isolated, not in the production path)

Evaluates `paddleocr`'s bundled `PaddleOCRVL` pipeline (v1.6, ~0.9B
parameter vision-language model for document parsing) against the same
`benchmarks/` corpus the production engines are measured on, so results are
comparable. Nothing here is imported by `local_lens/` or `app.py`.

## Why this exists

The V3 product direction (Capture → Understand → Act) eventually wants
layout-aware, table/formula-capable document parsing, which PaddleOCR-VL is
explicitly built for and the plain OCR engines are not. This experiment
answers: is it practical to run locally in this environment today, and is
the output quality worth its cost?

## Setup

Needs the `paddlex[ocr]` extra on top of `requirements-paddle.txt` (see
that file's comment) -- `PaddleOCRVL` raises a clear `DependencyError`
without it, which is how this was discovered.

```bash
pip install -r requirements.txt
pip install -r requirements-paddle.txt
pip install "paddlex[ocr]==<paddlex version>"
python experiments/paddleocr_vl/run_sample.py path/to/image.png
python experiments/paddleocr_vl/evaluate.py   # full corpus run
```

## Method

`run_sample.py` runs one image and prints raw output + load/inference
timing. `evaluate.py` runs the full `benchmarks/` corpus and computes the
same CER/WER/similarity metrics `run_benchmark.py` uses for EasyOCR/
PaddleOCR, writing `results.json` alongside this file.

## Results (measured locally, this environment, CPU-only)

Full run: `results.json` (11/11 fixtures ran without error). Load time
146.0s cold from local disk cache (no download this run); per-image latency
8-132s on CPU (see table). Numbers below are CER (0.0 = perfect) unless noted.

| Fixture | CER | WER | Notes |
|---|---|---|---|
| short_ui_save ("Save") | 0.00 | 0.00 | Perfect -- and notably does **not** reproduce plain PaddleOCR's short-text failure (CER 1.00 on the same fixture, see main benchmark results) |
| short_ui_cancel | 0.00 | 0.00 | Perfect |
| english/paragraph | 1.00 | 1.00 | **Empty output, no error raised.** Genuine open question -- not glossed over; see "Known limitations" |
| english/numeric | 0.00 | 0.00 | Perfect |
| english/english_numbers | 0.00 | 0.00 | Perfect |
| code/code_snippet | 0.22 | 0.00 | Every word correct (WER 0) but indentation was **not preserved** -- CER penalty is purely whitespace |
| tables/table_simple, table_dense | n/a | n/a | Ran without error; this experiment's `evaluate.py` does not yet score table structure accuracy for VL (only latency/error) -- a real gap, not implemented this iteration |
| urdu/urdu_paragraph | 0.79 | 1.00 | Poor -- consistent with the corpus's known unshaped-glyph rendering limitation, not necessarily the model |
| mixed/mixed_urdu_english | 0.12 | 0.25 | **Better than both OCR-only engines** on this fixture (EasyOCR 0.39, PaddleOCR 0.23 CER) |
| urdu/urdu_numbers | 0.40 | 0.50 | Moderate |

Compare against the same-corpus EasyOCR/PaddleOCR run in
`benchmarks/results/20260824T221555Z.json` for a like-for-like read.

**Headline takeaway:** PaddleOCR-VL is the only one of the three that
handled short UI text perfectly, and it clearly outperformed both OCR-only
engines on the mixed Urdu/English fixture -- consistent with it being a
layout/context-aware model rather than a per-word recognizer. It is not a
strict upgrade, though: one plain-English paragraph produced empty output
for no diagnosed reason, and it does not yet have a table-structure score
in this experiment.

## Known cost (measured)

First construction downloads multiple model families (document layout
detection + the VL recognition model's 20 weight/config files) to
`~/.paddlex/official_models/PaddleOCR-VL-1.6/`. Measured on this
sandbox's slow link (~60-100KB/s): the final and largest fetch batch (20
files, mostly the model weights) took **6m46s** once it was actually
transferring. Total first-time setup in this session took considerably
longer than that because it was interrupted twice by an unrelated disk-
space exhaustion issue (the sandbox's drive filled up from
`~/.paddlex/official_models/` + pip's cache combined -- see the V3 report)
and had to be resumed; none of that extra time reflects the model itself.
On a normal broadband connection this would be a few minutes at most.

**Cold load time (from local disk cache, no download):** 120-146s across
two runs. **Per-image inference (CPU-only):** 8-132s depending on image
content/size. Both are CPU-bound and would be substantially faster with a
GPU (see the model's own VRAM figures researched for the V2 report:
~2.1GB at FP16).

**Disk footprint:** ~3GB total under `~/.paddlex/official_models/` after
this experiment plus the table-extraction pipeline (V3's other new
PaddleOCR-dependent feature) were both set up.
