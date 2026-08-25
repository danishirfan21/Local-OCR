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

## Finalists: Round 1 (free) and Round 2 (paid)

The plan is now free-first (see `docs/DEEP_PROVIDER_EVALUATION.md` section
0): before spending any of the approved $0.25, run the finalists whose
free tier is verified to require no payment method and has no documented
auto-billing mechanism. Canonical config for every finalist -- including
its `round` and `cost_classification` -- lives in
`local_lens/deep_analysis/finalists.py`.

### Round 1 -- free (estimated cost: $0.00, no payment method required)

| Label | Adapter | Model | Credential env var | Why this one |
|---|---|---|---|---|
| Groq Qwen3.6-27B | `OpenAICompatibleVisionProvider` (exact-match OpenAI shape, no new code) | `qwen/qwen3.6-27b` | `LOCAL_LENS_BENCHMARK_GROQ_API_KEY` | Confirmed by Groq's own docs: image input, OCR, document/chart understanding, multilingual, JSON Object Mode. Free tier requires no payment method; RPD 1,000 comfortably covers the 12-fixture corpus. |
| Gemini 3.1 Flash-Lite | `GeminiProvider` (native, not the OpenAI-compat beta layer) | `gemini-3.1-flash-lite` | `LOCAL_LENS_BENCHMARK_GEMINI_API_KEY` | Current-generation, non-deprecated successor to `gemini-2.5-flash-lite` (which is scheduled to retire no earlier than 2026-10-16). Free tier confirmed to require no billing account; billing needs a separate, explicit, manual action. |

Hugging Face Inference Providers was researched and deliberately **omitted
from Round 1**: only $0.10/month free credit, and exact per-request
pricing for the one genuinely distinct vision model found
(`Qwen/Qwen3-VL-8B-Instruct` via Featherless AI) couldn't be confirmed
from static docs -- see `docs/DEEP_PROVIDER_EVALUATION.md` section 0 for
the full reasoning.

### Round 2 -- paid ($0.25 hard ceiling, not executed without separate approval)

| # | Label | Adapter | Model | Credential env var | Why this one |
|---|---|---|---|---|---|
| 1 | OpenAI GPT-5 | `OpenAICompatibleVisionProvider` | `gpt-5` | `LOCAL_LENS_BENCHMARK_OPENAI_API_KEY` | Strong proprietary baseline; zero new adapter code |
| 2 | Qwen2.5-VL-72B-Instruct (Fireworks AI) | `OpenAICompatibleVisionProvider` | `accounts/fireworks/models/qwen2p5-vl-72b-instruct` | `LOCAL_LENS_BENCHMARK_FIREWORKS_API_KEY` | Strongest hosted-open-VLM catalog found (confirmed, not inferred); zero new adapter code |
| 3 | Claude Sonnet 5 | `AnthropicProvider` (dedicated -- Messages API confirmed non-OpenAI-compatible) | `claude-sonnet-5` | `LOCAL_LENS_BENCHMARK_ANTHROPIC_API_KEY` | Tests whether Anthropic's own explicit low-confidence/anti-hallucination vision guidance produces a measurably lower `extra_content_rate` |
| -- | PaddleOCR-VL-1.6 (remote vLLM) | none -- no endpoint provisioned | `PaddleOCR-VL-1.6` | none | **Excluded from execution in every round** (`executable_in_first_run=False`) -- listed so the comparison isn't silently missing it, not because it's runnable |

Round 2 is only worth running if Round 1's results don't already answer
"could Local Lens Deep Analyze ship against a free hosted vision API"
well enough on their own.

Model names/endpoints are recorded from documentation research
(`docs/DEEP_PROVIDER_EVALUATION.md`), not confirmed by a live API call
(that would itself be a request) -- if a model name has changed by
execution time, that finalist's requests will fail cleanly and it gets
dropped after repeated failures (see `docs/REMOTE_BENCHMARK_EXECUTION.md`
"Abort and drop conditions"), not silently substituted.

