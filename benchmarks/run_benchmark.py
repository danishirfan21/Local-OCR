#!/usr/bin/env python
"""Lightweight OCR engine benchmark harness.

Framework only, per the Local Lens roadmap -- not a tuned accuracy suite.
Runs each available engine over benchmarks/samples/ and reports latency plus
a rough word-overlap score against ground truth. See benchmarks/README.md
for how to add real samples and what this does/doesn't measure yet.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw

from local_lens.engines.easyocr_engine import EasyOCREngine
from local_lens.engines.paddleocr_engine import PADDLEOCR_AVAILABLE, PaddleOCREngine
from local_lens.services.ocr_service import OCRService

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
MANIFEST_PATH = SAMPLES_DIR / "manifest.json"

ENGINES = {
    "easyocr": EasyOCREngine,
}
if PADDLEOCR_AVAILABLE:
    ENGINES["paddleocr"] = PaddleOCREngine


def _ensure_sample_image(image_path: Path, ground_truth: str) -> None:
    """Generate a small synthetic image for a manifest entry if missing."""
    if image_path.exists():
        return
    lines = ground_truth.split("\n")
    width, line_height = 500, 40
    img = Image.new("RGB", (width, line_height * len(lines) + 20), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((10, 10 + i * line_height), line, fill="black")
    img.save(image_path)


def _word_overlap_score(predicted: str, ground_truth: str) -> float:
    """Naive, directional-only accuracy signal (not WER/edit-distance)."""
    pred_words = predicted.lower().split()
    gt_words = ground_truth.lower().split()
    if not gt_words:
        return 1.0 if not pred_words else 0.0
    matched = sum(1 for w in gt_words if w in pred_words)
    return matched / len(gt_words)


def run(engine_names: list[str]) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())
    for entry in manifest:
        _ensure_sample_image(SAMPLES_DIR / entry["image"], entry["ground_truth"])

    print(f"{'engine':<12} {'sample':<28} {'latency(s)':>10} {'word_overlap':>12}")
    print("-" * 66)
    for engine_name in engine_names:
        engine_cls = ENGINES[engine_name]
        service = OCRService(engine_cls())
        for entry in manifest:
            image_path = SAMPLES_DIR / entry["image"]
            image_bytes = image_path.read_bytes()

            start = time.perf_counter()
            result = service.process(image_bytes, ["en"], "none")
            elapsed = time.perf_counter() - start

            score = _word_overlap_score(result.text, entry["ground_truth"])
            print(f"{engine_name:<12} {entry['image']:<28} {elapsed:>10.2f} {score:>12.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine",
        choices=list(ENGINES.keys()),
        help="Run only this engine (default: all available engines)",
    )
    args = parser.parse_args()

    if not ENGINES:
        print("No OCR engines available.")
        return

    engine_names = [args.engine] if args.engine else list(ENGINES.keys())
    run(engine_names)


if __name__ == "__main__":
    main()
