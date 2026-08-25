# Deep Analyze provider results — Round 1 (free)

## Benchmark environment

| | |
|---|---|
| Benchmark date | 2026-08-25 |
| Benchmark version | `deep-v1` |
| Repository commit used | `6999066` (code fix landed at execution time — see "Parser fix" below) |
| Run id | `20260825T063527Z` (second/final run — see "Parser fix") |
| Corpus | 12 frozen fixtures, `benchmarks/corpus.py`, hashes recorded in `benchmarks_remote/results/<run-id>/manifest.json` |
| Providers attempted | Groq (`qwen/qwen3.6-27b`), Gemini (`gemini-3.1-flash-lite`) |
| Round | Free (`--round free --free-tier-only --max-cost-usd 0.00`) |
| Execution | Serial, one request at a time, no concurrency |
| Total requests sent | 14 (2 Groq, attempted and failed; 12 Gemini, all successful) |
| Actual spend | **$0.00** |

## Parser fix found during execution (documented, not hidden)

The first run (`20260825T063222Z`) completed successfully for Gemini but its
table-fixture scores were wrong: every provider adapter represents a table
as markdown text inside the reply (per the shared `prompts.py` schema),
not as this project's own `TableResult` structure — `DocumentResult.tables`
is only ever populated by the local PaddleOCR table pipeline. The
benchmark's `_score_case()` was reading `doc_result.tables[0].rows`, which
was always empty for every remote provider, so every table fixture scored
as a total failure regardless of what the model actually returned.

This was caught by inspecting the first successful sanitized responses
(`table_simple`, `table_dense`) before trusting aggregate scores, per the
project's own evaluator-validation discipline (the same discipline that
caught a real PaddleOCR-VL extraction bug during V3). Fix: added
`parse_markdown_table()` (`local_lens/deep_analysis/deep_metrics.py`) as a
fallback source of table rows when `doc_result.tables` is empty, with a
regression test built from the *actual* captured Gemini responses. Per the
task's own instruction not to mix scoring pipelines inside one result set,
the entire round was **re-run from fixture 1** for both providers after the
fix landed — all results in this document are from run
`20260825T063527Z`, scored with one consistent parser version.

## Providers and exact model IDs

| Provider | Model ID | Result |
|---|---|---|
| Groq | `qwen/qwen3.6-27b` | **Failed — HTTP 403 on every attempt** |
| Gemini | `gemini-3.1-flash-lite` | Completed, 12/12 successful |

## Groq: what happened

Both attempted requests (`short_ui_save`, `paragraph`) returned **HTTP
403 Forbidden** from `https://api.groq.com/openai/v1`. The runner's
consecutive-auth-failure safeguard correctly dropped Groq from the rest of
the run after 2 failures rather than burning through the full corpus
against a broken credential. This happened identically on both the first
and second (post-fix) run — a reproducible failure, not a transient blip.

**Most likely cause** (not confirmed, since diagnosing further would
require additional requests that weren't part of the approved scope):
`qwen/qwen3.6-27b` is marked **Preview** status in Groq's own docs
(console.groq.com/docs/model/qwen/qwen3.6-27b) — preview models on Groq
sometimes require explicit account-level access/waitlist acceptance
distinct from a general API key having valid auth. A 403 (forbidden) is
consistent with "authenticated but not authorized for this specific
model," as opposed to a 401 (which would indicate the key itself is
rejected outright). No workaround was attempted — per the task's explicit
instruction not to route around access restrictions by switching accounts
or otherwise circumventing the provider's decision.

**This is itself a real, useful finding**: even a provider with a
confirmed-in-docs, OpenAI-compatible, genuinely free-tier vision model can
still be operationally unusable without an extra, undocumented enablement
step. That's relevant to "API simplicity" as an evaluation criterion in
its own right.

## Gemini: aggregate results (12/12 successful)

