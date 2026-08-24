"""Ad-hoc PaddleOCR-VL smoke test. See README.md for methodology and results.

Not imported by local_lens/ or app.py -- this experiment is intentionally
isolated from the production path.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    from paddleocr import PaddleOCRVL

    t0 = time.time()
    pipeline = PaddleOCRVL(pipeline_version="v1.6")
    load_s = time.time() - t0
    print(f"load_time_s={load_s:.1f}")

    image_path = sys.argv[1] if len(sys.argv) > 1 else "sample.png"
    t0 = time.time()
    results = list(pipeline.predict(image_path))
    infer_s = time.time() - t0
    print(f"infer_time_s={infer_s:.1f}")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
