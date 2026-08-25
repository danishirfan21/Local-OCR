# Remote Deep Analyze benchmark plan (execution framework built, not yet run)

Companion to `docs/DEEP_PROVIDER_EVALUATION.md` (what to test and why) and
`docs/REMOTE_BENCHMARK_EXECUTION.md` (exactly how to run it, once
approved). This document covers the finalists, corpus, and cost estimate.
**No request has been made.** The full execution framework --
`local_lens/deep_analysis/runner.py`, a dedicated Gemini adapter, canonical
per-finalist config, cost-ceiling enforcement, and `local-lens
benchmark-deep --preflight` / `--run` -- is now built and exercised only
against mocked transports in tests; nothing in this codebase has made a
real call to any of these providers.

## Finalists (5, not "every available model")

Selected for diversity per the task's own guidance -- one strong
proprietary general VLM, one cheap proprietary VLM, PaddleOCR-VL remote
(kept in the registry to answer whether self-hosting it is still worth it,
but excluded from execution -- see below), one strong hosted open VLM, and
one adapter-diversity test case. Canonical config for each lives in
`local_lens/deep_analysis/finalists.py`:

| # | Label | Adapter | Model | Credential env var | Why this one |
|---|---|---|---|---|---|
| 1 | OpenAI GPT-5 | `OpenAICompatibleVisionProvider` | `gpt-5` | `LOCAL_LENS_BENCHMARK_OPENAI_API_KEY` | Strong proprietary baseline; zero new adapter code |
| 2 | Gemini 2.5 Flash-Lite | `GeminiProvider` (native, not the OpenAI-compat beta layer) | `gemini-2.5-flash-lite` | `LOCAL_LENS_BENCHMARK_GEMINI_API_KEY` | Cheapest proprietary option; native adapter gives real `response_mime_type`/`usageMetadata` support instead of routing through Google's own beta compatibility shim |
| 3 | PaddleOCR-VL-1.6 (remote vLLM) | none -- no endpoint provisioned | `PaddleOCR-VL-1.6` | none | **Excluded from execution** (`executable_in_first_run=False`) -- listed so the comparison isn't silently missing it, not because it's runnable |
| 4 | Qwen2.5-VL-72B-Instruct (Fireworks AI) | `OpenAICompatibleVisionProvider` | `accounts/fireworks/models/qwen2p5-vl-72b-instruct` | `LOCAL_LENS_BENCHMARK_FIREWORKS_API_KEY` | Strongest hosted-open-VLM catalog found (confirmed, not inferred); zero new adapter code |
| 5 | Claude Sonnet 5 | `AnthropicProvider` (dedicated -- Messages API confirmed non-OpenAI-compatible) | `claude-sonnet-5` | `LOCAL_LENS_BENCHMARK_ANTHROPIC_API_KEY` | Tests whether Anthropic's own explicit low-confidence/anti-hallucination vision guidance produces a measurably lower `extra_content_rate` |

Model names/endpoints are recorded from documentation research
(`docs/DEEP_PROVIDER_EVALUATION.md`), not confirmed by a live API call
(that would itself be a request) -- if a model name has changed by
execution time, that finalist's requests will fail cleanly and it gets
dropped after repeated failures (see `docs/REMOTE_BENCHMARK_EXECUTION.md`
"Abort and drop conditions"), not silently substituted.

