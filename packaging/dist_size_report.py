"""Developer utility: reports the largest top-level directories and files
inside a PyInstaller onedir output. Packaging/development only -- never
imported by desktop/ or local_lens/, and ships no external dependency
(stdlib only).

Usage:
    .venv\\Scripts\\python.exe packaging\\dist_size_report.py dist\\LocalLens
    .venv\\Scripts\\python.exe packaging\\dist_size_report.py dist\\LocalLens --top 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _dir_size(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


def _format_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def report(dist_dir: Path, top: int = 15) -> str:
    """Returns a formatted report string -- kept as a pure function
    (rather than printing directly) so tests/test_dist_size_report.py can
    assert on its content without invoking PyInstaller or capturing
    stdout."""
    internal = dist_dir / "_internal"
    scan_root = internal if internal.is_dir() else dist_dir

    entries: list[tuple[str, int]] = []
    for child in scan_root.iterdir():
        if child.is_dir():
            entries.append((child.name, _dir_size(child)))
        elif child.is_file():
            try:
                entries.append((child.name, child.stat().st_size))
            except OSError:
                pass

    entries.sort(key=lambda pair: pair[1], reverse=True)
    total = sum(size for _, size in entries)

    lines = [f"Largest contents of {scan_root} (top {top} of {len(entries)}):", ""]
    for name, size in entries[:top]:
        lines.append(f"  {name:<30} {_format_mb(size):>10}")
    lines.append("")
    lines.append(f"Total measured: {_format_mb(total)}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist_dir", type=Path, help="Path to a PyInstaller onedir output, e.g. dist\\LocalLens")
    parser.add_argument("--top", type=int, default=15, help="How many largest entries to show (default 15)")
    args = parser.parse_args()

    if not args.dist_dir.is_dir():
        print(f"Not a directory: {args.dist_dir}", file=sys.stderr)
        return 1

    print(report(args.dist_dir, top=args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
