# Local Lens V4 Direction — Decision Report

Audit performed against `main` at commit `cd39087ea1a903c7eb03f6bcc505bdcd1edca934` (V3 complete, pushed, 98/98 tests passing, working tree clean). All numbers below are read directly from committed files: `benchmarks/results/20260824T221555Z.json` (EasyOCR/PaddleOCR) and `experiments/paddleocr_vl/results.json` (PaddleOCR-VL), plus new latency/disk measurements taken during this audit (documented as such, not committed benchmark artifacts).

## Executive decision

Local Lens V4 should split into two explicit modes — **Auto/Fast** (EasyOCR by default, PaddleOCR for mixed Urdu/English and tables) and **Deep Analyze** (PaddleOCR-VL, explicit opt-in only) — rather than one router that silently decides when to pay an 8-132 second CPU cost. The product's primary identity should remain **desktop screenshot intelligence** (option C: shared core, desktop as flagship UX), with CLI/API/developer tooling as a secondary surface built on the same `OCRService`. PaddleOCR-VL should ship as a **production-optional engine** behind an explicit "Deep Analyze" control, not as an auto-routed specialist and not left purely experimental — the accuracy is good enough to be worth having, the latency is bad enough that it must never run without the user asking for it.

## Evidence

### Comparison matrix (from committed results)

| Workload | EasyOCR | PaddleOCR | PaddleOCR-VL | Status |
|---|---|---|---|---|
| short UI text ("Save") | CER 0.00 | **CER 1.00 (total failure, 0 blocks)** | CER 0.00 | measured |
| short UI text ("Cancel Settings OK") | CER 0.00 | CER 0.06 | CER 0.00 | measured |
| English paragraph | CER 0.02 | CER 0.37 | **CER 1.00 (empty output — see §3)** | measured |
| numeric | CER 0.00 | CER 0.00 | CER 0.00 | measured |
| English + numbers | CER 0.03 | CER 0.03 | CER 0.00 | measured |
| code | CER 0.27 | CER 0.25 (WER 0.11) | CER 0.22 (WER **0.00**, loses indentation) | measured |
| tables (simple + dense) | cell_acc 1.00 (both) | cell_acc 1.00 (both) | ran OK, **not scored** for structure | measured (VL table accuracy: not measured) |
| Urdu paragraph | CER 0.75 | CER 0.75 | CER 0.79 | measured, but **corpus has a known shaping defect** — see §13 |
| mixed Urdu/English | CER 0.39 | CER 0.23 | **CER 0.12 (best)** | measured, same caveat |
| Urdu + numbers | CER 0.80 | CER 0.85 | CER 0.40 | measured, same caveat |
| model load time | 63.6s (first Reader() construction) | 14.9s (first pipeline construction) | 120-146s (from local cache, no download) | measured this audit |
| warm latency, short text | median 0.30s | median 2.52s | 38-41s | measured this audit (EasyOCR/PaddleOCR); VL from committed results |
| warm latency, paragraph | median 1.30s | median 6.18s | 8-50s | measured this audit / committed |
| warm latency, code | median 1.15s | median 7.96s | 132s | measured this audit / committed |
| disk cost | 300MB (`~/.EasyOCR`) | ~1.7GB (plain OCR + table pipeline models) | 1.8GB (VL weights alone) | measured this audit |
| memory (RAM/VRAM) | not measured | not measured | not measured | **not measured** — flagged, not guessed |

### Key correction to a V3-era assumption

V3's `engine_router.py` routes `document_scan`/`photo` input types to PaddleOCR on the reasoning that its doc-orientation/unwarping steps help there. **That reasoning was never tested against this corpus, because every fixture in `benchmarks/corpus.py` is a clean synthetic screenshot** — there is no photographed or scanned document fixture. On the fixtures that do exist, EasyOCR beats or ties PaddleOCR on accuracy for 5 of 6 plain-text categories (short UI ×2, numeric, English+numbers, paragraph) while being consistently 4-8x faster warm. PaddleOCR's one clear, measured win is mixed Urdu/English (CER 0.23 vs 0.39). This means the current router's "photo/scan → PaddleOCR" rule is an **untested assumption carried forward**, not a measured conclusion — flagged as a real gap in §12/§13/roadmap, not silently corrected by fabricating a photo-fixture result.

## §3 — PaddleOCR-VL paragraph failure: root cause found

Built a 4-way minimal repro from the exact failing fixture (`benchmarks/samples/english/paragraph.png`, 1760×56px, ~31:1 aspect ratio, single unwrapped line):

| Variant | Layout boxes found | Parsed content |
|---|---|---|
| Original (1760×56) | 1 | **empty** |
| 2x upscale (3520×112, same aspect ratio) | 1 | **empty** |
| Larger font, same wide single-line canvas (2200×80) | 1 | **empty** |
| Same text, wrapped to multiple lines (700×128, ~5.5:1 aspect) | 1 | **correct, full text recovered** |

