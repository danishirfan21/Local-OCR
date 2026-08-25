"""Find where PaddleOCR-VL's recognition stage starts failing on elongated
single-line crops.

The V3 audit found that a ~31:1 aspect-ratio single-line crop returns empty
recognized content while layout detection still finds the block. This
script renders the same text at a fixed line height across a range of
aspect ratios and records where the failure begins, to inform the
threshold used by the production extreme-aspect mitigation in
local_lens/engines/paddleocr_vl_engine.py. Isolated from local_lens/ and
app.py -- experimental only.

Usage: python experiments/paddleocr_vl/aspect_ratio_experiment.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from PIL import Image, ImageDraw, ImageFont

TEXT = "This is a normal paragraph of extracted text used for the aspect ratio experiment."
LINE_HEIGHT = 56
ASPECT_RATIOS = [5, 10, 15, 20, 25, 30]
OUT_DIR = Path(__file__).resolve().parent / "aspect_ratio_samples"
RESULTS_PATH = Path(__file__).resolve().parent / "aspect_ratio_results.json"


def _render_at_ratio(ratio: float) -> Path:
    width = int(LINE_HEIGHT * ratio)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 26)
    img = Image.new("RGB", (width, LINE_HEIGHT), "white")
    draw = ImageDraw.Draw(img)
    draw.text((5, 10), TEXT, fill="black", font=font)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"ratio_{ratio}.png"
    img.save(path)
    return path


def _extract_content(page) -> str:
    blocks = page.get("parsing_res_list") or []
    return "\n".join(getattr(b, "content", "") or "" for b in blocks)


def main() -> None:
    from paddleocr import PaddleOCRVL

    pipeline = PaddleOCRVL(pipeline_version="v1.6")

    results = []
    for ratio in ASPECT_RATIOS:
        path = _render_at_ratio(ratio)
        t0 = time.time()
        pages = list(pipeline.predict(str(path)))
        elapsed = time.time() - t0
        content = _extract_content(pages[0]) if pages else ""
        layout_boxes = len((pages[0].get("layout_det_res") or {}).get("boxes", [])) if pages else 0
        record = {
            "aspect_ratio": ratio,
            "image_size": [int(LINE_HEIGHT * ratio), LINE_HEIGHT],
            "latency_s": round(elapsed, 2),
            "layout_boxes": layout_boxes,
            "content_empty": len(content.strip()) == 0,
            "content_preview": content[:80],
        }
        print(record)
        results.append(record)

    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults written to {RESULTS_PATH}")

    failing = [r["aspect_ratio"] for r in results if r["content_empty"]]
    succeeding = [r["aspect_ratio"] for r in results if not r["content_empty"]]
    print(f"Failing ratios: {failing}")
    print(f"Succeeding ratios: {succeeding}")


if __name__ == "__main__":
    main()
