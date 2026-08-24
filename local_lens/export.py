"""Export DocumentResult to plain text, Markdown, and JSON."""

from __future__ import annotations

import json

from local_lens.models import DocumentResult


def to_txt(result: DocumentResult) -> str:
    return result.text


def to_markdown(result: DocumentResult) -> str:
    lines = ["# Extracted text", ""]
    content_type = result.metadata.get("content_type")
    if content_type:
        lines.append(f"*Detected content: {content_type}*")
        lines.append("")

    if content_type == "code":
        lines.append("```")
        lines.append(result.text)
        lines.append("```")
    else:
        lines.append(result.text)

    return "\n".join(lines)


def to_json(result: DocumentResult) -> str:
    payload = {
        "engine": result.engine,
        "language": result.language,
        "text": result.text,
        "average_confidence": result.average_confidence,
        "metadata": result.metadata,
        "blocks": [
            {
                "text": block.text,
                "confidence": block.confidence,
                "bounding_box": (
                    {
                        "left": block.bbox.left,
                        "top": block.bbox.top,
                        "width": block.bbox.width,
                        "height": block.bbox.height,
                    }
                    if block.bbox is not None
                    else None
                ),
            }
            for block in result.blocks
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