| Metric | Value |
|---|---|
| Requests successful | 12/12 |
| Structured JSON responses | 12/12 |
| Empty/malformed responses | 0/12 |
| Median latency | 1,430 ms |
| Mean latency | 1,610 ms |
| Fastest | 1,157 ms (`mixed_urdu_english`) |
| Slowest | 2,860 ms (`paragraph`) |
| p95 | not computed — 12 samples is too few for a meaningful p95; treat the max as the honest outlier instead |
| Total input tokens | 17,996 |
| Total output tokens | 1,392 |
| Actual charge | **$0.00** |
| Composite score (weights below) | **0.9934** |

## Full per-fixture result table

| Category | Fixture | Gemini 3.1 Flash-Lite | Groq Qwen3.6-27B |
|---|---|---:|---:|
| Short UI | `short_ui_save` | CER 0.00, exact match ("Save") | not attempted — dropped after fixture 2 |
| English paragraph | `paragraph` | CER 0.0182 (line-wrap artifact only, see below) | HTTP 403 |
| Extreme-wide edge | `extreme_wide_line` | CER 0.00, exact match | not attempted |
| Numbers | `numeric` | CER 0.00, exact match | not attempted |
| Python code | `python` | CER 0.00, byte-exact, indentation preserved | not attempted |
| TypeScript code | `typescript` | CER 0.00, byte-exact, indentation preserved | not attempted |
| Simple table | `table_simple` | cell accuracy 1.00, 3×3 exact | not attempted |
| Dense table | `table_dense` | cell accuracy 1.00, 5×4 exact | not attempted |
| Urdu | `urdu_paragraph` | CER 0.00, exact match | not attempted |
| Mixed Urdu/English | `mixed_urdu_english` | CER 0.3846, WER 0.50 — **word-order swap**, see below | not attempted |
| Receipt/document | `table_financial` | cell accuracy 1.00, 3×3 exact | not attempted |
| Photo/scan | `scan_clean` | CER 0.0154 (line-wrap artifact only) | not attempted |
| Reliability | — | 12/12 | 0/2 attempted |
| Median latency | — | 1,430 ms | — |
| Cost | — | $0 | $0 |

**"Line-wrap artifact"** (`paragraph`, `scan_clean`): Gemini's transcription
is word-for-word correct; the only CER cost comes from reproducing the
image's visual line breaks as literal `\n` characters where the ground
truth string uses a single unbroken line. This is arguably *more* faithful
to the image, not a content error — flagged here rather than silently
excluded so the number isn't misread as a real transcription mistake.

**Word-order swap** (`mixed_urdu_english`): ground truth is `"Order نمبر
12345 confirmed"`; Gemini returned `"Order 12345 نمبر confirmed"` — the
Urdu word and the number were swapped. Every character was transcribed
correctly (the CER/WER cost is purely reordering), but this is a genuine
mixed-script reading-order fidelity issue, not a transcription error. This
is exactly the kind of finding the corpus was designed to surface.

## Evaluation metrics — definitions used

- **CER/WER**: Levenshtein edit distance over characters/words, normalized
  by ground-truth length (`benchmarks/metrics.py`, unchanged from Fast-mode
  benchmarking — same functions, not reimplemented).
- **Normalized similarity**: `difflib.SequenceMatcher` ratio, case/
  whitespace-insensitive.
- **extra_content_rate**: fraction of produced words absent from the
  ground-truth word multiset — a coarse extraction-fidelity/hallucination
  proxy, not a semantic hallucination detector (see `benchmark.py`).
- **Table row/column/cell accuracy**: exact structural and cell-text match
  against ground truth, via `table_structure_accuracy()`.
- **Code metrics**: CER, line-count similarity, indentation preservation
  (per-line leading-whitespace match), punctuation/symbol-multiset overlap
  (`deep_metrics.py`, new this pass).
- **Composite score**: weighted blend, defined next.

## Composite score and weights

