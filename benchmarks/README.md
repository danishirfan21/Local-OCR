# Local Lens benchmark harness

A lightweight framework for comparing OCR engines. This is a **skeleton**
for now -- it establishes the structure and runs end-to-end, but the sample
set is tiny and synthetic, and the accuracy metric is intentionally naive.

## Layout

```
benchmarks/
├── README.md
├── run_benchmark.py     # CLI: runs configured engines over samples/
└── samples/
    ├── manifest.json    # list of {image, ground_truth} pairs
    └── *.png            # generated on first run if missing (see below)
```

## Adding samples

Add ground-truth text under `samples/` and register it in
`samples/manifest.json`:

```json
{
  "image": "my_sample.png",
  "ground_truth": "Expected extracted text"
}
```

Do not commit copyrighted or private material -- use synthetic images
(rendered text, screenshots you own the rights to, or generated test
fixtures) only. `run_benchmark.py` will auto-generate a couple of tiny
synthetic PNGs from `manifest.json` entries that don't yet have an image
file on disk, using PIL's own font rendering, so the repo doesn't need to
ship binary fixtures at all if you don't want it to.

## What it measures today

- **Latency**: wall-clock seconds per image per engine.
- **Rough accuracy**: word-overlap ratio between the engine's reconstructed
  text and the ground truth (case-insensitive, whitespace-normalized). This
  is not edit-distance/WER and should not be treated as a precise quality
  score -- it is a directional smoke signal only.

## What it does not measure yet (future work)

- Memory usage per engine.
- Language-specific accuracy breakdowns (e.g. Urdu vs English).
- Layout/reading-order preservation quality.
- Table/formula extraction accuracy (no engine produces these yet).

## Running

```bash
python benchmarks/run_benchmark.py
python benchmarks/run_benchmark.py --engine easyocr
```