Deliberately excluded from the first round, with reasons: Claude Opus 5/
Fable 5 (too expensive to justify before cheaper Sonnet 5 data exists),
Gemini 3.1 Pro (pricing wasn't confirmed in this research pass -- add once
confirmed), Mistral OCR (needs a new bespoke, non-OpenAI-compatible
adapter -- worth a second round if round one shows general VLMs
underperform on OCR fidelity specifically), Azure/Google/AWS specialist
OCR (off-target for arbitrary-screenshot use case per the evaluation doc),
OpenRouter (would just re-test Fireworks/Together models through an extra
hop -- redundant with #4 in a first round).

## Benchmark corpus (12 fixtures, reused from the existing corpus)

`local_lens/deep_analysis/benchmark_cases.py` selects these from
`benchmarks/corpus.py` -- no new fixtures were created, all are already
rights-safe (self-rendered) and already have committed ground truth:

| id | category | what it tests |
|---|---|---|
| `short_ui_save` | short_ui | minimal short text, UI-label style |
| `paragraph` | english | realistic wrapped multi-line paragraph |
| `extreme_wide_line` | edge_cases | the ~31:1 aspect-ratio regression fixture that broke PaddleOCR-VL's recognition stage in V3 |
| `numeric` | english | pure numeric text |
| `python` | code | code extraction, indentation-sensitive |
| `typescript` | code | second programming language |
| `table_simple` | tables | basic row/column table |
| `table_dense` | tables | 4-column, 4-row table |
| `urdu_paragraph` | urdu | properly shaped Urdu (arabic_reshaper + bidi) |
| `mixed_urdu_english` | mixed | mixed-script line, reading-order sensitive |
| `table_financial` | tables | invoice/receipt-like: currency, negative values, percentages |
| `scan_clean` | photo_scan | synthetic photographed/scanned document (grayscale transform) |

Run `local-lens benchmark-deep --dry-run` to see this list validated live
against the actual materialized fixtures (all 12 confirmed present as of
this pass).

## Proposed execution scale

```
Finalists:              5
Fixtures:               12
Requests per finalist:  12
Total requests:         60
```

Estimated maximum cost (token-billed finalists only, at ~1,000 input /
~500 output tokens per request -- a conservative upper-bound assumption,
not a real usage measurement):

```
OpenAI GPT-5              ~$0.075
Gemini 2.5 Flash-Lite      ~$0.004
Qwen2.5-VL-72B (Fireworks) ~$0.016
Claude Sonnet 5            ~$0.126
                           -------
Token-billed subtotal:     ~$0.22 maximum
```

PaddleOCR-VL is GPU-time-billed, not token-billed -- its cost depends on
which serverless GPU host is chosen and is not estimated here (see
`docs/DEEP_PROVIDER_EVALUATION.md` section 1's PaddleOCR-VL notes for the
GPU footprint discussion). Standing up a scale-to-zero endpoint for a
60-image benchmark is very unlikely to be the dominant cost, but it does
require actually deploying a GPU server, which itself needs separate
approval (see below).

**Total estimated maximum bake-off cost: well under $1 for the four
API-based finalists; PaddleOCR-VL's cost depends on the hosting decision
and isn't included in that figure.**

## What's needed before this runs for real

1. **API keys** for OpenAI, Google (Gemini), Anthropic, and Fireworks AI --
   `local-lens benchmark-deep --preflight` (zero network calls) reports
   exactly which of these are currently configured; as of this pass, none
   are.
2. **Explicit user approval to spend money** -- even though the token-
   billed total is small (well under $1), no paid API request happens
   without approval, regardless of how small. `--run` itself will not
   proceed without both `--confirm-remote` and `--max-cost-usd`.

PaddleOCR-VL is deliberately out of scope for this first executable round
entirely -- it's excluded in `finalists.py`
(`executable_in_first_run=False`), so no GPU-provisioning decision is
needed to run the first bake-off. Provisioning a remote PaddleOCR-VL
endpoint (Modal was the cleaner-documented managed-GPU option found in
research; RunPod Serverless the alternative) remains a separate, later
decision if the first round's results make it worth revisiting.

## Exact command that would execute the bake-off (NOT run in this session)

```bash
# 1. Check what's configured and what it would cost -- zero network calls:
local-lens benchmark-deep --preflight

# 2. Configure whichever finalists' credentials you want included:
export LOCAL_LENS_BENCHMARK_OPENAI_API_KEY=...
export LOCAL_LENS_BENCHMARK_GEMINI_API_KEY=...
export LOCAL_LENS_BENCHMARK_ANTHROPIC_API_KEY=...
export LOCAL_LENS_BENCHMARK_FIREWORKS_API_KEY=...

# 3. Only after reviewing step 1's output again with real credentials set:
local-lens benchmark-deep \
  --run \
  --confirm-remote \
  --max-cost-usd 0.25 \
  --output benchmarks_remote/results/
```

Full detail on flags, output structure, abort conditions, and privacy
handling: `docs/REMOTE_BENCHMARK_EXECUTION.md`.

## Result archival

`benchmarks_remote/results/<run-id>/` -- `manifest.json` (frozen corpus
with per-fixture hashes), `results.json` (one sanitized result per
request), `summary.json` (run-level outcome), `raw/<finalist>__<case_id>
.json` (sanitized parsed response per request). Every write passes through
`local_lens/deep_analysis/sanitize.py`, which actively strips API keys,
`Authorization`/`x-api-key`/`x-goog-api-key` header values, and any
credential-shaped URL query parameter -- not merely trusts callers to have
already removed them. This whole directory is gitignored.

## Do not run before approval

This plan intentionally stops here. No command in this file has been
executed. The execution framework is fully built and tested against mocked
transports; running it for real requires: the API keys above and the
user's explicit go-ahead via `--run --confirm-remote --max-cost-usd ...`.