```text
Extraction fidelity     30%   (similarity vs. ground truth, penalized by extra_content_rate)
Tables                  20%   (mean cell accuracy)
Code                    15%   (mean indentation preservation)
Urdu/multilingual       15%   (not separately broken out this round -- see below)
Reliability             10%   (successful-request rate)
Latency                  5%   (0s -> 1.0, 30s+ -> 0.0, linear)
Cost                     5%   ($0 -> 1.0, $0.01/request+ -> 0.0)
```

**Individual metrics are shown above in full, not hidden behind this
number** — per the task's own instruction, a single composite must never
stand in for the category breakdown. With only Gemini having any
successful data this round, the composite (**0.9934**) reflects Gemini
alone; Groq has no composite (0 successful requests, nothing to average).
The "Urdu/multilingual" weight slot is currently folded into the general
extraction-fidelity component in this implementation (both `urdu_paragraph`
and `mixed_urdu_english` are scored as `kind: text` like any other text
fixture) rather than broken out as a separate weighted term — worth a
follow-up if Urdu-specific comparisons become a recurring priority.

## Category winners

With only one provider producing any successful data, "winners" mostly
reduce to "Gemini, by default — Groq has no data to compare." Stated
explicitly rather than glossed over:

- **Best short screenshot OCR**: Gemini (only data point) — perfect.
- **Best general OCR**: Gemini (only data point) — near-perfect, with one
  reordering artifact.
- **Best code transcription**: Gemini (only data point) — byte-exact on
  both fixtures, no "helpful" rewriting observed.
- **Best table extraction**: Gemini (only data point) — perfect cell
  accuracy on all three table fixtures.
- **Best Urdu**: Gemini (only data point) — exact match on the pure-Urdu
  fixture.
- **Best mixed Urdu/English**: Gemini (only data point) — correct content,
  one word-order swap.
- **Best photo/scan**: Gemini (only data point) — correct content, minor
  line-wrap artifact.
- **Best structured-response reliability**: Gemini, 12/12 valid structured
  JSON responses, 0 malformed.
- **Fastest provider**: Gemini, median 1,430 ms (Groq never produced a
  timed successful response to compare).
- **Best overall extraction fidelity**: Gemini.

No genuine head-to-head comparison was possible this round — this is a
finding about Groq's accessibility, not a quality judgment against it.

## Qualitative observations (measured findings only)

- Gemini's transcription is essentially perfect on clean, short, and
  moderately complex synthetic fixtures (UI text, paragraphs, numbers,
  code, tables) — CER 0.00 on 9 of 12 fixtures, with the remaining 3
  explained by a benign line-wrap artifact (2 fixtures) and one genuine
  mixed-script reordering issue (1 fixture).
- Gemini did not "help" — no invented headings, no code reformatting, no
  paraphrasing, no explanatory commentary anywhere in the 12 responses.
  `extra_content_rate` was 0.0 on every text/code fixture. This matters
  specifically because the anti-hallucination prompt (`prompts.py`) was
  designed to suppress exactly this failure mode, and it appears to have
  worked.
- The one real content defect found (mixed Urdu/English word-order swap)
  is a legitimate, narrow finding about bidi/reading-order handling, not a
  broad accuracy problem.
- Groq could not be evaluated on quality at all — its only observable
  behavior this round was a consistent, fast (~100ms) HTTP 403 rejection.

## Comparison with Fast mode (EasyOCR)

Historical EasyOCR measurements exist for 4 of these 12 fixtures
(`short_ui_save`, `paragraph`, `numeric`, `table_simple`) from
`benchmarks/results/20260824T221555Z.json` (a V3-era run — the underlying
fixture text content for these IDs is unchanged since then, but the
run predates later corpus changes such as paragraph re-wrapping, so this
is contextual reference, not a controlled identical-image comparison; no
new local benchmark sweep was run for this pass, per the task's own
instruction):