**Root cause**: layout detection reliably finds exactly one text region in every variant — the failure is not a detection miss. The VL *recognition* stage returns empty content specifically for extremely elongated, single-line crops; a normal-aspect-ratio multi-line crop of the identical text succeeds. This is consistent with the recognition stage's vision encoder normalizing crops toward a roughly-square input tile, which would squish a 31:1 aspect-ratio strip into unreadability while a 5.5:1 crop survives resizing intact. Neither image size (2x scale still fails) nor font size (larger font still fails) is the cause — aspect ratio/crop shape is.

**Disposition**: this is a genuine PaddleOCR-VL recognition-stage limitation, and it is representative of a real class of input (a single very long unwrapped line — a long URL, a wide log line, a status bar). It is **not fixed in this audit**: the fix belongs in `benchmarks/corpus.py`'s fixture generation (wrap long single-line text like a realistic paragraph screenshot would), but changing that fixture would silently invalidate the already-committed EasyOCR/PaddleOCR measurements this same audit relies on as its evidence base. Recommended as a V4 task (§15) rather than done here, per the instruction not to over-invest in tuning one fixture mid-audit.

## Engine roles (recommended for V4)

- **EasyOCR** — default fast-path engine for clean digital screenshots (short text, paragraphs, numeric, code). Fastest warm latency measured (0.3-1.3s) and matches-or-beats PaddleOCR's accuracy on every plain-text category tested except mixed Urdu/English.
- **PaddleOCR** — fast-path specialist for mixed Urdu/English (measured accuracy win) and the assumed-but-unverified photo/scan case (doc-orientation/unwarping capability, not yet benchmarked against a real photo/scan fixture). Also the only currently-viable option for pure Urdu, though neither engine is good there on this corpus.
- **Paddle table pipeline** (`TableRecognitionPipelineV2`) — unchanged from V3: gated behind content classification, not a routing choice between engines. Perfect cell accuracy on the two fixtures tested; see §12 for what that does and doesn't prove.
- **PaddleOCR-VL** — Deep Analyze, explicit opt-in only. Too slow (8-132s per image) for any default interactive path; strong accuracy on short text and the best measured mixed Urdu/English result, but with one confirmed reliability failure mode (§3) and no table-structure scoring yet.

## Product direction

**Primary identity: C — shared core, desktop as flagship UX.** The tagline ("Private AI for everything on your screen"), the clipboard/Snipping Tool workflow being the single most consistently emphasized feature across V1-V3, and the roadmap's own repeated prioritization of native desktop capture over CLI/API all point here. Developer tooling (CLI, API, MCP) is a real, valuable secondary surface — `OCRService`, the router, and the table pipeline are already Streamlit-independent by design specifically so this works — but it is not the identity V4 should lead with.

## UX concept: Fast vs. Deep

Two explicit modes, not one smart router that sometimes takes 2 minutes without warning:

```
Mode
● Auto / Fast   -- EasyOCR (default) or PaddleOCR (mixed Urdu/English, tables), sub-10s
○ Deep Analyze  -- PaddleOCR-VL, explicit opt-in, 8-132s, user is told to expect a wait
```

This directly follows from the latency data: forcing every image through a router that might silently invoke a 2-minute model is bad UX regardless of accuracy. An explicit, predictable mode switch is preferred, matching the instruction to prioritize predictable UX over automatic cleverness.

## Architecture (V4 target, not implemented)

```
Desktop / CLI / API
        │
        ▼
    OCRService
        │
        ▼
   Input Analyzer  (screenshot / photo / scan / unknown -- unchanged from V3,
        │           but "photo/scan → PaddleOCR" needs real fixture validation)
        ▼
      Router                         Mode: Auto/Fast (default) or Deep Analyze (explicit)
   ┌────┼──────────────┐                    │
   ▼    ▼              ▼                    ▼
EasyOCR PaddleOCR   [Deep Analyze only] PaddleOCR-VL
   │       │
   └───┬───┘
       ▼ (if content_type == table)
  Paddle table pipeline
```

- **Fast path**: Auto/Fast mode never invokes PaddleOCR-VL. Table extraction remains a post-classification enrichment step, unchanged from V3.
- **Deep path**: only entered when the user explicitly selects Deep Analyze. No automatic promotion from Fast to Deep based on content, given the latency data in §evidence.
- **Fallback behavior**: unchanged from V3 — if a selected/routed engine isn't installed, fall back to whatever is available and say why (existing `RoutingDecision.reason` mechanism already does this).
- **Caching/model lifecycle**: unchanged pattern (module-level cache per engine/pipeline config, wrapped in `st.cache_resource` at the UI layer) extends cleanly to a `PaddleOCRVLEngine` — no new lifecycle concept needed.
- **Optional dependencies**: PaddleOCR-VL's `paddlex[ocr]` extra (already documented, ~1.8GB disk) stays optional and separately installed, same as the table pipeline's dependency today.

## Risks

