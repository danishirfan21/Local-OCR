# Remote Deep Analyze benchmark: execution guide

Companion to `docs/REMOTE_BENCHMARK_PLAN.md` (what/why) and
`docs/DEEP_PROVIDER_EVALUATION.md` (provider research). This document is
the "how to actually run it" reference, written before any real request
has been made from this repository.

## Safety flags (all required for `--run`)

`local-lens benchmark-deep` has three mutually exclusive modes:

| Flag | Network calls | Purpose |
|---|---|---|
| `--dry-run` | zero | Enumerate fixtures + candidates + a flat cost estimate (pre-existing) |
| `--preflight` | zero | Report configured/executable finalists, exact request count, estimated maximum cost, and privacy warnings |
| `--run --confirm-remote --max-cost-usd <ceiling>` | **real** | Execute the bake-off |

`--run` alone does nothing -- both `--confirm-remote` and `--max-cost-usd`
are separately required, and the underlying `execute_benchmark()` function
itself refuses to run without an explicit `confirm_remote=True` argument
even if called directly from Python, not just through the CLI. This is
deliberate defense in depth: an absentminded `--run` does not spend money.

Before any request, the ceiling is checked against the preflight's
estimated maximum:

```text
Estimated maximum: $0.22
Configured ceiling: $0.25

Proceeding.
```

or

```text
Estimated maximum: $0.31
Configured ceiling: $0.25

ABORTED.
No requests sent.
```

During execution, the SAME ceiling is checked again after every single
request using that request's actual token usage (when the provider
reports it) or the conservative estimate otherwise -- if accumulated real
cost crosses the ceiling mid-run, the run stops immediately rather than
finishing the corpus. Partial results already written remain on disk;
`summary.json` records `aborted: true` and why.

## Provider setup

Credentials are read from dedicated environment variables -- separate from
the single-provider `LOCAL_LENS_DEEP_*` variables the app's Deep Analyze
mode uses, because the bake-off needs multiple providers configured
simultaneously:

```env
LOCAL_LENS_BENCHMARK_OPENAI_API_KEY=
LOCAL_LENS_BENCHMARK_GEMINI_API_KEY=
LOCAL_LENS_BENCHMARK_ANTHROPIC_API_KEY=
LOCAL_LENS_BENCHMARK_FIREWORKS_API_KEY=
```

See `.env.example`. A blank value, or an obvious placeholder (`changeme`,
`your-api-key`, `xxx`, etc.), is treated as **not configured** --
`local_lens/deep_analysis/finalists.py`'s `credential_configured()` never
reports a placeholder as real.

Model, endpoint, and pricing are fixed per finalist in
`local_lens/deep_analysis/finalists.py` -- there is no way to silently
substitute a different model at request time; if a configured model turns
out to be unavailable, that finalist's requests fail and it gets dropped
(see "Abort and drop conditions" below), it does not fall back to a
different model.

PaddleOCR-VL is present in the finalist registry but
`executable_in_first_run=False` -- it is never included in `--run`'s
executable set, regardless of credentials, because no GPU endpoint has
been provisioned. Its prior local measurements (`docs/V4_DIRECTION.md`)
remain the only evidence for it until that changes.

## Output structure

```text
benchmarks_remote/results/<run-id>/
├── manifest.json       # frozen fixture list: id, category, image/ground-truth sha256, languages
├── results.json        # one sanitized RequestResult per (finalist, case) pair
├── summary.json         # run-level: dropped finalists, total cost, aborted?, why
└── raw/
    └── <finalist>__<case_id>.json   # sanitized parsed response (metadata + text), per request
```

`<run-id>` is a UTC timestamp (`YYYYMMDDTHHMMSSZ`), so repeated runs never
collide. This whole directory is gitignored (`benchmarks_remote/results/`)
-- it's per-run local output, not something to commit.

**What "raw" means here**: the sanitized parsed `DocumentResult` metadata
and text for that request (provider, model, latency, HTTP status, token
usage, structured-response flag, extracted text) -- not literal wire-level
HTTP bytes. Capturing genuinely raw request/response bytes would require
deeper plumbing inside every provider adapter to smuggle the raw body back
out; this project chose the already-parsed-but-still-per-request record
instead, which is honest about what it is rather than calling something
"raw" that isn't.

