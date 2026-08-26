"""Developer utility: validates a staged release-model source directory
before it's handed to `packaging/local_lens.spec` via
`LOCAL_LENS_RELEASE_MODEL_DIR` (V6.8's bundled-model release seam).

Checks, in order:
  1. All three required EasyOCR model files are present.
  2. Each file's SHA-256 matches the known-good hash recorded here (the
     hashes of the exact model files already installed in this project's
     development EasyOCR cache -- see docs/V6_7_PORTABLE_OPTIMIZATION.md
     and docs/V6_8_SELF_CONTAINED_RC.md for how they were computed).
  3. No unexpected `.pth` files are present in the directory (guards
     against accidentally staging an unrelated/extra weight file into a
     release build).

This module NEVER downloads anything -- it only reads files already on
disk. Packaging/development only: never imported by desktop/ or
local_lens/, stdlib only (hashlib for SHA-256).

Usage:
    .venv\\Scripts\\python.exe packaging\\validate_release_models.py D:\\LocalLensReleaseModels
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# Known-good SHA-256 hashes of the three required EasyOCR model files, as
# computed from this project's own development ~/.EasyOCR/model cache
# during V6.8. Update these only if you deliberately mean to accept a
# different (e.g. newer upstream) set of model weights -- never to paper
# over a validation failure.
REQUIRED_MODEL_HASHES: dict[str, str] = {
    "craft_mlt_25k.pth": "4a5efbfb48b4081100544e75e1e2b57f8de3d84f213004b14b85fd4b3748db17",
    "english_g2.pth": "e2272681d9d67a04e2dff396b6e95077bc19001f8f6d3593c307b9852e1c29e8",
    "arabic.pth": "2a9afd42c374deb98aed0b53c9b77d75e1d00d4e0501f3b0276c54190c89b1a8",
}


class ReleaseModelValidationError(Exception):
    """Raised when a staged release-model directory fails validation.
    Never caught silently by callers -- meant to fail the build loudly."""


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_release_model_dir(model_dir: Path) -> list[str]:
    """Validates `model_dir` against REQUIRED_MODEL_HASHES.

    Returns a list of human-readable "OK" lines on success. Raises
    ReleaseModelValidationError with a clear, actionable message on any
    failure (missing file, hash mismatch, or an unexpected extra .pth
    file present) -- it never partially succeeds or warns-and-continues.
    """
    if not model_dir.is_dir():
        raise ReleaseModelValidationError(f"Release model directory does not exist: {model_dir}")

    ok_lines: list[str] = []
    missing: list[str] = []
    mismatched: list[str] = []

    for filename, expected_hash in REQUIRED_MODEL_HASHES.items():
        file_path = model_dir / filename
        if not file_path.is_file():
            missing.append(filename)
            continue
        actual_hash = _sha256_of(file_path)
        if actual_hash != expected_hash:
            mismatched.append(f"{filename} (expected {expected_hash}, got {actual_hash})")
        else:
            ok_lines.append(f"OK  {filename}  sha256={actual_hash}")

    actual_pth_files = {p.name for p in model_dir.glob("*.pth")}
    unexpected = sorted(actual_pth_files - set(REQUIRED_MODEL_HASHES))

    if missing or mismatched or unexpected:
        problems: list[str] = []
        if missing:
            problems.append(f"missing required file(s): {', '.join(missing)}")
        if mismatched:
            problems.append(f"SHA-256 mismatch: {'; '.join(mismatched)}")
        if unexpected:
            problems.append(f"unexpected .pth file(s) present (not part of the required set): {', '.join(unexpected)}")
        raise ReleaseModelValidationError(
            f"Release model directory {model_dir} failed validation -- " + " | ".join(problems) +
            ". This validator never downloads models -- fix the staged directory's contents "
            "(re-copy from a known-good EasyOCR cache) and re-run validation before building."
        )

    return ok_lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_dir", type=Path, help="Path to a staged release-model directory, e.g. D:\\LocalLensReleaseModels")
    args = parser.parse_args()

    try:
        ok_lines = validate_release_model_dir(args.model_dir)
    except ReleaseModelValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    for line in ok_lines:
        print(line)
    print(f"All {len(ok_lines)} required model files validated OK in {args.model_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
