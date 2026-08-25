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
    fast_backend_statuses,
    legacy_local_deep_status,
    table_backend_status,
)
from local_lens.env_file import load_env
from local_lens.export import export_table_csv, export_table_markdown, to_json, to_markdown, to_txt
from local_lens.languages import DEFAULT_LANGUAGE
from local_lens.models import DocumentResult
from local_lens.preprocessing.image import PRESET_NONE
from local_lens.services.ocr_service import OCRService


def _resolve_env() -> dict:
    """Merges real process env vars with project-local `.env` (real env
    wins -- see load_env's docstring). Used for both production
    (LOCAL_LENS_GEMINI_API_KEY) and benchmark (LOCAL_LENS_BENCHMARK_*)
    credential resolution; never logs or prints anything from the result."""
    return load_env()


# Backward-compat alias -- some call sites read more clearly with this name.
_resolve_benchmark_env = _resolve_env


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
    from local_lens.deep_analysis.production import build_production_gemini_provider
    from local_lens.services.ocr_service import OCRService as _OCRService

    provider = build_production_gemini_provider(env=_resolve_env())
    if provider is None:
        raise SystemExit(
            "Deep Analyze requires a Gemini API key. Set LOCAL_LENS_GEMINI_API_KEY "
            "(directly or in a project-local .env) to enable it. See README.md 'Deep Analyze'."
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
        if not args.allow_remote:
            print(
                "Deep mode sends the image to Gemini. Re-run with --allow-remote.",
                file=sys.stderr,
            )
            return 1
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


def cmd_providers(_args: argparse.Namespace) -> int:
    """Offline configuration validation only -- never pings an endpoint.
    Deliberately three distinct sections: Fast (local), Deep (the one
    production Gemini provider), and Benchmark (developer/CI tooling,
    LOCAL_LENS_BENCHMARK_* credentials) -- keeping them visually separate
    is the whole point, so a benchmark credential is never mistaken for
    production config or vice versa."""
    from local_lens.deep_analysis.finalists import FINALISTS, credential_configured
    from local_lens.deep_analysis.production import production_gemini_status

    env = _resolve_env()

    print("Fast (local):")
    for status in fast_backend_statuses():
        mark = "available" if status.available else status.reason or "not installed"
        print(f"  {status.name:<12} {mark}")

    print("\nDeep (production, BYOK):")
    deep = production_gemini_status(env)
    mark = f"configured ({deep.reason})" if deep.available else deep.reason
    print(f"  Gemini       {mark}")

    print("\nBenchmark (developer/CI tooling -- LOCAL_LENS_BENCHMARK_*, separate from Deep above):")
    for fc in FINALISTS:
        if fc.credential_env_var is None:
            continue
        configured = credential_configured(fc, env)
        print(f"  {fc.label:<38} {'configured' if configured else 'not configured'}")

    return 0


def _cmd_benchmark_deep_dry_run() -> int:
    from local_lens.deep_analysis.benchmark import estimate_request_cost
    from local_lens.deep_analysis.benchmark_cases import build_deep_benchmark_cases
    from local_lens.deep_analysis.finalists import (
        ESTIMATED_INPUT_TOKENS_PER_REQUEST,
        ESTIMATED_OUTPUT_TOKENS_PER_REQUEST,
        PROPOSED_FINALISTS,
    )

    cases = build_deep_benchmark_cases()
    print("Deep Analyze benchmark -- DRY RUN (zero network calls)\n")
    print(f"Cases: {len(cases)}")
    missing = [c for c in cases if not c.image_path.exists()]
    for case in cases:
        exists = "ok" if case.image_path.exists() else "MISSING"
        gt = "text" if case.expected_text is not None else "table" if case.expected_table is not None else "none"
        print(f"  [{exists:7}] {case.category:12} {case.id:22} ground_truth={gt}")
    if missing:
        print(f"\nerror: {len(missing)} fixture image(s) missing -- run benchmarks/corpus.py's ensure_corpus() first")
        return 1

    print(f"\nCandidates: {len(PROPOSED_FINALISTS)}")
    total_requests = 0
    total_max_cost = 0.0
    for finalist in PROPOSED_FINALISTS:
        n_requests = len(cases)
        cost_per_request = estimate_request_cost(
            finalist.pricing, ESTIMATED_INPUT_TOKENS_PER_REQUEST, ESTIMATED_OUTPUT_TOKENS_PER_REQUEST
        )
        subtotal = round(cost_per_request * n_requests, 4)
        total_requests += n_requests
        total_max_cost += subtotal
        cost_note = (
            "GPU-time billed, not per-token -- see docs"
            if finalist.pricing.input_per_million == 0
            else f"~${subtotal:.4f} max"
        )
        print(f"  {finalist.label:38} {n_requests} requests, {cost_note}")

    print(f"\nTotal requests if fully executed: {total_requests}")
    print(f"Estimated maximum token-billed cost: ~${total_max_cost:.2f} (excludes GPU-time-billed candidates)")
    print("\nNo network call was made. See docs/REMOTE_BENCHMARK_PLAN.md for the full proposal and approval checklist.")
    return 0


def _cmd_benchmark_deep_preflight(args: argparse.Namespace) -> int:
    from local_lens.deep_analysis.runner import run_preflight

    round_name = args.round  # None | "free" | "paid"
    report = run_preflight(env=_resolve_benchmark_env(), round_name=round_name)
    print(f"Deep benchmark {report.benchmark_version} -- round: {report.round}\n")
    print(f"Fixtures: {report.fixture_count}\n")

    for f in report.finalists:
        print(f.label)
        print(f"  configured: {'yes' if f.configured else 'no'}")
        if not f.executable:
            print(f"  status: not executable ({f.unavailable_reason})")
            print()
            continue
        print(f"  requests: {f.requests}")
        print(f"  cost classification: {f.cost_classification.replace('_', ' ').upper()}")
        print(f"  nominal provider price: ${f.nominal_cost_usd:.4f}")
        if f.cost_classification in ("zero_cost_eligible", "likely_free"):
            print(f"  expected benchmark charge: ${f.expected_actual_charge_usd:.4f} (reason: {f.cost_classification.replace('_', ' ')} -- no payment method required)")
            if f.within_free_tier_request_limit is not None:
                print(f"  within free-tier daily request limit: {'yes' if f.within_free_tier_request_limit else 'NO -- would exceed documented RPD'}")
        else:
            print(f"  expected benchmark charge: ${f.expected_actual_charge_usd:.4f}")
        print()

    print(f"Total executable requests: {report.total_executable_requests}")
    print(f"Estimated maximum API cost (counted toward --max-cost-usd): ${report.estimated_max_cost_usd:.4f}")

    if report.warnings:
        print("\nWarnings:")
        for w in report.warnings:
            print(f"  - {w}")

    print("\nNo requests sent.")
    return 0


def _cmd_benchmark_deep_run(args: argparse.Namespace) -> int:
    if not args.confirm_remote:
        print("Remote benchmark execution requires --confirm-remote.\nNo requests were sent.", file=sys.stderr)
        return 1
    if args.max_cost_usd is None:
        print("Remote benchmark execution requires --max-cost-usd <ceiling>.\nNo requests were sent.", file=sys.stderr)
        return 1
    if args.round == "free" and not args.free_tier_only:
        print(
            "A free-round benchmark still sends images to a third party and requires --free-tier-only "
            "in addition to --confirm-remote, even though it's expected to cost nothing.\nNo requests were sent.",
            file=sys.stderr,
        )
        return 1

    from local_lens.deep_analysis.runner import BudgetExceeded, NoExecutableFinalists, execute_benchmark, run_preflight

    benchmark_env = _resolve_benchmark_env()
    preflight = run_preflight(env=benchmark_env, round_name=args.round)
    print(f"Estimated maximum: ${preflight.estimated_max_cost_usd:.4f}")
    print(f"Configured ceiling: ${args.max_cost_usd:.4f}\n")

    if preflight.estimated_max_cost_usd > args.max_cost_usd:
        print("ABORTED.\nNo requests sent.", file=sys.stderr)
        return 1

    print("Proceeding.\n")

    try:
        summary = execute_benchmark(
            max_cost_usd=args.max_cost_usd,
            output_dir=Path(args.output),
            env=benchmark_env,
            confirm_remote=True,
            round_name=args.round,
            free_tier_only=args.free_tier_only,
        )
    except NoExecutableFinalists as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except BudgetExceeded as exc:
        print(f"ABORTED: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Run id: {summary.run_id}")
    print(f"Results written to: {summary.output_dir}")
    print(f"Requests made: {len(summary.results)}")
    print(f"Total estimated cost: ${summary.total_estimated_cost_usd:.4f}")
    if summary.dropped_finalists:
        print("Dropped finalists:")
        for label, reason in summary.dropped_finalists.items():
            print(f"  {label}: {reason}")
    if summary.aborted:
        print(f"\nABORTED mid-run: {summary.abort_reason}")
        return 1
    return 0


def cmd_benchmark_deep(args: argparse.Namespace) -> int:
    modes_selected = sum([bool(args.dry_run), bool(args.preflight), bool(args.run)])
    if modes_selected == 0:
        print(
            "error: choose one of --dry-run, --preflight, or --run (with --confirm-remote --max-cost-usd). "
            "See docs/REMOTE_BENCHMARK_EXECUTION.md.",
            file=sys.stderr,
        )
        return 1
    if modes_selected > 1:
        print("error: choose only one of --dry-run, --preflight, --run.", file=sys.stderr)
        return 1

    if args.dry_run:
        return _cmd_benchmark_deep_dry_run()
    if args.preflight:
        return _cmd_benchmark_deep_preflight(args)
    return _cmd_benchmark_deep_run(args)


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

    from local_lens.deep_analysis.production import production_gemini_status

    print("\nDeep Analyze (production -- Gemini only, BYOK):")
    deep = production_gemini_status(_resolve_env())
    mark = f"configured ({deep.reason})" if deep.available else deep.reason
    print(f"  {'gemini':<20} {mark}")
    print("\n  (run `local-lens providers` for benchmark/developer-tooling credential status)")
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
    extract.add_argument(
        "--allow-remote",
        action="store_true",
        help="Required alongside --mode deep -- explicit acknowledgment that the image will be sent to Gemini.",
    )
    extract.set_defaults(func=cmd_extract)

    doctor = subparsers.add_parser("doctor", help="Report which backends are available/configured")
    doctor.set_defaults(func=cmd_doctor)

    providers = subparsers.add_parser(
        "providers", help="Validate Fast/Deep provider configuration (offline only, never pings an endpoint)"
    )
    providers.set_defaults(func=cmd_providers)

    benchmark_deep = subparsers.add_parser("benchmark-deep", help="Deep Analyze provider bake-off")
    benchmark_deep.add_argument(
        "--dry-run", action="store_true", help="Enumerate cases/candidates/cost estimate. Zero network calls."
    )
    benchmark_deep.add_argument(
        "--preflight",
        action="store_true",
        help="Report configured/executable finalists, request count, and max cost. Zero network calls.",
    )
    benchmark_deep.add_argument(
        "--run", action="store_true", help="Execute the real bake-off. Requires --confirm-remote and --max-cost-usd."
    )
    benchmark_deep.add_argument(
        "--confirm-remote",
        action="store_true",
        help="Required alongside --run -- acknowledges this will make real, potentially billable API calls.",
    )
    benchmark_deep.add_argument(
        "--max-cost-usd",
        type=float,
        default=None,
        help="Required alongside --run -- hard ceiling; execution refuses to start if the preflight estimate exceeds it.",
    )
    benchmark_deep.add_argument(
        "--output", default="benchmarks_remote/results", help="Output directory for --run (default: %(default)s)"
    )
    benchmark_deep.add_argument(
        "--round",
        choices=["free", "paid"],
        default=None,
        help="Restrict to Round 1 (free, zero-cost-eligible finalists) or Round 2 (paid). Default: all finalists.",
    )
    benchmark_deep.add_argument(
        "--free-tier-only",
        action="store_true",
        help="Required alongside --run --round free -- explicit acknowledgment that a free-cost run still sends "
        "images to a third party; also excludes zero-cost-eligible finalists' nominal price from --max-cost-usd.",
    )
    benchmark_deep.set_defaults(func=cmd_benchmark_deep)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