**What never appears anywhere in output**: API keys, `Authorization`/
`x-api-key`/`x-goog-api-key` header values, or any request URL with an
embedded credential (`local_lens/deep_analysis/sanitize.py` actively
strips these -- it does not merely trust callers to have already done so).

## Reproducibility

`manifest.json` records the SHA-256 of every fixture image and its ground
truth, plus the frozen `benchmark_version` (`deep-v1`). If
`benchmarks/corpus.py` ever changes how a fixture renders, a new manifest
will show a different hash for that fixture's `image_sha256` -- so a
later comparison against an older run can detect "this wasn't actually the
same corpus" instead of silently assuming it was.

Execution order is deterministic and case-major (`case 1 -> every
finalist, case 2 -> every finalist, ...`), chosen over shuffling because
this is a small, one-shot benchmark, not a large statistical sample where
provider-order bias across many repeated runs would matter; case-major
also makes partial-run output easier to reason about (every finalist has
results for the same prefix of cases at any abort point). Execution is
strictly **serial** -- no concurrent requests -- for simpler cost
accounting, fewer rate-limit surprises, easier debugging, and a clean stop
point if something goes wrong.

## Abort and drop conditions

- **Cost ceiling exceeded** (upfront, from the preflight estimate, or
  mid-run, from accumulated actual/estimated cost) -- the whole run stops
  immediately.
- **A finalist hits 2 consecutive authentication errors** -- that finalist
  is dropped from the rest of the run; other finalists continue. If
  dropping leaves zero active finalists, the whole run stops.
- **A finalist hits 3 consecutive malformed/unparseable responses** -- same
  drop-then-check-if-any-remain behavior.
- Generic/transient errors (timeouts, rate limits, single server errors)
  are recorded as failed requests but do **not** drop or pause a finalist
  -- only sustained authentication or malformed-response problems do,
  since those indicate something structurally wrong (bad key, wrong
  endpoint/model) rather than a one-off blip.
- Every write to disk goes through `sanitize_result_record`/
  `sanitize_error_message` first, which actively strips known-sensitive
  keys rather than trusting the caller -- this is a safety net, not the
  primary control (the primary control is that no provider adapter ever
  puts a credential into a `DocumentResult` in the first place).

## Privacy notes

Deep Analyze's core privacy guarantee -- "nothing leaves the device
without an explicit Deep Analyze action" -- is preserved: only
`benchmark-deep --run` makes any request, and it requires two separate
explicit flags plus a cost ceiling. `--dry-run` and `--preflight` are
provably network-free (enforced by tests that monkeypatch
`urllib.request.urlopen` to raise if called).

**Gemini specifically**: `--preflight` and `--run` both surface an
explicit warning when a Gemini credential is configured, because Google's
documented policy differs sharply between the free/AI-Studio tier
(content may be used to improve products, human review possible) and the
paid tier (not used for training) -- see
`docs/DEEP_PROVIDER_EVALUATION.md`. This benchmark uses only synthetic,
rights-safe fixtures, which is the only reason running it against a
free-tier key is acceptable; **this same behavior must not be extended to
real user screenshots in the app's Deep Analyze mode** without a separate,
explicit, tier-aware privacy disclosure in the UI. Nothing in this
codebase currently does that distinction for the app's own Deep Analyze
mode -- it's called out here as a requirement for if/when Gemini is ever
wired into the app itself, not something already built.

## Exact execution steps (for when this is approved)

```bash
# 1. Set credentials for whichever finalists you want to include (a subset
#    is fine -- unconfigured finalists are simply excluded, not an error).
export LOCAL_LENS_BENCHMARK_OPENAI_API_KEY=...
export LOCAL_LENS_BENCHMARK_ANTHROPIC_API_KEY=...
# ... etc.

# 2. Confirm what would run and its cost, with zero network calls:
local-lens benchmark-deep --preflight

# 3. Only after reviewing that output, run for real:
local-lens benchmark-deep \
  --run \
  --confirm-remote \
  --max-cost-usd 0.25 \
  --output benchmarks_remote/results/
```

No step 3 has been executed as part of building this framework. See
`docs/REMOTE_BENCHMARK_PLAN.md`'s "Do not run before approval" section.
