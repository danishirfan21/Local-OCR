# V5: Gemini becomes the production Deep Analyze backend

This document covers the production wiring that followed the Round 1
benchmark (`docs/DEEP_PROVIDER_RESULTS.md`). That document is the evidence;
this document is the resulting architecture, config, privacy model, failure
behavior, CLI semantics, and the reasoning for what was deliberately *not*
done.

## Benchmark-derived decision

Gemini (`gemini-3.1-flash-lite`) became the initial production Deep Analyze
backend because, measured (not assumed):

- 12/12 requests succeeded
- 12/12 valid structured JSON output, 0 malformed
- 0 hallucinated/invented content (`extra_content_rate` 0.0 across every
  fixture)
- Near-perfect OCR: CER 0.00 on 9/12 fixtures, with the remaining 3 fully
  explained (2 benign line-wrap artifacts, 1 genuine mixed-script
  word-order finding — see below)
- ~1.43s median benchmark latency (remote, over HTTPS)
- Table extraction was a major practical advantage over Fast mode's local
  pipeline (1.3s vs. 66.6s for the same accuracy, once the benchmark's own
  markdown-table scoring bug was fixed and re-verified)
- Zero-cost developer testing (free tier, no payment method required, no
  documented auto-billing mechanism)

Groq (`qwen/qwen3.6-27b`) produced **no usable data** — every request
failed with HTTP 403, most likely because the model's Preview status on
Groq requires an account-level enablement step beyond a valid API key. This
was not investigated further (out of scope for that task), and Groq is
**not** claimed to be worse than Gemini — there is simply no comparison to
make yet. Groq's benchmark support stays in the codebase, unused in
production, pending someone with Groq account access resolving the 403.

**This is not a claim of universal superiority.** Gemini's own results show
where Deep genuinely helps (tables, arguably code/Urdu/complex layouts) and
where it doesn't add value over Fast mode (plain clean text, where EasyOCR
is already excellent and Deep only adds network latency). The product UX
reflects that distinction deliberately — see "UX framing" below.

## Architecture

```
Local Lens
│
├── Fast
│   └── EasyOCR
│       ├── local
│       ├── offline
│       └── private
│
└── Deep Analyze
    └── Gemini 3.1 Flash-Lite
        ├── remote
        ├── BYOK
        └── explicit user action
```

- **Fast** is unchanged by this work: local EasyOCR (optionally PaddleOCR),
  zero network calls, always available, no configuration required.
- **Deep Analyze** is now Gemini-only in the production UI/CLI, frozen to
  `gemini-3.1-flash-lite` (`local_lens/deep_analysis/production.py`'s
  `PRODUCTION_GEMINI_MODEL`). The model is a deliberate, one-line,
  version-controlled choice — never `"latest"`, never silently upgraded by
  config. Changing it should mean a new benchmark round first.
- The `DeepAnalysisProvider` abstraction (`local_lens/deep_analysis/base.py`)
  is **not** deleted or narrowed — `OpenAICompatibleVisionProvider`,
  `AnthropicProvider`, and `PaddleVLLMProvider` all still exist, are still
  tested, and remain available for internal/advanced use via the older
  generic `LOCAL_LENS_DEEP_*` BYOK config
  (`local_lens/deep_analysis/config.py`). They are simply **not exposed as
  normal production UI/CLI choices** — the app and `local-lens extract
  --mode deep` only ever construct a `GeminiDeepProvider`. Extensibility
  without exposing "choose from 7 providers" before there's product need
  for it.

### Why a separate production provider class, not the benchmark adapter directly