| Fixture | EasyOCR (local) | Gemini (remote) |
|---|---|---|
| `short_ui_save` | CER 0.00, latency 6.9s (cold) | CER 0.00, latency 1.5s |
| `paragraph` | CER 0.018, latency 1.5s | CER 0.0182, latency 2.9s |
| `numeric` | CER 0.00, latency 0.4s | CER 0.00, latency 1.9s |
| `table_simple` | cell accuracy 1.00, **latency 66.6s** (full pipeline incl. local table extractor) | cell accuracy 1.00, latency 1.3s |

**Reading this honestly**: on plain clean text, EasyOCR (once warm) is
already excellent and often faster than a network round-trip to Gemini —
Fast mode's own accuracy is not the bottleneck for these categories. The
one place Deep clearly wins on this limited overlap is **table
extraction**: Fast mode's local table pipeline took 66.6 seconds end-to-
end for a 3×3 table, vs. Gemini's 1.3 seconds, for the same cell accuracy.
Deep also covers categories Fast mode's committed results don't include at
all in this comparison set: code fidelity, Urdu, mixed-script, and
photo/scan — where Gemini's results this round were strong.

## Comparison with historical PaddleOCR-VL (V3/V4, contextual only)

From `docs/V4_DIRECTION.md`'s committed V3/V4 audit measurements — **not a
controlled comparison with this round**: different execution environment
(local CPU vs. remote GPU-backed API), and critically, the historical Urdu
fixtures had a **known shaping defect** (unjoined Arabic letterforms,
fixed later via `arabic_reshaper`) that this round's Urdu fixtures do not
have — so any Urdu CER improvement between then and now conflates fixture
quality with model quality and must not be read as "Gemini beats
PaddleOCR-VL at Urdu."

| Category | PaddleOCR-VL (historical, local) | Gemini (this round, remote) |
|---|---|---|
| Short UI text | CER 1.00 (total failure on one variant) | CER 0.00 |
| English paragraph | CER 1.00 (empty output, root-caused extreme-aspect-ratio bug) | CER 0.0182 |
| Code | CER 0.22, WER 0.00, loses indentation | CER 0.00, indentation preserved |
| Tables | ran OK, **never scored for structure** | cell accuracy 1.00 (now scored, thanks to this round's parser fix) |
| Mixed Urdu/English | CER 0.12 (best of 3 engines at the time) | CER 0.3846 — **but ground-truth fixture quality differs, not comparable** |
| Warm latency (paragraph) | 8-50s | 2.9s (single sample) |
| Warm latency (code) | 132s | ~2s |

The historical PaddleOCR-VL data point that *is* fairly read across both
rounds: **latency**. Even accounting for local-CPU-vs-remote-GPU being an
unfair comparison in PaddleOCR-VL's favor (a real deployment would be
GPU-backed and faster than these CPU numbers), an 8-132 second local
latency is categorically different from Gemini's ~1-3 second remote
latency. That gap is unlikely to close even with a well-tuned remote
PaddleOCR-VL deployment, given the model's own architecture.

## Failure analysis

- **Groq (2/2 failed)**: HTTP 403, root cause not confirmed (see above),
  but not a parser or evaluator problem — the failure occurred entirely at
  the HTTP layer, before any response body existed to parse.
- **Gemini (0/12 failed)**: no failures to analyze.
- **Parser bug found and fixed during this pass** (see "Parser fix"
  section above) — the only code defect discovered, and it was caught by
  the evaluator-validation step before being allowed to contaminate final
  results, per the task's explicit instruction.

## Answering the product question

> Does Deep Analyze meaningfully improve over local EasyOCR for the kinds
> of inputs Local Lens targets?

**Partially, and unevenly** — not a blanket "yes." On plain clean text
(short UI labels, simple paragraphs, numbers), EasyOCR is already
excellent and the remote round-trip adds latency without adding accuracy.
Deep's clearest, most defensible win in this data is **table extraction
speed** (66.6s local vs. 1.3s remote for identical accuracy) and coverage
of categories Fast mode doesn't handle as an integrated pipeline (code
fidelity, Urdu, photo/scan) — though this round only has one working
provider to judge those on, not a competitive comparison. This is not
strong enough evidence to claim Deep categorically beats Fast; it's
evidence that Deep adds real value in specific categories (tables,
possibly code/Urdu) while adding no value and extra latency in others
(plain short text).

