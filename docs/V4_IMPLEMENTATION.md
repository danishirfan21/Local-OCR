# V4 implementation report

This report covers a resource-safety-driven revision of the V4 plan
(`docs/V4_DIRECTION.md`) after a laptop freeze traced to disk exhaustion
during local Paddle/PaddleOCR-VL experimentation. It documents what
changed, what was executed locally vs. deliberately deferred, and what
still requires the user's explicit approval before proceeding.

## 1. What happened and why the plan changed

The laptop froze during heavy local Paddle/PaddleOCR-VL work. Investigation
found the root cause: the C: drive had filled to **3.6 GB free** (98% used),
largely from `~/.paddlex/official_models` (≈3.5 GB, including ~1.8 GB of
PaddleOCR-VL weights) plus `~/.EasyOCR` (~300 MB) and Paddle's own Python
packages (~412 MB in `.venv`). The user then manually removed the Paddle
stack:

- `%USERPROFILE%\.paddlex\official_models` deleted (confirmed absent via
  `Test-Path` → `False`).
- `paddlepaddle`, `paddleocr`, `paddlex` uninstalled from `.venv` (confirmed
  via `pip show` → not found for all three).
- `easyocr` and its ~300 MB local model cache were kept intentionally.
- Free disk recovered to **6.93 GB**.

A hard resource-safety rule is now in effect: no reinstalling, downloading,
loading, benchmarking, or executing Paddle/PaddleX/PaddleOCR-VL, vLLM, or
any other multi-GB model/weight locally on this laptop without explicit
approval. This report and the code changes below were produced entirely
under that rule — nothing heavy was reinstalled, downloaded, or run.

## 2. Resource-safety changes

**Paddle is now fully optional, confirmed by measurement, not assumption.**
`pytest tests/ -q` passes **140/140** with `paddlepaddle`/`paddleocr`/
`paddlex` completely absent from the environment. Every module that can
touch Paddle already guarded the import behind `try/except ImportError` and
exposed an `*_AVAILABLE` flag before this pass
(`local_lens/engines/paddleocr_engine.py`,
`local_lens/tables/paddle_table_extractor.py`,
`local_lens/engines/paddleocr_vl_engine.py`) — that pattern was verified,
not newly invented, by actually removing Paddle and re-running the suite.
Importing `local_lens` (including `local_lens.backends` and
`local_lens.deep_analysis.*`) triggers no model download, no heavyweight
import, and no optional-backend failure — this is asserted directly in
`tests/test_no_silent_network.py`.

**Backend capability model** (`local_lens/backends.py`): a `BackendStatus`
dataclass (`name`, `available`, `mode: "local"|"remote"`, `reason`)
distinguishes *not installed* from *not configured* from *available*. The
UI's "Model availability" panel and the CLI's `local-lens doctor` both read
from this instead of probing dependencies ad hoc in multiple places.

## 3. Target architecture (revised)

```
                         Local Lens
                             |
               +-------------+-------------+
               v                           v
          Fast / Local                Deep / Remote
               |                           |
           EasyOCR                     HTTPS API (BYOK)
               |                           |
       offline / private              hosted VLM/GPU you configure
```

- **Fast** = EasyOCR only, by default. PaddleOCR remains a supported manual
  option in Fast mode's engine selector but is never required — the
  `AVAILABLE_ENGINE_KEYS` list and `choose_engine()` already degrade
  gracefully to EasyOCR when PaddleOCR is absent (this was true before this
  pass too, and is now the *primary* supported configuration, not a
  fallback path).
- **Deep Analyze** = a remote `DeepAnalysisProvider`, never a local Paddle
  process. It is opt-in, BYOK, and off by default (`LOCAL_LENS_DEEP_BASE_URL`
  unset → "not configured").
- Table extraction: local PaddleOCR table pipeline remains available *if*
  the user has separately opted into `requirements-paddle.txt` (unchanged,
  optional, clearly labeled legacy). No remote table provider was built
  this pass — Deep Analyze's structured-response schema includes a `blocks`
  field that can carry a markdown table in a block's `text`, which is the
  interim path until a dedicated remote table strategy is designed.

## 4. Deep Analyze provider abstraction

`local_lens/deep_analysis/`:

- `base.py` — `DeepAnalysisProvider` protocol (`name`,
  `extract(image, langs) -> DocumentResult`) plus a typed exception
  hierarchy (`DeepAnalysisNotConfigured`, `DeepAnalysisAuthError`,
  `DeepAnalysisRateLimited`, `DeepAnalysisServerError`,
  `DeepAnalysisTimeout`, `DeepAnalysisBadResponse`). Deliberately the same
  shape as `OCREngine`, so `OCRService` runs Fast and Deep through one code
  path with no special-casing.
- `http_client.py` — stdlib-only (`urllib.request`) HTTP transport, chosen
  over adding `requests`/`httpx` as a new dependency for what is one POST
  per request. A `Transport` callable is an injectable seam so tests never
  touch the real network. Retries: one retry on timeout/429/5xx; **no**
  retry on 401/403/other 4xx (a bad key or malformed request won't fix
  itself, and providers may charge per request). `redact_headers()` strips
  `Authorization`/API-key values for anything that gets logged.
