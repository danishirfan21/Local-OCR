# Remote Deep Analyze benchmark plan (not yet executed)

Companion to `docs/DEEP_PROVIDER_EVALUATION.md`. That document says what to
test and why; this document says exactly what would run, how much it would
cost at most, and what's needed before it's approved. **No request in this
plan has been made.** `local-lens benchmark-deep --dry-run` (built this
pass) runs everything up to but not including the actual network calls.

## Finalists (5, not "every available model")

Selected for diversity per the task's own guidance -- one strong
proprietary general VLM, one cheap proprietary VLM, PaddleOCR-VL remote
(mandatory, to actually answer whether self-hosting it is still worth it),
one strong hosted open VLM, and one adapter-diversity test case:

| # | Label | `LOCAL_LENS_DEEP_PROVIDER` | Model | Why this one |
|---|---|---|---|---|
| 1 | OpenAI GPT-5 | `openai-compatible` | `gpt-5` | Strong proprietary baseline; zero new adapter code |
| 2 | Gemini 2.5 Flash-Lite | `openai-compatible` (Gemini's OpenAI-compat beta endpoint) | `gemini-2.5-flash-lite` | Cheapest proprietary option; tests whether the beta OpenAI-compat layer holds up for OCR-shaped requests |
| 3 | PaddleOCR-VL-1.6 (self-hosted vLLM) | `paddle-vllm` | `PaddleOCR-VL-1.6` | The original candidate -- must stay in to answer "is self-hosting still worth it" with data, not assumption |
| 4 | Qwen2.5-VL-72B-Instruct (Fireworks AI) | `openai-compatible` | `accounts/fireworks/models/qwen2p5-vl-72b-instruct` | Strongest hosted-open-VLM catalog found (confirmed, not inferred); zero new adapter code |
| 5 | Claude Sonnet 5 | `anthropic` | `claude-sonnet-5` | Tests whether Anthropic's own explicit low-confidence/anti-hallucination vision guidance produces a measurably lower `extra_content_rate`; the one finalist that needed (and got) a dedicated adapter |

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
   none are configured in this environment (`local-lens providers`
   confirms Deep is currently unconfigured).
2. **A decision on where to run PaddleOCR-VL's vLLM server** -- Modal was
   the cleaner-documented managed-GPU option found this pass (first-party
   vLLM-container deploy guide, true per-second scale-to-zero billing);
   RunPod Serverless is the alternative. Either requires provisioning
   infrastructure, which this task was explicitly told not to do without
   separate approval.
3. **Explicit user approval to spend money** -- even though the token-
   billed total is small (well under $1), the task's own instructions are
   clear: no paid API request happens without approval, regardless of how
   small.

## Exact command that would execute the bake-off (NOT run in this session)

```bash
# 1. Configure each finalist's credentials (one at a time, or via
#    separate LOCAL_LENS_DEEP_* env files per finalist -- the current
#    config model supports one configured Deep provider at a time).
# 2. Then, once real execution is implemented (see "Not yet implemented" below):
local-lens benchmark-deep --run --output benchmarks_remote/results/
```

**Not yet implemented**: only `local-lens benchmark-deep --dry-run` exists
in this codebase. A real `--run` mode was deliberately not built this pass
-- building it would invite running it, and the task was explicit that no
paid request should happen without approval. Implementing `--run` is a
small, mechanical follow-up once finalists/keys are approved: loop over
`(finalist, case)` pairs, call `DeepAnalysisProvider.extract()`, score with
the metrics in `docs/DEEP_PROVIDER_EVALUATION.md` section 5, and write
sanitized results (see below) to `benchmarks_remote/results/`.

## Result archival (once execution is approved)

Planned location: `benchmarks_remote/results/<timestamp>/<finalist>/<case_id>.json`.

Must never contain: API keys, `Authorization`/`x-api-key` header values,
signed URLs, or any other credential (the same `redact_headers()` used in
production error paths should gate what gets written). Must contain: the
provider/model label, latency, HTTP status, the parsed `DocumentResult`
fields, and the computed metric values -- not raw request/response bodies
verbatim unless separately reviewed for secrets first.

## Do not run before approval

This plan intentionally stops here. No command in this file has been
executed. Running the real bake-off requires: the API keys above, a
provisioned PaddleOCR-VL endpoint (or dropping it from round one), the
small `--run` mode implemented, and the user's explicit go-ahead.
