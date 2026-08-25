"""Command-line interface, built directly on OCRService -- no Streamlit
import anywhere in this module's import chain, so `local-lens ...` works
in a headless/server/CI context.

    local-lens extract image.png --mode fast
    local-lens extract image.png --mode deep --format json
    local-lens doctor
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from local_lens.backends import (
    deep_backend_status,
    fast_backend_statuses,
    legacy_local_deep_status,
    table_backend_status,
)
from local_lens.export import export_table_csv, export_table_markdown, to_json, to_markdown, to_txt
from local_lens.languages import DEFAULT_LANGUAGE
from local_lens.models import DocumentResult
from local_lens.preprocessing.image import PRESET_NONE
from local_lens.services.ocr_service import OCRService

_FORMATTERS = {
    "text": lambda r: r.text,
    "markdown": to_markdown,
    "json": to_json,
}


def _build_fast_service(engine_name: str) -> OCRService:
    from local_lens.tables.paddle_table_extractor import TABLE_EXTRACTION_AVAILABLE, PaddleTableExtractor

    table_extractor = PaddleTableExtractor() if TABLE_EXTRACTION_AVAILABLE else None

    if engine_name == "paddleocr":
        from local_lens.engines.paddleocr_engine import PADDLEOCR_AVAILABLE, PaddleOCREngine

        if not PADDLEOCR_AVAILABLE:
            raise SystemExit(
                "PaddleOCR is not installed. Install with:\n"
                "  pip install -r requirements-paddle.txt\n"
                "or use --engine easyocr (the default)."
            )
        return OCRService(PaddleOCREngine(), table_extractor=table_extractor)

    from local_lens.engines.easyocr_engine import EasyOCREngine

    return OCRService(EasyOCREngine(), table_extractor=table_extractor)


def _run_deep(image_path: Path, langs: list[str]) -> DocumentResult:
    from local_lens.deep_analysis.base import DeepAnalysisError
    from local_lens.deep_analysis.config import build_deep_provider
    from local_lens.services.ocr_service import OCRService as _OCRService

    provider = build_deep_provider()
    if provider is None:
        raise SystemExit(
            "Deep Analyze is not configured. Set LOCAL_LENS_DEEP_BASE_URL "
            "(and optionally LOCAL_LENS_DEEP_PROVIDER / LOCAL_LENS_DEEP_API_KEY / "
            "LOCAL_LENS_DEEP_MODEL) to enable it. See README.md 'Deep Analyze'."
        )

    service = _OCRService(provider)
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        return service.process(image_bytes, langs, PRESET_NONE)
    except DeepAnalysisError as exc:
        raise SystemExit(f"Deep Analyze failed: {exc}") from exc


def cmd_extract(args: argparse.Namespace) -> int:
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"error: no such file: {image_path}", file=sys.stderr)
        return 1

    langs = [args.lang] if args.lang else [DEFAULT_LANGUAGE]

    if args.mode == "deep":
        result = _run_deep(image_path, langs)
    else:
        service = _build_fast_service(args.engine)
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        result = service.process(image_bytes, langs, PRESET_NONE)

    if args.format in ("csv",) or (args.format is None and result.tables):
        fmt = args.format or "csv"
        if not result.tables:
            print("error: no table detected -- use --format text/markdown/json instead", file=sys.stderr)
            return 1
        table = result.tables[0]
        output = export_table_csv(table) if fmt == "csv" else export_table_markdown(table)
    else:
        fmt = args.format or "text"
        output = _FORMATTERS[fmt](result)

    print(output)
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    print("Fast mode (local):")
    for status in fast_backend_statuses():
        mark = "available" if status.available else status.reason or "not installed"
        print(f"  {status.name:<20} {mark}")

    table_status = table_backend_status()
    mark = "available" if table_status.available else table_status.reason or "not installed"
    print(f"  {'table_extraction':<20} {mark}")

    legacy = legacy_local_deep_status()
    mark = "installed" if legacy.available else "not installed (expected)"
    print(f"  {'paddleocr_vl_local':<20} {mark}")

    print("\nDeep Analyze (remote, BYOK):")
    deep = deep_backend_status()
    mark = f"configured ({deep.reason})" if deep.available else deep.reason or "not configured"
    print(f"  {deep.name:<20} {mark}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-lens", description="Local Lens command-line interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract", help="Run OCR/Deep Analyze on an image")
    extract.add_argument("image", help="Path to an image file")
    extract.add_argument("--mode", choices=["fast", "deep"], default="fast")
    extract.add_argument("--engine", choices=["easyocr", "paddleocr"], default="easyocr", help="Fast-mode engine")
    extract.add_argument("--format", choices=["text", "markdown", "json", "csv"], default=None)
    extract.add_argument("--lang", default=None, help=f"Language code (default: {DEFAULT_LANGUAGE})")
    extract.set_defaults(func=cmd_extract)

    doctor = subparsers.add_parser("doctor", help="Report which backends are available/configured")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
