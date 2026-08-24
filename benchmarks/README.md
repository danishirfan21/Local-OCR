# Local Lens benchmark harness

A corpus + harness for comparing OCR engines (and, separately, table
extraction). Still a framework more than a tuned suite -- see "Known
limitations" below before reading too much into any single number.

## Layout

```
benchmarks/
├── README.md
├── corpus.py           # fixture definitions + synthetic image generation
├── metrics.py           # CER, WER, normalized similarity, table accuracy
├── run_benchmark.py     # CLI: runs configured engines over the corpus
├── samples/
│   ├── english/          paragraph, numeric, English+numbers
│   ├── urdu/              pure Urdu text, Urdu+numbers
│   ├── mixed/             Urdu+English mixed line
│   ├── short_ui/          "Save", "Cancel Settings OK"
│   ├── tables/             simple 3x3, dense 5x4
│   ├── code/               a short Python snippet
│   └── documents/          (reserved for future longer/multi-paragraph fixtures)
├── ground_truth/         mirrors samples/, one .json per fixture (committed)
└── results/               one timestamped .json per run (committed selectively)
```

Images under `samples/` are regenerated on demand from `corpus.py`'s
`CORPUS` list (they're gitignored) -- `ground_truth/` is committed since
it's small, human-readable text/table data.

## Corpus

All fixtures are synthetic (rendered via PIL) -- nothing copyrighted or
private, so the whole corpus is safe to commit and regenerate. Covers, at
minimum: short UI text, a paragraph, pure numbers, English+numbers, a code
snippet, a simple table, a dense table, pure Urdu text, Urdu+numbers, and a
mixed Urdu/English line.

**Known limitation -- Urdu fixture quality:** this environment's Pillow
build has no `raqm` text-shaping support (checked via
`PIL.features.check("raqm")`), so the Urdu fixtures render Arabic-script
glyphs in **isolated letterforms**, not properly joined Nastaliq/Naskh
script. Treat Urdu benchmark numbers here as "does the pipeline handle
Arabic-script Unicode end-to-end," not "how accurate is this on realistic
Urdu screenshots" -- for the latter you'd need a real screenshot or a
shaping-capable renderer (e.g. Pillow built with `libraqm`, or a browser
screenshot).

## Metrics

- **CER / WER**: Levenshtein edit distance over characters/words,
  normalized by ground-truth length. 0.0 = perfect.
- **Normalized similarity**: `difflib.SequenceMatcher` ratio, case/
  whitespace-insensitive, in [0, 1].
- **Latency**: wall-clock seconds per fixture per engine (includes
  preprocessing + reconstruction + classification, i.e. the full
  `OCRService.process()` call, not just raw engine inference).
- **Table fixtures** are scored separately: row-count match, column-count
  match, and cell-text accuracy (case-insensitive exact match per cell,
  only over the overlapping region if predicted/ground-truth dimensions
  differ).
- **Block count** and **average confidence** are recorded but not scored
  against anything -- informational only.

## What this still does not measure

- Memory usage per engine.
- A real accuracy comparison on Urdu (see the fixture-quality caveat
  above).
- Layout/reading-order preservation on genuinely multi-column input (no
  such fixture exists yet).
- Anything about PaddleOCR-VL -- that's a separate track, see
  `experiments/paddleocr_vl/`.

## Running

```bash
python benchmarks/run_benchmark.py                # all available engines
python benchmarks/run_benchmark.py --engine easyocr
```

Prints a human-readable summary and writes `benchmarks/results/<UTC timestamp>.json`.
