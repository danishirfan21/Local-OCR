"""The real Deep Analyze bake-off executor -- preflight (zero network
calls) and the actual serial run (real network calls, gated behind
several deliberate safety checks before the first request).

This module is imported and unit-tested with a fake transport throughout
this project's development; it has never been invoked against a real
provider from this repository. See local_lens/cli.py's `benchmark-deep`
command for how a human triggers it (`--preflight`, `--dry-run`, or the
gated `--run --confirm-remote --max-cost-usd ...`).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from local_lens.deep_analysis.base import (
    DeepAnalysisAuthError,
    DeepAnalysisBadResponse,
    DeepAnalysisError,
)
from local_lens.deep_analysis.benchmark import estimate_request_cost
from local_lens.deep_analysis.benchmark_cases import build_deep_benchmark_cases
from local_lens.deep_analysis.deep_metrics import score_code_case, score_table_case, score_text_case
from local_lens.deep_analysis.finalists import (
    ESTIMATED_INPUT_TOKENS_PER_REQUEST,
    ESTIMATED_OUTPUT_TOKENS_PER_REQUEST,
    FINALISTS,
    build_provider_for_finalist,
    credential_configured,
    finalists_for_round,
)
from local_lens.deep_analysis.manifest import write_manifest
from local_lens.deep_analysis.sanitize import sanitize_error_message, sanitize_result_record

# Per-finalist consecutive-failure thresholds before that finalist is
# dropped from the rest of the run (the remaining finalists keep going --
# see PreflightReport/RunSummary docstrings for why this is "drop the
# finalist," not "abort everything," except where noted).
_MAX_CONSECUTIVE_AUTH_FAILURES = 2
_MAX_CONSECUTIVE_MALFORMED_RESPONSES = 3


class BudgetExceeded(Exception):
    pass


class NoExecutableFinalists(Exception):
    pass


# --- preflight (zero network calls) ---------------------------------------


@dataclass
class PreflightFinalist:
    label: str
    provider_kind: str
    model: str
    round: str
    cost_classification: str
    configured: bool
    executable: bool
    unavailable_reason: str | None
    requests: int
    nominal_cost_usd: float | None
    expected_actual_charge_usd: float | None
    within_free_tier_request_limit: bool | None = None


@dataclass
class PreflightReport:
    benchmark_version: str
    round: str
    fixture_count: int
    finalists: list[PreflightFinalist]
    total_executable_requests: int
    estimated_max_cost_usd: float
    warnings: list[str] = field(default_factory=list)


def run_preflight(env: dict | None = None, round_name: str | None = None) -> PreflightReport:
    """Zero network calls: only local config inspection + fixture
    materialization (the same lightweight PIL rendering `--dry-run` already
    does). `round_name`: "free", "paid", or None for all finalists
    regardless of round."""
    from local_lens.deep_analysis.manifest import BENCHMARK_VERSION

    cases = build_deep_benchmark_cases()
    finalists: list[PreflightFinalist] = []
    warnings: list[str] = []
    total_requests = 0
    total_cost = 0.0

    candidates = FINALISTS if round_name is None else finalists_for_round(round_name)

    for fc in candidates:
        configured = credential_configured(fc, env) if fc.credential_env_var else False
        executable = fc.executable_in_first_run and configured

        reason = None
        if not fc.executable_in_first_run:
            reason = "not executable in this run -- historical/local benchmark only, remote hosting pending"
        elif not configured:
            reason = f"not configured -- set {fc.credential_env_var}"

        requests = len(cases) if executable else 0
        nominal_cost = None
        expected_charge = None
        within_limit = None

        if executable:
            per_request = estimate_request_cost(
                fc.pricing, ESTIMATED_INPUT_TOKENS_PER_REQUEST, ESTIMATED_OUTPUT_TOKENS_PER_REQUEST
            )
            nominal_cost = round(per_request * requests, 4)
            total_requests += requests

            if fc.cost_classification in ("zero_cost_eligible", "likely_free"):
                # Nominal (this finalist's real published per-token rate,
                # recorded for transparency) is NOT the same as what this
                # account will actually be charged -- see finalists.py's
                # module docstring for why these are tracked separately.
                expected_charge = 0.0
                if fc.free_tier_limits is not None and fc.free_tier_limits.rpd is not None:
                    within_limit = requests <= fc.free_tier_limits.rpd
            else:
                expected_charge = nominal_cost
                total_cost += nominal_cost

        if executable and fc.provider_kind == "gemini":
            warnings.append(
                "Gemini: this benchmark cannot determine from configuration alone whether the configured API "
                "key is a free-tier (AI Studio) or paid-tier key. Google's documented policy differs sharply "
                "between them -- free-tier content may be used to improve products and may be human-reviewed; "
                "paid-tier is not used for training. Running this benchmark against a free-tier key is "
                "acceptable ONLY because every fixture is synthetic/rights-safe. Do not extend this same "
                "behavior to real user screenshots in the app without an explicit, tier-aware privacy "
                "disclosure in the UI first."
            )
        if executable and fc.provider_kind == "openai-compatible" and "groq" in (fc.base_url or "").lower():
            warnings.append(
                "Groq: free-tier data is not retained for inference requests by default and Groq's Services "
                "Agreement prohibits training on inputs/outputs without explicit permission -- see "
                "docs/DEEP_PROVIDER_EVALUATION.md. No payment method is required for the free tier."
            )

        finalists.append(
            PreflightFinalist(
                label=fc.label,
                provider_kind=fc.provider_kind,
                model=fc.model,
                round=fc.round,
                cost_classification=fc.cost_classification,
                configured=configured,
                executable=executable,
                unavailable_reason=reason,
                requests=requests,
                nominal_cost_usd=nominal_cost,
                expected_actual_charge_usd=expected_charge,
                within_free_tier_request_limit=within_limit,
            )
        )

    return PreflightReport(
        benchmark_version=BENCHMARK_VERSION,
        round=round_name or "all",
        fixture_count=len(cases),
        finalists=finalists,
        total_executable_requests=total_requests,
        estimated_max_cost_usd=round(total_cost, 4),
        warnings=warnings,
    )


# --- real execution (network calls) ----------------------------------------


@dataclass
class RequestResult:
    provider: str
    model: str
    case_id: str
    success: bool
    latency_ms: float
    http_status: int | None = None
    input_usage: int | None = None
    output_usage: int | None = None
    nominal_cost_usd: float | None = None
    estimated_cost_usd: float | None = None
    metrics: dict | None = None
    error: str | None = None


@dataclass
class RunSummary:
    run_id: str
    output_dir: Path
    manifest_path: Path
    results: list[RequestResult]
    dropped_finalists: dict[str, str]
    total_estimated_cost_usd: float
    aborted: bool
    abort_reason: str | None = None


def _score_case(case, doc_result) -> dict:
    text = doc_result.text or "\n".join(b.text for b in doc_result.blocks)
    if case.expected_table is not None:
        produced_rows = doc_result.tables[0].rows if doc_result.tables else []
        return {"kind": "table", **score_table_case(produced_rows, case.expected_table)}
    if case.category == "code":
        return {"kind": "code", **score_code_case(text, case.expected_text or "")}
    return {"kind": "text", **score_text_case(text, case.expected_text or "")}


def execute_benchmark(
    max_cost_usd: float,
    output_dir: Path,
    env: dict | None = None,
    confirm_remote: bool = False,
    round_name: str | None = None,
    free_tier_only: bool = False,
    provider_overrides: dict[str, object] | None = None,
) -> RunSummary:
    """Runs the real bake-off. `confirm_remote` is a belt-and-suspenders
    re-check -- the CLI layer already refuses to call this without
    `--confirm-remote`, but this function refuses too, so nothing else in
    the codebase can trigger a real run by calling it directly.

    `round_name`: "free", "paid", or None for every configured finalist
    regardless of round. `free_tier_only=True` is REQUIRED when
    `round_name == "free"` -- a second explicit acknowledgment (on top of
    `confirm_remote`) that this still sends images to a third party even
    though it's expected to cost nothing; it also changes cost accounting:
    zero_cost_eligible/likely_free finalists' nominal per-token cost is
    recorded for transparency but does NOT count against `max_cost_usd`
    (their real published pricing would otherwise make a strict $0.00
    ceiling impossible to satisfy even though the account will not
    actually be charged -- see finalists.py's module docstring). Paid
    finalists are never exempted from the ceiling, in any round.

    `provider_overrides`: {finalist_label: DeepAnalysisProvider} -- used
    exclusively by tests to inject a fake-transport provider instead of a
    real one. Never used by the CLI path.
    """
    if not confirm_remote:
        raise PermissionError("execute_benchmark called without confirm_remote=True -- refusing to proceed.")
    if round_name == "free" and not free_tier_only:
        raise PermissionError(
            "round_name='free' requires free_tier_only=True -- a free benchmark still sends images to a "
            "third party and must be explicitly acknowledged, even though it's expected to cost nothing."
        )

    preflight = run_preflight(env, round_name=round_name)
    if preflight.estimated_max_cost_usd > max_cost_usd:
        raise BudgetExceeded(
            f"Estimated maximum ${preflight.estimated_max_cost_usd:.4f} exceeds ceiling ${max_cost_usd:.4f}."
        )

    executable = [f for f in preflight.finalists if f.executable]
    if not executable:
        raise NoExecutableFinalists("No configured, executable finalists -- nothing to run.")

    finalist_by_label = {fc.label: fc for fc in FINALISTS}
    provider_overrides = provider_overrides or {}
    providers: dict[str, object] = {}
    for pf in executable:
        fc = finalist_by_label[pf.label]
        providers[pf.label] = provider_overrides.get(pf.label) or build_provider_for_finalist(fc, env)

    cases = build_deep_benchmark_cases()
    output_dir = Path(output_dir)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = output_dir / run_id
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = write_manifest(run_dir)

    from PIL import Image

    results: list[RequestResult] = []
    consecutive_auth: dict[str, int] = {pf.label: 0 for pf in executable}
    consecutive_malformed: dict[str, int] = {pf.label: 0 for pf in executable}
    dropped: dict[str, str] = {}
    accumulated_cost = 0.0
    aborted = False
    abort_reason: str | None = None

    active_labels = [pf.label for pf in executable]

    for case in cases:
        if aborted:
            break
        image = Image.open(case.image_path)

        for label in list(active_labels):
            if label in dropped:
                continue
            fc = finalist_by_label[label]
            provider = providers[label]

            t0 = time.monotonic()
            try:
                doc_result = provider.extract(image, case.languages or ["en"])
                latency_ms = (time.monotonic() - t0) * 1000
            except DeepAnalysisAuthError as exc:
                consecutive_auth[label] += 1
                result = RequestResult(
                    provider=label, model=fc.model, case_id=case.id, success=False,
                    latency_ms=(time.monotonic() - t0) * 1000,
                    error=sanitize_error_message(str(exc)),
                )
                results.append(result)
                if consecutive_auth[label] >= _MAX_CONSECUTIVE_AUTH_FAILURES:
                    dropped[label] = f"dropped after {_MAX_CONSECUTIVE_AUTH_FAILURES} consecutive auth failures"
                continue
            except DeepAnalysisBadResponse as exc:
                consecutive_malformed[label] += 1
                result = RequestResult(
                    provider=label, model=fc.model, case_id=case.id, success=False,
                    latency_ms=(time.monotonic() - t0) * 1000,
                    error=sanitize_error_message(str(exc)),
                )
                results.append(result)
                if consecutive_malformed[label] >= _MAX_CONSECUTIVE_MALFORMED_RESPONSES:
                    dropped[label] = (
                        f"dropped after {_MAX_CONSECUTIVE_MALFORMED_RESPONSES} consecutive malformed responses"
                    )
                continue
            except DeepAnalysisError as exc:
                result = RequestResult(
                    provider=label, model=fc.model, case_id=case.id, success=False,
                    latency_ms=(time.monotonic() - t0) * 1000,
                    error=sanitize_error_message(str(exc)),
                )
                results.append(result)
                continue

            consecutive_auth[label] = 0
            consecutive_malformed[label] = 0

            usage = doc_result.metadata.get("usage") or {}
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            if input_tokens is not None and output_tokens is not None:
                nominal_request_cost = estimate_request_cost(fc.pricing, input_tokens, output_tokens)
            else:
                nominal_request_cost = estimate_request_cost(
                    fc.pricing, ESTIMATED_INPUT_TOKENS_PER_REQUEST, ESTIMATED_OUTPUT_TOKENS_PER_REQUEST
                )

            if fc.cost_classification in ("zero_cost_eligible", "likely_free"):
                # Recorded for transparency (see RequestResult.metrics'
                # "nominal_cost_usd" below) but never counted toward the
                # ceiling -- this finalist's real billing is governed by
                # its free-tier request limits, not token pricing.
                cost = 0.0
            else:
                cost = nominal_request_cost
                accumulated_cost += cost

            metrics = _score_case(case, doc_result)

            result = RequestResult(
                provider=label,
                model=fc.model,
                case_id=case.id,
                success=True,
                latency_ms=round(latency_ms, 1),
                http_status=doc_result.metadata.get("http_status"),
                input_usage=input_tokens,
                output_usage=output_tokens,
                nominal_cost_usd=round(nominal_request_cost, 6),
                estimated_cost_usd=cost,
                metrics=metrics,
            )
            results.append(result)

            raw_record = sanitize_result_record(
                {
                    "provider": label,
                    "model": fc.model,
                    "case_id": case.id,
                    "metadata": doc_result.metadata,
                    "text": doc_result.text or "\n".join(b.text for b in doc_result.blocks),
                }
            )
            (raw_dir / f"{label.replace(' ', '_')}__{case.id}.json").write_text(
                json.dumps(raw_record, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
            )

            if accumulated_cost > max_cost_usd:
                aborted = True
                abort_reason = (
                    f"accumulated estimated cost ${accumulated_cost:.4f} exceeded ceiling ${max_cost_usd:.4f}"
                )
                break

        active_labels = [label for label in active_labels if label not in dropped]
        if not active_labels:
            aborted = True
            abort_reason = "every finalist was dropped (repeated auth/malformed-response failures)"
            break

    results_path = run_dir / "results.json"
    sanitized_results = [sanitize_result_record(r.__dict__) for r in results]
    results_path.write_text(json.dumps(sanitized_results, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = RunSummary(
        run_id=run_id,
        output_dir=run_dir,
        manifest_path=manifest_path,
        results=results,
        dropped_finalists=dropped,
        total_estimated_cost_usd=round(accumulated_cost, 4),
        aborted=aborted,
        abort_reason=abort_reason,
    )
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "dropped_finalists": dropped,
                "total_estimated_cost_usd": summary.total_estimated_cost_usd,
                "aborted": aborted,
                "abort_reason": abort_reason,
                "request_count": len(results),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary
