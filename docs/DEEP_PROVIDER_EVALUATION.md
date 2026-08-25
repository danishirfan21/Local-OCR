# Deep Analyze provider evaluation

Research-only pass (August 2026): no remote provider was called, no
infrastructure was provisioned, no Paddle was reinstalled. This document
answers "what should we test," not "what won" -- per the task's own
instruction, a winner is only declared after real benchmark data exists
(see `docs/REMOTE_BENCHMARK_PLAN.md` for the not-yet-executed bake-off).

All findings below came from live documentation research this session
(WebSearch/WebFetch against each provider's current official docs). Claims
are marked **confirmed** (found explicitly in current official docs),
**likely** (reasonable inference, not explicitly stated), or **unknown**
(not found, not guessed). Source URLs are inline.

## 1. Candidate landscape

### OpenAI

- **Current vision-capable models**: GPT-5 family (GPT-5, GPT-5-mini,
  GPT-5-nano), GPT-4o / GPT-4o-mini. GPT-4.1 does **not** accept image
  input (text only) -- confirmed, easy to assume wrong. [Images and
  vision](https://developers.openai.com/api/docs/guides/images-vision)
- **API surface**: the Responses API is now OpenAI's recommended path
  (`input_image` content type); Chat Completions' `image_url` block (what
  our `OpenAICompatibleVisionProvider` already sends) is still supported,
  just the legacy surface, not the newest-feature-first one. Our adapter
  works against OpenAI unmodified either way. [Migration
  guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- **Structured output**: `response_format: {"type": "json_schema",
  "strict": true}` (Structured Outputs, recommended over plain JSON mode).
- **Pricing** (per 1M tokens): GPT-5-nano $0.05/$0.40 (cheapest); GPT-4o-mini
  $0.15/$0.60; GPT-5 $1.25/$10.00; GPT-4o $2.50/$10.00. [Pricing](https://developers.openai.com/api/docs/pricing)
- **Image tokenization**: tile-based on GPT-4o family (85 base tokens +
  170/tile); patch-based on GPT-5.4+ (32x32px patches x model coefficient).
  `detail: "original"` preserves full resolution for OCR on GPT-5.4+.
- **Data retention/training**: API data not used for training by default
  (opt-in only, since March 2023); ~30-day default retention; Zero Data
  Retention available for approved enterprise customers. [Enterprise
  privacy](https://openai.com/enterprise-privacy/)
- **Documented OCR limitation**: docs explicitly warn non-Latin-alphabet
  text (example given: Japanese/Korean) "may not perform optimally." **No
  mention of Urdu/Arabic anywhere** -- unknown, not found in docs.

### Anthropic (Claude)

- **Current vision-capable models**: full lineup vision-capable -- Opus 5,
  Sonnet 5, Haiku 4.5 (cheapest), Fable 5 (most capable). [Vision
  docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- **API surface**: genuinely **not** OpenAI-compatible -- confirmed, not
  assumed. Image content block is `{"type":"image","source":{"type":
  "base64","media_type":"image/png","data":...}}` vs. OpenAI's
  `{"type":"image_url","image_url":{"url":...}}` -- different field names
  and nesting. Auth is `x-api-key` + `anthropic-version` headers, not
  `Authorization: Bearer`. **This is why Local Lens now has a dedicated
  `AnthropicProvider`** (`local_lens/deep_analysis/anthropic_provider.py`)
  rather than forcing it through the generic adapter.
- **Structured output**: `messages.parse()` / forced `tool_use` with a
  schema; no direct `response_format` equivalent.
- **Pricing** (per 1M tokens): Haiku 4.5 $1.00/$5.00 (cheapest); Sonnet 5
  $3.00/$15.00; Opus 5 $5.00/$25.00; Fable 5 $10.00/$50.00.
- **Image tokenization (exact documented formula)**: `tokens =
  ceil(width/28) x ceil(height/28)`, tiled in 28x28px patches. Standard tier
  (pre-4.7 models): max 1568 visual tokens. High-res tier (4.7+ models,
  automatic): max 4784 visual tokens.
- **Data retention/training**: images are "ephemeral... not stored beyond
  the duration of the API request," auto-deleted after processing; not
  used for training. [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision)
- **Documented OCR limitation** (unusually explicit -- exactly the kind of
  honesty this project's own prompt tries to elicit): Claude "might
  hallucinate or make mistakes when interpreting low-quality, rotated, or
  very small images under 200 pixels"; spatial/coordinate output is
  "approximate"; heavy JPEG compression is called out as harmful to
  dense-text tasks specifically. **No Urdu-specific claim found** --
  unknown.

### Google Gemini

- **Current vision-capable models**: Gemini 3.1 Pro (flagship), 3.7 Flash /
  3.6 Flash (balanced), 3.5 Flash-Lite / 3.1 Flash-Lite (cheap); legacy
  2.5 Flash-Lite ($0.10/$0.40, cheapest found, but **deprecates 2026-10-16**
  -- don't build a benchmark around a model retiring in two months).
  [Models](https://ai.google.dev/gemini-api/docs/models)
- **API surface**: Google runs a genuine OpenAI-compatible endpoint
  (`https://generativelanguage.googleapis.com/v1beta/openai/`) --
  **confirmed live**, our generic adapter should work with a base-URL/model
  swap. Google's own docs flag it as **"still in beta while we extend
  feature support"** -- a real caveat, not a blocker. Native API uses a
  different structured-output mechanism (`response_mime_type` +
  `response_schema`) than the OpenAI-compat layer's `response_format`.
  [OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)
- **Pricing**: see above; promo pricing $0.75/$3.75 (3.6/3.7 Flash) through
  2026-12-31, standard $1.50/$7.50 after.
- **Image tokenization**: 258 tokens if <=384px both dims, else tiled into
  768x768 tiles at 258 tokens/tile. Native PDF support: ~258 tokens/page,
  up to 1000 pages/request.
- **Data retention/training -- the sharpest split found across all
  providers**: **free tier (AI Studio)**: "Google uses the content you
  submit... to provide, improve, and develop Google products... human
  reviewers may read, annotate, and process your API input and output" --
  explicitly told not to submit sensitive data. **Paid tier**: "Google
  doesn't use your prompts... or responses to improve our products." EEA/
  Switzerland/UK users are required onto the paid tier. [Gemini API
  terms](https://ai.google.dev/gemini-api/terms) -- **this materially
  affects Deep Analyze's privacy messaging if Gemini is ever the default**:
  free-tier Gemini must never be silently used for a privacy-positioned
  feature.
- **Urdu/OCR benchmarks**: not found in official docs -- unknown.

### Hosted open VLMs (serverless marketplaces)

| Provider | Serverless? | OpenAI-compatible? | Named OCR/doc-VLM catalog | Pricing basis |
|---|---|---|---|---|
| **Fireworks AI** | Yes | Yes | **Confirmed**: Qwen2-VL (2B/72B), Qwen2.5-VL (3B/7B/32B/72B), InternVL3 | Per-token, ~$0.14-$3/M |
| **OpenRouter** | Yes (aggregator) | Yes, single endpoint for 400+ models/70+ providers | Re-exposes Fireworks/Together/DeepInfra/HF | Per-token + 5.5% platform fee, no other markup |
| Together AI | Yes | Yes | Qwen3-VL-32B, Llama-3.2-90B-Vision | Per-token, e.g. $0.50/$1.50 |
| DeepInfra | Yes | Yes | Unclear which VLMs by name -- not found in docs | Per-token, tiered (Flex/Standard/Priority) |
| HF Inference Providers | Yes | Yes (`router.huggingface.co/v1`) | Llama-3.2-Vision, Qwen2-VL-72B, InternVL2 (routed) | Per-token, no HF markup |
| Groq | Yes | Yes | Only one vision model (Qwen3.6-27B) -- thin catalog | Not published in docs found |
| Replicate | Per-second GPU | **No** -- own prediction API | Individual community models exist, none verified by name | Per-second: T4 $0.000225/s, A100-80GB $0.0014/s |
| Modal | General serverless GPU | N/A -- bring your own container | You self-host (e.g. PaddleOCR-VL) | Per-second: A100-80GB ~$2.50/hr, H100 ~$3.95/hr |
| RunPod Serverless | Yes, scale-to-zero | N/A -- bring your own container | You self-host | Per-second GPU + $0.025-$0.076/cold-start |
| Baseten | Both modes | Unclear for Model APIs | Not confirmed by name | Per-token (serverless) or per-instance (dedicated) |

**Strongest single candidate: Fireworks AI** -- the only marketplace with a
confirmed, *named* catalog of exactly the OCR/document-VLM families worth
testing (Qwen2.5-VL family, InternVL3), genuinely serverless, and slots
into the existing generic adapter with zero new code (base URL + model
name change only).

**Best hedge: OpenRouter** -- one integration, many backends, transparent
fee -- worth keeping in mind for production redundancy, not needed for the
initial bake-off since it would just re-test Fireworks/Together models
through an extra hop.

### PaddleOCR-VL remote hosting

- **Two distinct server paths exist** (this matters, and is easy to get
  wrong): (1) PaddleOCR's own `genai_server` Docker wrapper
  (`paddleocr genai_server --model_name PaddleOCR-VL-1.6-0.9B --backend
  vllm`), the officially documented pairing for
  `vl_rec_backend="vllm-server"`; (2) raw upstream `vllm serve
  PaddlePaddle/PaddleOCR-VL --trust-remote-code ...`, documented directly
  by the vLLM project, which exposes a **standard OpenAI-compatible
  `/v1/chat/completions` endpoint any generic HTTP client can call** --
  this is the path `PaddleVLLMProvider` targets. [vLLM
  recipe](https://docs.vllm.ai/projects/recipes/en/stable/PaddlePaddle/PaddleOCR-VL.html)
- **Client-side dependency, precisely**: driving PaddleOCR's *full pipeline*
  (layout detection, reading order, table structure) with only VL
  recognition offloaded still needs `paddlex`/`paddleocr` installed
  locally for the pre/post-processing stages -- that's the mode we
  deliberately avoid. Talking directly to a raw `vllm serve` endpoint
  (bypassing PaddleOCR's own orchestration) needs **no local Paddle
  install** -- confirmed for this path specifically, not "confirmed for
  the full pipeline via a remote backend" (that combination wasn't
  verifiable from the docs fetched).
- **GPU footprint**: model is ~0.9B params; ~2GB VRAM cited by third-party
  GPU-recommender sites; one HF discussion reports 40GB+ used on an A100 in
  practice, likely from vLLM's default memory pre-allocation, not a hard
  requirement.
- **Hugging Face hosting -- verified, not assumed**: the official model
  page explicitly states **"This model isn't deployed by any Inference
  Provider."** No dedicated Inference Endpoint offering either -- only
  self-hosting via `transformers`, PaddleOCR's own Docker/vLLM server, or
  llama.cpp. [huggingface.co/PaddlePaddle/PaddleOCR-VL](https://huggingface.co/PaddlePaddle/PaddleOCR-VL)
- **Current recommended variant**: PaddleOCR-VL-1.6-0.9B.
- **Urdu**: docs claim "109 languages" and explicitly name Arabic,
  Cyrillic, Devanagari script support -- **Urdu is not explicitly named
  anywhere found**. Treat as unverified, not confirmed, despite Arabic
  script support being a positive signal.

### Specialist OCR/document APIs

| Service | Fit for arbitrary screenshots? | OpenAI-compatible? | Pricing |
|---|---|---|---|
| **Mistral OCR** | Yes -- general-purpose, markdown-native output (tables/images/confidence), 170 languages | No, bespoke REST | $4/1,000 pages (OCR 4, standard), $2/1,000 (batch) |
| Azure AI Document Intelligence (Read tier) | General OCR is fine; the platform's real value (Layout/prebuilt) skews invoice/form | No | $1.50/1,000 pages (Read) |
| Google Document AI (Enterprise Document OCR) | Same pattern -- general tier fine, specialized processors off-target | No | $1.50/1,000 pages |
| AWS Textract (DetectDocumentText) | Same pattern | No | $1.50/1,000 pages |

None of these are OpenAI-compatible -- each would need its own adapter.
**Mistral OCR is the one worth a benchmark slot**: genuinely general-
purpose (not narrow invoice/form extraction), markdown-native output fits
Local Lens's code/table/mixed-content needs well, competitively priced,
simple REST. Azure/Google/AWS's base OCR tiers are commodity-priced but
their platforms' actual differentiators (forms/invoices-as-a-service) are
off-target for "arbitrary screenshot/document intelligence" -- excluded
from the initial bake-off, not because they're bad, but because they solve
a different problem.

## 2. Comparison matrix

Capability columns are marked from documentation only -- **no fixture has
been run against any of these yet**. "Likely" reflects general model
capability claims (e.g. a flagship general VLM claiming strong multilingual
OCR); it is not a measurement.

| Model / Provider | Screenshot OCR | Tables | Code | Urdu | Structured JSON | Serverless | BYOK | Approx cost (per 1K img, ~1K in/500 out tok) | Integration effort |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| OpenAI GPT-5 | likely strong | likely strong | likely strong | unknown | confirmed (json_schema) | yes | yes | ~$6.25 | none (generic adapter) |
| OpenAI GPT-5-nano | likely good | likely fair | likely good | unknown | confirmed | yes | yes | ~$0.25 | none |
| Anthropic Claude Sonnet 5 | likely strong, explicit low-confidence guidance | likely strong | likely strong | unknown | confirmed (tool_use) | yes | yes | ~$10.50 | dedicated adapter (built) |
| Anthropic Claude Haiku 4.5 | likely good | likely good | likely good | unknown | confirmed | yes | yes | ~$3.50 | dedicated adapter (shared) |
| Gemini 2.5/3.5 Flash-Lite | likely good | likely fair | likely good | unknown | confirmed (native); beta (OpenAI-compat) | yes | yes | ~$0.30 | none via OpenAI-compat beta |
| Gemini 3.1 Pro | likely strong, native PDF | likely strong | likely strong | unknown | confirmed | yes | yes | pricing not confirmed | none via OpenAI-compat beta |
| Qwen2.5-VL-72B (Fireworks) | likely strong (open OCR-focused lineage) | likely good | likely good | unknown | best-effort via prompt | yes | yes | ~$1.35 | none (generic adapter) |
| PaddleOCR-VL-1.6 (self-hosted vLLM) | **measured locally in V3** (see docs/V4_DIRECTION.md) -- 8-132s CPU latency, real extreme-aspect-ratio bug found and mitigated | measured (real table pipeline) | not benchmarked | unverified in docs, Arabic script confirmed | best-effort via prompt | no -- self-managed | yes (self-hosted) | GPU-time billed, not per-token | provider built (PaddleVLLMProvider); server not deployed |
| Mistral OCR | likely strong (OCR-specialist) | confirmed (markdown table output) | unknown | unknown | markdown, not the shared JSON schema | yes | yes | ~$4.00 (per-page, not per-token) | new bespoke adapter (not built) |

Cost column uses this benchmark's own token-budget assumption (~1,000 input
/ ~500 output tokens per request -- see `local_lens/deep_analysis/
finalists.py`) x 1,000 requests, purely for a same-basis comparison; it is
not a prediction of real-world usage cost, which depends heavily on actual
image resolution and response length.

## 3. BYOK vs. Local-Lens-managed infrastructure

**BYOK (current design)**:
- Pros: user pays their chosen provider directly; no Local-Lens-operated
  billing system; no Local-Lens-operated GPU; no image proxy through a
  Local Lens backend (better privacy story -- Local Lens never sees the
  image either); much easier open-source distribution (no infra to keep
  running).
- Cons: setup friction (user must get their own API key/endpoint); quality
  varies by what the user configures; API key management is on the user.

**Local-Lens-managed** (not built, not planned for this stage):
- Pros: seamless UX (works out of the box, no configuration).
- Cons: billing system required; abuse/rate-limiting surface; security
  responsibility for proxied images; image-handling privacy obligations
  shift onto Local Lens itself; ongoing operational cost regardless of
  usage.

**Recommendation: stay BYOK.** Local Lens is a single-developer,
laptop-resource-constrained, open-source project at this stage -- operating
billed infrastructure would invert the entire reason Deep Analyze moved
remote in the first place (to get heavy compute *off* something Local Lens
operates). Revisit only if the project takes on a hosting/product
identity distinct from what it is today.

## 4. Privacy comparison

| Provider | Trains on API data? | Retention | Notes |
|---|---|---|---|
| OpenAI | No (opt-in only) | ~30 days default; Zero Data Retention available (enterprise-approved) | [Enterprise privacy](https://openai.com/enterprise-privacy/) |
| Anthropic | No | Images "ephemeral," deleted after request processing | [Vision docs](https://platform.claude.com/docs/en/build-with-claude/vision) |
| Google Gemini (free/AI Studio tier) | **Yes** -- content may be used to improve products; human review possible | Not itemized in pages fetched | Explicitly told not to submit sensitive data on this tier |
| Google Gemini (paid tier) | No | Brief retention for abuse/legal only | EEA/UK/Switzerland users required onto paid tier |
| Fireworks/Together/DeepInfra/HF-routed | Not researched this pass | Not researched this pass | Flag for the finalist round if any of these gets picked |
| PaddleOCR-VL self-hosted | N/A -- no third party at all | You control it entirely | Only option where "your data doesn't leave infrastructure you control" is literally true |
| Mistral OCR | Not researched this pass | Not researched this pass | — |

**Actionable finding**: if Gemini is ever wired up, Local Lens's Deep
Analyze privacy notice (`app.py`'s sidebar caption) must distinguish free
vs. paid Gemini tier explicitly -- "sent to your configured provider" is
not honest enough for Gemini's free tier specifically, where the provider
itself says it may use the content for training and human review.

## 5. Evaluation metrics (defined before any request is made)

**OCR**: CER, WER, normalized similarity (same functions already in
`benchmarks/metrics.py` -- reused, not reinvented).

**Code**: CER, line-count preservation (produced line count == expected),
indentation preservation (leading-whitespace-per-line match rate), and a
punctuation-preservation check (non-alphanumeric character multiset
overlap) as a cheap proxy for "didn't reformat/autocorrect the code."

**Tables**: row/column/cell accuracy, structure accuracy -- reusing
`benchmarks/metrics.py`'s existing `table_structure_accuracy()`.

**Urdu**: CER, WER, plus a manual visual-inspection step (as in V3/V4 --
automated shaping metrics alone don't catch a plausible-looking but
actually-reordered Arabic-script result).

**Reliability**: valid-structured-response rate (`DeepBenchmarkResult`s
where `parsed_result.metadata["structured_response"] is True`), empty-
result rate, and error rate by `DeepAnalysisError` subtype.

**Extraction fidelity ("hallucination") signal**: `extra_content_rate()`
(`local_lens/deep_analysis/benchmark.py`) -- fraction of produced words not
present in the ground-truth word multiset. Explicitly documented as a
coarse extraction-fidelity signal, not a semantic hallucination detector
(a genuine recognition error and an invented value both register as
"extra") -- meant to be read alongside CER/WER, never alone.

**Performance**: total HTTP latency per request (`DeepBenchmarkResult.
latency_ms`), and where possible a cold-vs-warm distinction (first request
per provider vs. subsequent ones in the same run).

**Cost**: `estimate_request_cost()` for a planning-stage estimate before
any call; actual cost read from provider-supplied usage fields where the
response includes them (not yet implemented -- no response has been
received from any provider).

## 6. Is PaddleOCR-VL still worth self-hosting?

**Not yet answerable from documentation alone -- this is exactly the kind
of question the task said benchmark data must answer, not docs.** What
documentation research *does* establish:

- PaddleOCR-VL is the only finalist with **real prior measurement** behind
  it (V3's benchmark run: 8-132s CPU latency, a genuine extreme-aspect-
  ratio recognition bug found and root-caused, a working table pipeline).
  Every other finalist is untested against this project's own fixtures.
- It is the only finalist requiring genuinely new operational surface
  (deploying and paying for a GPU server, even a scale-to-zero one) rather
  than an API key.
- Its GPU footprint is small on paper (~2GB class) but real-world vLLM
  memory behavior was reported far higher by at least one user report --
  worth confirming directly if self-hosting is pursued, not assumed from
  the model's parameter count.
- Urdu support is undocumented for PaddleOCR-VL specifically, despite
  Arabic-script support being claimed generally -- a real open question
  for a project where Urdu is a first-class use case.
- Against it: every proprietary/hosted-open finalist is a config change
  away (API key + base URL), with no server to operate, monitor, or pay
  idle-GPU cost for even at zero traffic (serverless marketplaces bill
  per-token; a self-hosted scale-to-zero GPU still has cold-start latency
  and *someone* has to keep the deployment working).

**Provisional read, to be confirmed or overturned by actual benchmark
data**: self-hosting PaddleOCR-VL is worth the operational complexity only
if the bake-off shows it meaningfully outperforms the hosted-open-VLM
finalist (Fireworks/Qwen2.5-VL) on OCR fidelity or Urdu specifically --
otherwise a hosted option removes an entire operational surface (server
maintenance, cold starts, GPU billing) for comparable quality. This
question is the primary reason PaddleOCR-VL stays in the finalist list
despite four other candidates being simpler to operate.