- **CPU VLM latency**: 8-132s per image is real and confirmed, not a first-run artifact — this is warm, cached-model inference. Any production path must make this cost visible and opt-in, never silent.
- **Urdu benchmark quality**: every Urdu number in this report is confounded by the corpus's known lack of `raqm` text shaping (isolated letterforms, not real joined script). None of the Urdu CER numbers should be used to make a production claim about real-world Urdu accuracy.
- **Model disk size**: PaddleOCR-VL alone is 1.8GB; the full Paddle stack (plain OCR + table pipeline + VL) is ~3.5GB. This has real implications for a desktop app's install size/first-run experience.
- **Paddle dependencies**: the `paddlex[ocr]` extra requirement was itself an undocumented-upstream discovery in V3 — future PaddleOCR/paddlex upgrades could introduce similar surprises; no CI/pinning strategy exists yet to catch this automatically.
- **Table generalization**: perfect accuracy on 2 clean synthetic tables proves the pipeline *works*, not that it's *robust* — see §12.

## §12 — Table pipeline: what's proven, what isn't

**Proven**: `TableRecognitionPipelineV2` can extract exactly correct rows/cells from a clean, digitally-rendered, gridlined table with simple text content, for both engines' upstream OCR (table extraction is engine-independent). Perfect cell accuracy on 2 fixtures (3×3 and 5×4).

**Not proven, and should not be assumed**: performance on merged cells, missing/partial borders, multi-line cell content, financial-table formatting (currency symbols, alignment, negative numbers in parens), an Urdu table (RTL column order, script), a photographed table (perspective, lighting, moiré), or a dense spreadsheet-style table (many columns, small font). Two clean fixtures is proof of correctness on the easy case, not evidence of robustness. All six of these are recommended as explicit V4 benchmark additions (not implemented in this audit).

## §13 — Urdu: what we can and cannot conclude

The current corpus's Urdu fixtures are rendered without `raqm` text shaping, producing isolated Arabic-script letterforms rather than real joined Nastaliq/Naskh script. Every CER number above involving Urdu is measuring **OCR performance on synthetically-broken glyphs**, not real Urdu text. The one number that partially escapes this caveat is PaddleOCR-VL's mixed-script result (CER 0.12) being clearly better than both OCR-only engines (0.23-0.39) — a VLM's contextual/layout awareness plausibly helps even on broken glyphs in a way word-level recognition can't, which is suggestive but not sufficient to claim production-quality Urdu support.

**Recommendation for a legitimate Urdu benchmark**: either (a) obtain a Pillow build with `libraqm` linked and re-render the existing fixtures (cheapest fix, stays synthetic/safe-to-commit), or (b) source a small number of real, rights-cleared Urdu screenshots (news sites, public documents, self-typed WhatsApp/UI screenshots) with hand-verified ground truth. Do not report a production Urdu accuracy claim until one of these exists.

## V4 roadmap (prioritized, 6-8 tasks)

1. **Fix the corpus's paragraph fixture to wrap realistically** (§3) — cheap, unblocks a clean re-benchmark, and removes the one fixture with a diagnosed-but-unfixed failure.
2. **Real Urdu benchmark** (§13) — either a `raqm`-capable Pillow build or a handful of real rights-cleared Urdu screenshots. Blocks any legitimate Urdu accuracy claim.
3. **Implement Fast/Deep mode switch in the UI** — replace the current single Auto router with the explicit two-mode UX from §"UX concept." This is the most user-visible, lowest-risk V4 change.
4. **Validate (or correct) the photo/scan → PaddleOCR routing rule** with a real photographed/scanned-document fixture — currently an unverified carry-over assumption (§evidence).
5. **Production PaddleOCR-VL adapter** (`PaddleOCRVLEngine` implementing the existing `OCREngine` protocol) wired only into Deep Analyze mode — the accuracy case is made; this is mostly plumbing given the existing engine abstraction.
6. **Table robustness benchmark set** (§12: merged cells, missing borders, multi-line cells, financial tables, Urdu table, photographed table, dense spreadsheet) — do not claim table robustness beyond what's tested.
7. **CLI on top of `OCRService`** — architecture is already there; smallest step toward the developer-tools secondary surface without committing to API/MCP yet.
8. **Repository rename to `local-lens`** (see below) — low effort, timed for when the README/branding work is otherwise being touched (e.g. alongside task 3).

## Repository rename

**Recommend renaming to `local-lens`** (lowercase-hyphenated, the GitHub-conventional form) in V4, not now. `Local-OCR` undersells the current scope (tables, routing, Urdu handling, a VLM experiment) and will undersell it further once Deep Analyze ships. GitHub automatically redirects the old URL after a rename, so existing links keep working — the "existing links" concern is not a real blocker. `local-lens` over `Local-Lens`: GitHub's own convention and most popular repos favor all-lowercase-hyphenated names for discoverability and consistency with `pip install`/`npm`-style naming expectations, and it reads better in a portfolio context than mixed-case. Not renamed in this task, per instructions.
