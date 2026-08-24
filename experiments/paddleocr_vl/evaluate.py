"""Run PaddleOCR-VL over the benchmarks/ corpus and report the same metrics
run_benchmark.py uses for the production engines, for a like-for-like
comparison. Isolated from local_lens/ and app.py -- experimental only.

Usage: python experiments/paddleocr_vl/evaluate.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "benchmarks"))

from corpus import ensure_corpus, image_path_for  # noqa: E402
from metrics import (  # noqa: E402
    character_error_rate,
    normalized_similarity,
    table_structure_accuracy,
    word_error_rate,
)

RESULTS_PATH = Path(__file__).resolve().parent / "results.json"


def _extract_markdown_text(page) -> str:
    """Best-effort plain-text extraction from a PaddleOCR-VL page result.

    `page` is a paddlex PaddleOCRVLResult; its dict-like `page.get(...)`
    interface does not expose a top-level "text"/"markdown" string (that
    was an incorrect assumption in an earlier version of this script,
    confirmed wrong by inspecting a real result object). The actual
    recognized text lives in `page["parsing_res_list"]`, a list of
    PaddleOCRVLBlock objects each with a `.content` string -- this joins
    them in order for a like-for-like CER/WER comparison with the
    OCR-only engines, without claiming it's using the model's full
    structured/layout output.
    """
    blocks = page.get("parsing_res_list") or []
    return "\n".join(getattr(b, "content", "") or "" for b in blocks)


def main() -> None:
    from paddleocr import PaddleOCRVL

    print("Loading PaddleOCR-VL (v1.6)...")
    t0 = time.time()
    pipeline = PaddleOCRVL(pipeline_version="v1.6")
    load_s = time.time() - t0
    print(f"load_time_s={load_s:.1f}")

    corpus = ensure_corpus()
    records = []

    for entry in corpus:
        image_path = image_path_for(entry)
        start = time.perf_counter()
        try:
            results = list(pipeline.predict(str(image_path)))
            error = None
            text = "\n".join(_extract_markdown_text(p) for p in results)
        except Exception as exc:
            error = str(exc)
            text = ""
        elapsed_s = time.perf_counter() - start

        record = {
            "fixture": entry["id"],
            "category": entry["category"],
            "kind": entry["kind"],
            "latency_s": round(elapsed_s, 3),
            "error": error,
        }
        if not error and entry["kind"] == "text":
            gt = entry["text"]
            record["cer"] = round(character_error_rate(text, gt), 3)
            record["wer"] = round(word_error_rate(text, gt), 3)
            record["similarity"] = round(normalized_similarity(text, gt), 3)
            record["output_preview"] = text[:200]

        print(f"{entry['category']}/{entry['id']}: {record}")
        records.append(record)

    RESULTS_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "load_time_s": round(load_s, 1),
                "records": records,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nResults written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