## Paid Round 2 decision

```text
PAID ROUND 2 NOT CURRENTLY JUSTIFIED
```

Gemini's Round 1 results are strong enough (composite 0.9934, 12/12
reliable, near-zero cost) that spending any of the approved $0.25 budget
to test OpenAI/Anthropic/Fireworks isn't justified by this data alone —
Round 1 didn't reveal a quality gap paid providers would need to close.
The stronger open question is fixing Groq's access issue (a config/account
problem, not a quality question) and re-testing it for real head-to-head
data, which costs nothing and doesn't require Round 2's budget at all.

## PaddleOCR-VL decision

```text
DROP SELF-HOSTED PADDLEOCR-VL FOR NOW
```

Gemini's measured Round 1 latency (median 1.4s) is categorically better
than PaddleOCR-VL's historical local latency (8-132s), and Gemini's
measured reliability (12/12, 0 malformed) and table-structure fidelity
(now actually scored, thanks to this round's fix) are strong. Self-hosting
PaddleOCR-VL would mean taking on GPU provisioning, cold starts, and
ongoing operational burden to compete with a provider that's already free,
fast, and reliable in this data. This isn't a claim that PaddleOCR-VL is
worse at OCR in principle — its historical mixed-Urdu-English CER (0.12)
was actually the best of three engines measured in V3 — but the
operational cost of self-hosting isn't justified when a zero-cost hosted
alternative already clears the bar this well. Revisit only if a future
round finds a category where hosted options measurably underperform.

## Recommended Local Lens Deep architecture

Given only one provider has usable data, the honest recommendation is
narrower than "pick a winner":

- **Initial Deep backend**: Gemini (`gemini-3.1-flash-lite`), pending Groq's
  access issue being resolved (see below) — Gemini alone already clears
  the bar for a usable default: fast, reliable, accurate, genuinely
  zero-cost on the free tier.
- **Single-provider BYOK, not configurable-multi-provider**, for the
  initial release — the architecture already supports multiple providers
  (this benchmark proves it), but shipping one well-tested default is
  simpler UX and there isn't yet evidence that offering a provider picker
  to end users adds value over one solid default. Revisit if/when Groq
  (or another candidate) produces genuinely differentiated results.
- **Groq's 403 needs a human, not more benchmark code**: someone with
  access to the Groq account should check whether `qwen/qwen3.6-27b`
  (Preview status) requires an explicit opt-in/waitlist step in the Groq
  console. This is worth resolving before writing Groq off — the earlier
  research suggested a genuinely attractive profile (fast, free, OpenAI-
  compatible) that this round never actually got to test.

## Privacy caveat (production, not benchmark)

**Benchmark privacy**: acceptable as executed — all 12 fixtures are
synthetic, self-rendered, rights-safe images; no real user screenshot or
personal content was ever sent to either provider.

**Production privacy, if Gemini becomes the default**: Google's documented
policy differs sharply between tiers (`docs/DEEP_PROVIDER_EVALUATION.md`,
`ai.google.dev/gemini-api/terms`) — the **free tier** may use submitted
content to improve Google's products and may be reviewed by humans; the
**paid tier** is not used for training. This benchmark ran against
whichever tier the configured API key belongs to (not confirmable from
configuration alone — see the preflight warning). Before Gemini is wired
into the production Deep Analyze feature for real user screenshots, the
UI must disclose this tier distinction explicitly rather than presenting
Deep Analyze uniformly as "sent to your configured provider." This is not
hidden because Gemini performed well in this benchmark — it is exactly why
it needs to be said plainly now, before any production wiring happens.
