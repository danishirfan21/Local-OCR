"""The single structured-extraction prompt every Deep Analyze provider is
sent, so bake-off comparisons measure model capability, not prompt
differences between providers.

Deliberately extraction-focused, not conversational: Deep Analyze is an
OCR/document tool, not a chat assistant, and the dominant failure mode for
a general VLM used this way is *helpfulness* -- autocorrecting typos,
filling in a table cell it "knows" should be there, summarizing instead of
transcribing. The anti-hallucination block exists specifically to suppress
that, and the benchmark's `extra_content_rate` metric (see benchmark.py)
gives it something to be checked against.
"""

from __future__ import annotations

DEEP_ANALYSIS_PROMPT = """\
Analyze this screenshot or document image and extract its content exactly \
as it appears.

Return ONLY a JSON object (no markdown fences, no commentary) matching this \
schema:
{
  "text": "<all visible text, in reading order, exactly as written>",
  "content_type": "<text|code|table|unknown>",
  "languages": ["<ISO 639-1 codes for every script/language actually present>"],
  "blocks": [
    {
      "type": "<text|title|table|code|formula|image|unknown>",
      "text": "<this block's content>"
    }
  ]
}

Strict extraction rules -- this is OCR/transcription, not summarization or \
assistance:
1. Transcribe visible text exactly as it appears. Do not correct spelling, \
grammar, or punctuation, even if it looks like a typo.
2. Do not invent, infer, or complete any text, table cell, or value that is \
not actually visible in the image. If a cell or region is empty, blank, or \
illegible, represent it as an empty string -- never guess a plausible value.
3. Preserve code exactly: indentation, line breaks, punctuation, and casing \
matter. Do not "fix" or reformat code.
4. Preserve numbers, currency symbols, and punctuation exactly as shown -- \
do not normalize formatting (e.g. do not change "1,234.50" to "1234.5").
5. If the image contains a table, represent it as a markdown table inside \
the relevant block's "text", preserving row/column structure and empty \
cells.
6. If you cannot read part of the image with confidence, omit that part \
rather than guessing, and do not mention your uncertainty inside the \
transcribed text itself.
7. Do not add any text, labels, or content that is not visibly present in \
the image, including headers, captions, or summaries you were not asked for.
"""
