#!/usr/bin/env python
"""OCR engine benchmark harness over the synthetic corpus in benchmarks/corpus.py.

Framework only, per the Local Lens roadmap -- not a tuned accuracy suite,
and results depend heavily on how well the synthetic fixtures represent
real screenshots (see corpus.py's Urdu-rendering caveat in particular).
Writes machine-readable results to benchmarks/results/<timestamp>.json and
prints a human-readable summary.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import ensure_corpus, image_path_for
from metrics import (
    character_error_rate,
    normalized_similarity,
    table_structure_accuracy,
    word_error_rate,
)

from local_lens.engines.easyocr_engine import EasyOCREngine
from local_lens.engines.paddleocr_engine import PADDLEOCR_AVAILABLE, PaddleOCREngine
from local_lens.services.ocr_service import OCRService
from local_lens.tables.paddle_table_extractor import (
    TABLE_EXTRACTION_AVAILABLE,
    PaddleTableExtractor,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"

ENGINES = {"easyocr": EasyOCREngine}
if PADDLEOCR_AVAILABLE:
    ENGINES["paddleocr"] = PaddleOCREngine


def _make_service(engine_name: str) -> OCRService:
    engine = ENGINES[engine_name]()
    table_extractor = PaddleTableExtractor() if TABLE_EXTRACTION_AVAILABLE else None
    return OCRService(engine, table_extractor=table_extractor)


def run(engine_names: list[str]) -> list[dict]:
    corpus = ensure_corpus()
    records = []

    for engine_name in engine_names:
        service = _make_service(engine_name)
        for entry in corpus:
            image_path = image_path_for(entry)
            image_bytes = image_path.read_bytes()
            langs = ["ur", "en"] if entry["category"] in ("urdu", "mixed") else ["en"]

            start = time.perf_counter()
            try:
                result = service.process(image_bytes, langs, "none")
                error = None
            except Exception as exc:
                result = None
                error = str(exc)
            elapsed_s = time.perf_counter() - start

            record = {
                "engine": engine_name,
                "fixture": entry["id"],
                "category": entry["category"],
                "kind": entry["kind"],
                "latency_s": round(elapsed_s, 3),
                "error": error,
            }

            if result is not None:
                record["block_count"] = len(result.blocks)
                record["average_confidence"] = result.average_confidence
                if entry["kind"] in ("text", "transform"):
                    gt_text = entry["text"] if entry["kind"] == "text" else entry["base"]
                    record["cer"] = round(character_error_rate(result.text, gt_text), 3)
                    record["wer"] = round(word_error_rate(result.text, gt_text), 3)
                    record["similarity"] = round(normalized_similarity(result.text, gt_text), 3)
                else:
                    table_rows = result.tables[0].rows if result.tables else []
                    record["table_extraction_status"] = result.metadata.get("table_extraction_status")
                    record["table_accuracy"] = table_structure_accuracy(table_rows, entry["rows"])

            records.append(record)

    return records


def print_summary(records: list[dict]) -> None:
    print("\nBenchmark Summary")
    by_engine: dict[str, list[dict]] = {}
    for r in records:
        by_engine.setdefault(r["engine"], []).append(r)

    for engine_name, rows in by_engine.items():
        print(f"\n{engine_name}")
        for r in rows:
            if r["error"]:
                print(f"  - {r['category']}/{r['fixture']}: ERROR ({r['error']})")
            elif r["kind"] in ("text", "transform"):
                print(
                    f"  - {r['category']}/{r['fixture']}: "
                    f"CER={r['cer']:.2f} WER={r['wer']:.2f} sim={r['similarity']:.2f} "
                    f"latency={r['latency_s']:.2f}s"
                )
            else:
                acc = r["table_accuracy"]
                print(
                    f"  - {r['category']}/{r['fixture']}: "
                    f"rows_ok={acc['row_count_correct']} cols_ok={acc['column_count_correct']} "
                    f"cell_acc={acc['cell_accuracy']:.2f} status={r['table_extraction_status']} "
                    f"latency={r['latency_s']:.2f}s"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=list(ENGINES.keys()), help="Run only this engine")
    args = parser.parse_args()

    if not ENGINES:
        print("No OCR engines available.")
        return

    engine_names = [args.engine] if args.engine else list(ENGINES.keys())
    records = run(engine_names)
    print_summary(records)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{timestamp}.json"
    out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
