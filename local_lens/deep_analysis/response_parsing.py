"""Shared structured-reply parsing for Deep Analyze providers.

Every provider asks the model to reply with the same JSON schema (see
prompts.py) but returns that reply wrapped differently (OpenAI:
`choices[0].message.content`; Anthropic: `content[0].text`). Once each
provider has pulled out the raw reply string, parsing it into
blocks/document_blocks is identical -- factored here so
OpenAICompatibleVisionProvider and AnthropicProvider don't duplicate it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from local_lens.models import BoundingBox, DocumentBlock, TextBlock


@dataclass
class ParsedReply:
    text: str
    language: str | None
    content_type: str | None
    structured: bool
    blocks: list[TextBlock] = field(default_factory=list)
    document_blocks: list[DocumentBlock] = field(default_factory=list)


def parse_structured_reply(content: str) -> ParsedReply:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()

    structured: dict | None = None
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            structured = parsed
    except json.JSONDecodeError:
        structured = None

    if structured is not None:
        text = str(structured.get("text") or "")
        language = structured.get("language")
        if not language:
            languages = structured.get("languages")
            if isinstance(languages, list) and languages:
                language = languages[0]
        content_type = structured.get("content_type")

        blocks: list[TextBlock] = []
        document_blocks: list[DocumentBlock] = []
        for raw_block in structured.get("blocks") or []:
            if not isinstance(raw_block, dict):
                continue
            block_text = str(raw_block.get("text") or "")
            block_type = str(raw_block.get("type") or "text")
            bbox = _bbox_from_raw(raw_block.get("bbox"))
            document_blocks.append(DocumentBlock(type=block_type, text=block_text, bbox=bbox, metadata={}))
            if block_text:
                blocks.append(TextBlock(text=block_text, confidence=None, bbox=bbox))

        # The schema's top-level "text" is the primary full-text output --
        # a provider that fills "text" but leaves "blocks" empty (a common,
        # valid response shape; nothing requires per-block granularity) must
        # not have its content silently dropped just because block-based
        # reconstruction is what downstream code (OCRService.process's
        # reconstruct_text, and this project's own benchmark scoring) reads.
        if not blocks and text.strip():
            blocks = [TextBlock(text=text, confidence=None, bbox=None)]

        return ParsedReply(
            text=text,
            language=language,
            content_type=content_type,
            structured=True,
            blocks=blocks,
            document_blocks=document_blocks,
        )

    blocks = [TextBlock(text=content.strip(), confidence=None, bbox=None)] if content.strip() else []
    return ParsedReply(text=content, language=None, content_type=None, structured=False, blocks=blocks)


def _bbox_from_raw(raw) -> BoundingBox | None:
    if not raw or not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    x1, y1, x2, y2 = raw[0], raw[1], raw[2], raw[3]
    return BoundingBox(left=int(x1), top=int(y1), width=int(x2 - x1), height=int(y2 - y1))