`GeminiDeepProvider` (`local_lens/deep_analysis/production.py`) is a thin
subclass of `GeminiProvider` (the same HTTP adapter the benchmark used,
`local_lens/deep_analysis/gemini_provider.py`) with the model frozen and a
distinct `name`. No request/response logic was duplicated or forked --
production and benchmark share the exact HTTP code path that was actually
validated by 12 real requests. What's different is *configuration*:
production reads `LOCAL_LENS_GEMINI_API_KEY` (a dedicated env var, resolved
through `local_lens/env_file.py`'s real-env-then-`.env` precedence);
benchmark reads `LOCAL_LENS_BENCHMARK_GEMINI_API_KEY`. These are
intentionally never interchangeable — `local-lens providers` reports both
under clearly separate headings so one is never mistaken for the other.

## Privacy model

**Deep Analyze is never automatic.** The sequence is always:

```
image captured
↓
user chooses Deep Analyze (sidebar radio)
↓
privacy disclosure shown
↓
user explicitly clicks "Analyze remotely" / "Analyze with Gemini"
↓
remote request
```

No background Deep request, no speculative prefetch, no automatic
"helpful" cloud analysis. `tests/test_no_silent_network.py` and
`tests/test_production.py` enforce that importing the app, uploading an
image, switching modes (without clicking Analyze), and running Fast
extraction all make zero network calls.

**First-use disclosure** (shown every time Deep Analyze is selected with an
image present, not just the first time — re-stated per the task's
"always retain a visible remote/cloud indicator" requirement, not
persisted-forever consent):

> Deep Analyze sends this image to Google's Gemini API for processing.
> Google's free-tier API may use submitted content to improve products and
> may involve human review.

**Session-level button wording** changes after the first click in a session
(`st.session_state.deep_consent_given`) from "This image will be sent to
Gemini — Analyze remotely" to the shorter "Analyze with Gemini" — the
disclosure text itself stays visible regardless, so the cloud/remote nature
of the action is never hidden behind a shorter label.

**Free-tier vs. paid-tier**: Google's documented policy differs sharply
between the free Developer API tier (content may be used to improve
products, human review possible) and a paid/billed account (not used for
training) — see `docs/DEEP_PROVIDER_EVALUATION.md`. Local Lens cannot
determine this from the API key alone (no billing API is called). An
optional `LOCAL_LENS_GEMINI_TIER=free|paid` environment variable lets a
user state which applies to their account for more precise UI messaging;
unset defaults to conservative (assume-free-tier) messaging rather than
claiming privacy the app can't actually verify.

**The benchmark's own privacy story stays separate from production's**:
Round 1 used only synthetic, self-rendered, rights-safe fixtures — that
acceptability does not transfer to real user screenshots, which may
contain private information. This distinction is documented explicitly
here and in the README so it's never quietly elided because Gemini
performed well.

## Failure behavior

| Condition | UX |
|---|---|
| No key configured | "Deep Analyze requires a Gemini API key." |
| 401/403 | "Gemini rejected the configured API key." |
| 429 | "Gemini rate limit reached. Fast mode is still available." |
| Timeout | "Deep Analyze timed out. Your local Fast result is unaffected." |
| 5xx | Generic Deep Analyze failure message, provider-specific detail included |
| Malformed response | Same generic path — never crashes the Streamlit app |

**Deep failure never overwrites or hides the Fast result.** Fast always
runs automatically on image arrival (it's local and cheap) and is cached
per-image in `st.session_state`; Deep Analyze failing shows its own error
message in its own section, with the Fast result still visible (in its own
panel when Fast mode is selected, or in a "Fast result (local, already
computed)" expander when Deep mode is selected). The previous prototype's
"Deep unavailable, falling back to Fast" framing was removed on purpose —
presenting a Fast result as if it were a successful Deep result would
misrepresent what actually happened. Mode identity stays clear: if Deep
failed, the UI says Deep failed.

## Table, code, and Urdu/mixed-script handling

- **Tables**: a real structured preview (`st.dataframe`) plus CSV/Markdown/
  JSON export, not flattened to plain text. Multiple tables in one result
  are handled explicitly via a selector, not silently reduced to the first
  one. (Gemini represents a table as markdown in its reply text, not this
  project's own `TableResult` — `local_lens/deep_analysis/deep_metrics.py`'s
  `parse_markdown_table()`, found and fixed during the benchmark, is what
  makes structured table extraction from Gemini's replies possible at all;
  see `docs/DEEP_PROVIDER_RESULTS.md`'s "Parser fix" section.)
- **Code**: rendered in a dedicated code block (`st.code`, which includes a
  built-in copy affordance) rather than a plain text area, preserving
  indentation/punctuation/line breaks exactly as returned — Deep Analyze
  does not "fix" or explain code during extraction (interpretation is a
  possible future feature, not this one).
- **Urdu/mixed-script**: `OCRService.process()` applies the existing script
  detection and `normalize_urdu_text()` normalization uniformly regardless
  of which engine produced the text (Fast or Deep) — no special-casing
  needed, since `GeminiDeepProvider` returns a `DocumentResult` in the same
  shape as any other engine. `tests/test_production.py` includes regression
  fixtures built from the actual Round 1 responses, including the one real
  finding: Gemini swapped word order on the mixed Urdu/English fixture
  (`"Order نمبر 12345 confirmed"` → `"Order 12345 نمبر confirmed"`,
  content correct, order wrong) — the test asserts the parser doesn't
  introduce *further* reordering on top of whatever the model returns, since
  that's a model behavior to track, not a parsing bug to silently paper
  over.

## Configuration

```env
# Production Deep Analyze (Gemini only, frozen to gemini-3.1-flash-lite)
LOCAL_LENS_GEMINI_API_KEY=

# Optional -- affects only privacy messaging, not behavior
LOCAL_LENS_GEMINI_TIER=          # "free" | "paid" | unset (conservative default)
```

Resolution order: real process environment variable → project-local `.env`
→ not configured (`local_lens/env_file.py`). Never printed, logged, or
included in any exception message or stored result
(`local_lens/deep_analysis/sanitize.py` and provider-level redaction cover
this, verified by `tests/test_production.py`'s secret-non-exposure tests).

## CLI semantics

```bash
# Fast: always valid, no key, no flag, no internet.
local-lens extract screenshot.png --mode fast

# Deep: requires an explicit --allow-remote flag on top of a configured key,
# so a script can never unexpectedly upload an image.
local-lens extract screenshot.png --mode deep --allow-remote
# Without --allow-remote:
#   "Deep mode sends the image to Gemini. Re-run with --allow-remote."
```

`local-lens doctor` / `local-lens providers` distinguish three sections:
Fast (local backends), Deep (the one production Gemini provider), and
Benchmark (developer/CI-only `LOCAL_LENS_BENCHMARK_*` tooling) — a
benchmark credential being configured never makes `Deep / Gemini` report as
configured, and vice versa.

## Why PaddleOCR-VL was dropped (for now)

`docs/DEEP_PROVIDER_RESULTS.md`'s explicit conclusion:
`DROP SELF-HOSTED PADDLEOCR-VL FOR NOW`. Gemini's measured Round 1 latency
(median 1.4s) is categorically better than PaddleOCR-VL's historical local
latency (8-132s, from the V3/V4 audit), and Gemini's measured reliability
(12/12, 0 malformed) and table fidelity are strong. Self-hosting
PaddleOCR-VL would mean taking on GPU provisioning, cold starts, and
ongoing operational burden to compete with a provider that's already free,
fast, and reliable in this data. This is not a claim that PaddleOCR-VL is
categorically worse at OCR — its historical mixed-Urdu-English CER (0.12)
was the best of three engines measured in V3 — but the operational cost
isn't justified while a zero-cost hosted alternative already clears the
bar. `local_lens/engines/paddleocr_vl_engine.py` and the benchmark's
`PaddleVLLMProvider` remain in the codebase (historical/legacy, and ready
if this decision is revisited) but are not part of the production path,
and no production UI implies local Paddle is part of normal Local Lens
usage.

## What was explicitly not done in this pass

- No paid Round 2 benchmark (OpenAI, Anthropic, Fireworks) — Round 1's
  data didn't reveal a quality gap that would justify spending the
  approved budget on it.
- No multi-provider picker in the UI — architecture supports it, product
  need doesn't yet justify the UX complexity.
- No native desktop/Tauri work (separate future task).
- No Groq investigation beyond recording the 403 — worth revisiting with
  someone who has Groq account access, since the earlier research profile
  (fast, free, OpenAI-compatible) never actually got tested.
