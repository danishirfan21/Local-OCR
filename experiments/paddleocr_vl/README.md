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

## Results

<!-- Filled in from the actual run performed for this V3 iteration -- see
     the V3 implementation report for the authoritative, dated numbers.
     This file is updated whenever the experiment is re-run. -->

See the V3 final report for the measured results and their status
(measured-locally vs. upstream-claim vs. not-tested) as of this iteration.

## Known cost

First construction downloads multiple model families (document layout
detection + the VL recognition model itself) to
`~/.paddlex/official_models/`. In this sandboxed environment (observed
~60-100KB/s), that took on the order of many minutes to reach the final,
largest weight file -- see the V3 report for the exact wall-clock time
measured. On a normal broadband connection this would be a few minutes at
most; the slowness here is specific to this sandbox's network, not the
model itself.