- `openai_compatible_provider.py` — `OpenAICompatibleVisionProvider`,
  targeting the `/v1/chat/completions` contract (system+user messages, an
  `image_url` content block with a base64 PNG data URL, response in
  `choices[0].message.content`). This is the publicly documented OpenAI
  Chat Completions vision request shape, which vLLM's OpenAI-compatible
  server implements — it was not guessed for this specific integration.
  Requests a structured JSON reply (`text`, `content_type`, `language`,
  `blocks[]`); falls back to treating the raw reply as plain text if it
  isn't valid JSON, rather than failing. Maps into `DocumentResult` with
  `metadata["provider"]`, `metadata["remote"] = True`.
- `paddle_vllm_provider.py` — `PaddleVLLMProvider`, a thin subclass of the
  above with PaddleOCR-VL-appropriate defaults (`model="PaddleOCR-VL-1.6"`,
  120s timeout). Calls the vLLM server's HTTP endpoint directly — it does
  **not** import or require `paddlex`/`paddleocr` locally, so using remote
  PaddleOCR-VL never reintroduces the heavy dependency stack that was just
  removed.
- `config.py` — reads `LOCAL_LENS_DEEP_PROVIDER` / `LOCAL_LENS_DEEP_BASE_URL`
  / `LOCAL_LENS_DEEP_API_KEY` / `LOCAL_LENS_DEEP_MODEL` from the
  environment. No default base URL ships with the app — BYOK by design, no
  Local-Lens-operated inference infrastructure, no billing system, no image
  proxy through a Local Lens backend.

**Not executed locally, by design**: no live HTTP request was made against
a real remote endpoint in this session — that would require the user to
provision one, which is exactly the kind of paid/infrastructure action this
pass was told to stop short of. Request/response handling (structured and
unstructured replies, every documented failure status, retry behavior,
secret redaction) is instead covered by `tests/test_deep_analysis.py`
against a fake, injected transport — 20 tests, all passing, zero network
calls.

## 5. Fast/Deep UX in app.py

- Sidebar "Processing Mode": `Fast` (default) / `Deep Analyze`. Selecting
  Deep Analyze while unconfigured shows a warning and the app transparently
  falls back to Fast mode rather than erroring.
- When Deep Analyze *is* configured, selecting it shows which host the
  image will be sent to before any request is made.
- "Model availability" expander lists EasyOCR / PaddleOCR / table
  extraction / legacy local PaddleOCR-VL / Deep Analyze with ✓/○ and a
  reason for anything unavailable.
- Result line reads `Detected: <type> · Engine: <name> · Mode: <Fast|Deep
  Analyze (remote)>`; the Advanced-details expander adds provider/base-URL
  info when Deep Analyze was used.
- Verified in-browser (Streamlit dev server via the sandbox's browser
  preview, no external traffic): Fast/Deep radio renders, Model
  availability panel correctly reports EasyOCR available / PaddleOCR,
  table extraction, and Deep Analyze all "not configured/not installed",
  and selecting Deep Analyze with nothing configured shows the fallback
  warning with no traceback.

## 6. CLI

`local_lens/cli.py`, no Streamlit import anywhere in its import chain:

```bash
local-lens extract image.png --mode fast [--engine easyocr|paddleocr] [--format text|markdown|json|csv]
local-lens extract image.png --mode deep
local-lens doctor
```

`--mode deep` without a configured provider exits non-zero with an
actionable message rather than attempting an install or crashing. `doctor`
reports every backend's status via `local_lens/backends.py`. Packaged via
`pyproject.toml` (`[project.scripts] local-lens = "local_lens.cli:main"`);
`requirements.txt`/`requirements-paddle.txt` are kept alongside it for the
existing `pip install -r ...` + `streamlit run app.py` workflow.

## 7. Testing

`pytest tests/ -q` → **140 passed**, run with Paddle completely absent from
the environment. New test files this pass:

- `tests/test_deep_analysis.py` (20 tests) — config parsing, status
  reporting, structured/unstructured response mapping, every documented
  HTTP failure mode mapped to the correct exception, no-retry-on-401,
  retry-up-to-max-on-500, API key never appears outside the `Authorization`
  header, header redaction for logging.
- `tests/test_backends.py` (5 tests) — capability/status reporting never
  raises and reports a reason whenever something is unavailable.
- `tests/test_no_silent_network.py` (2 tests) — Fast-mode OCR and importing
  every `local_lens.deep_analysis`/`local_lens.backends` module make zero
  network calls (enforced by monkeypatching `urllib.request.urlopen` to
  raise if called).
- `tests/test_cli.py` (6 tests) — Fast extraction (fake engine, no real
  model load), missing-file handling, Deep-mode-unconfigured error, JSON
  format output, `doctor` output shape.