Deliberately excluded from both rounds, with reasons: Claude Opus 5/Fable 5
(too expensive to justify before cheaper Sonnet 5 data exists), Gemini 3.1
Pro (pricing wasn't confirmed in this research pass -- add once confirmed),
Mistral OCR (needs a new bespoke, non-OpenAI-compatible adapter -- worth a
future round if free/paid VLMs underperform on OCR fidelity specifically),
Azure/Google/AWS specialist OCR (off-target for arbitrary-screenshot use
case per the evaluation doc), OpenRouter (would just re-test Fireworks/
Together models through an extra hop -- redundant with Fireworks itself).

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

**Round 1 (free)**:

```
Finalists:              2  (Groq, Gemini)
Fixtures:               12
Requests per finalist:  12
Total requests:         24
Estimated maximum cost: $0.00 (both finalists are cost_classification=zero_cost_eligible --
                         their nominal per-token price is never counted toward --max-cost-usd
                         when --free-tier-only is set; see finalists.py's module docstring)
```

**Round 2 (paid, only if Round 1 doesn't already answer the product
question)**, unchanged from the original estimate:

```
Finalists:              3  (OpenAI, Fireworks, Anthropic)
Fixtures:               12
Requests per finalist:  12
Total requests:         36

OpenAI GPT-5              ~$0.075
Qwen2.5-VL-72B (Fireworks) ~$0.016
Claude Sonnet 5            ~$0.126
                           -------
Token-billed subtotal:     ~$0.22 maximum
```

PaddleOCR-VL is GPU-time-billed, not token-billed, and is excluded from
execution entirely (no endpoint provisioned) -- see
`docs/DEEP_PROVIDER_EVALUATION.md` section 1's PaddleOCR-VL notes.

**Total estimated maximum spend: $0.00 for Round 1; well under $0.25 for
Round 2 if it's ever run.**

## What's needed before this runs for real

**Round 1**: API keys for Groq and Gemini --
`local-lens benchmark-deep --preflight --round free` (zero network calls)
reports exactly which are currently configured; as of this pass, none are.
No spending approval is needed beyond the general acknowledgment that
free-tier usage still sends images to a third party (`--confirm-remote`
and `--free-tier-only` both required).

**Round 2** (if pursued later): API keys for OpenAI, Anthropic, and
Fireworks AI, plus explicit user approval to spend money -- `--run` will
not proceed without both `--confirm-remote` and `--max-cost-usd`.

PaddleOCR-VL is deliberately out of scope for every round -- it's excluded
in `finalists.py` (`executable_in_first_run=False`), so no GPU-provisioning
decision is needed to run either bake-off round. Provisioning a remote
PaddleOCR-VL endpoint (Modal was the cleaner-documented managed-GPU option
found in research; RunPod Serverless the alternative) remains a separate,
later decision if the results make it worth revisiting.

## Exact commands that would execute the bake-off (NOT run in this session)

```bash
# Round 1 (free) -- check first, zero network calls:
local-lens benchmark-deep --preflight --round free

# Configure Round 1 credentials:
export LOCAL_LENS_BENCHMARK_GROQ_API_KEY=...
export LOCAL_LENS_BENCHMARK_GEMINI_API_KEY=...

# Only after reviewing the preflight output with real credentials set:
local-lens benchmark-deep \
  --run \
  --round free \
  --confirm-remote \
  --free-tier-only \
  --max-cost-usd 0.00 \
  --output benchmarks_remote/results/
```

```bash
# Round 2 (paid, only if Round 1 warrants it) -- check first:
local-lens benchmark-deep --preflight --round paid

export LOCAL_LENS_BENCHMARK_OPENAI_API_KEY=...
export LOCAL_LENS_BENCHMARK_ANTHROPIC_API_KEY=...
export LOCAL_LENS_BENCHMARK_FIREWORKS_API_KEY=...

local-lens benchmark-deep \
  --run \
  --round paid \
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