- `tests/test_engines.py` — extended with a table-cleanup test (trims cell
  whitespace, drops fully-empty rows, records `row_count`/`column_count`/
  `empty_cell_ratio`/`removed_empty_rows` in `TableResult.metadata` without
  fabricating a confidence score).

## 8. CI

`.github/workflows/ci.yml`: installs `requirements.txt` only, explicitly
asserts Paddle is **not** present (`pip show paddlepaddle paddleocr paddlex`
must fail), compiles the whole tree, runs the unit test suite, and smoke
tests the CLI (`--help`, `doctor`). No model downloads, no Paddle install,
matching the resource-safety rule — a clean Paddle-free environment is a
first-class CI case, not a special one.

## 9. What was NOT executed locally (per the resource-safety rule)

- No `paddlepaddle`/`paddleocr`/`paddlex` reinstall.
- No PaddleOCR-VL (or any other) model weights downloaded.
- No vLLM install, local or otherwise.
- No live request to any remote Deep Analyze provider — `OpenAICompatibleVisionProvider`
  and `PaddleVLLMProvider` are verified only against a fake transport.
- No cloud/GPU infrastructure provisioned (RunPod, Modal, HF Endpoints, or
  otherwise) — no cost was incurred.
- No repository rename executed.
- No deletion of anything beyond what the user had already manually removed
  before this session began.

## 10. Remote provider comparison (documentation-only, from the prior audit)

Carried forward from the earlier hosted-inference research (not repeated
against live APIs this pass, since that would require live requests):

| Option | Fit for PaddleOCR-VL | Notes |
|---|---|---|
| HF Inference Providers | No | Doesn't serve PaddleOCR-VL as a hosted model. |
| HF Inference Endpoints | Possible, more setup | Dedicated deployment, needs a custom handler for a non-standard task; per-hour billing even when idle unless paused manually. |
| Official PaddleOCR-VL + vLLM remote-server mode | **Best fit** | Officially supported (`vl_rec_backend="vllm-server"`), exposes an OpenAI-compatible endpoint — exactly what `PaddleVLLMProvider` targets. Requires a GPU host to run vLLM on. |
| RunPod Serverless / Modal / similar | Best way to *host* the above | Per-second billing, scale-to-zero, supports custom containers (a vLLM+PaddleOCR-VL image) — infrastructure choice, not a PaddleOCR-VL-specific service. |
| Generic hosted OpenAI-compatible VLM (any provider) | Alternative to PaddleOCR-VL itself | `OpenAICompatibleVisionProvider` works against any of these unmodified — avoids vendor lock to PaddleOCR-VL specifically. |

**Recommendation unchanged from the prior audit**: self-host PaddleOCR-VL's
own vLLM server on a scale-to-zero serverless GPU host (RunPod-style),
fronted by `PaddleVLLMProvider`; keep `OpenAICompatibleVisionProvider` as
the generic fallback so switching providers is a config change, not a code
change. This has not been re-verified against current pricing/availability
in this session.

## 11. Known limitations

- Deep Analyze's structured-response schema is a best-effort request to the
  model, not a guaranteed contract — providers that ignore the
  "respond with only JSON" instruction fall back to plain text
  automatically, but table/formula structure from Deep Analyze is
  unverified against any real provider.
- No remote table-extraction strategy exists yet; local table extraction
  still requires the optional Paddle stack.
- The legacy local `PaddleOCRVLEngine` (aspect-ratio-fallback mitigation)
  was written and compiles cleanly but has never been exercised against a
  real PaddleOCR-VL instance in this repository — the experiment that would
  confirm its aspect-ratio threshold (`experiments/paddleocr_vl/
  aspect_ratio_experiment.py`) has not been run, and must not be run on
  this laptop.
- `benchmarks/run_remote.py` (a remote-endpoint-configurable benchmark
  runner) was not built this pass — flagged as the next benchmarking step
  once a provider is actually provisioned.

## 12. Recommended next action requiring explicit user approval

Any of the following would cost money, provision infrastructure, send an
image to a remote provider, or install a heavyweight local dependency —
none were performed:

1. **Provision a remote Deep Analyze endpoint** (e.g. a RunPod serverless
   vLLM+PaddleOCR-VL deployment, or sign up for a hosted OpenAI-compatible
   VLM provider) and set `LOCAL_LENS_DEEP_BASE_URL`/`LOCAL_LENS_DEEP_API_KEY`
   to actually exercise Deep Analyze end-to-end for the first time.
2. **Reinstall the local Paddle stack** (`pip install -r
   requirements-paddle.txt`) — only if the user specifically wants local
   PaddleOCR/table extraction/legacy PaddleOCR-VL on this machine despite
   the disk-space history; not recommended given the prior freeze.
3. **Run the aspect-ratio experiment and a full benchmark pass** — needs
   either an approved bounded local run or a remote/cloud environment with
   Paddle installed.

Until one of these is approved, Local Lens is fully usable in Fast mode
with Deep Analyze visibly "not configured."
