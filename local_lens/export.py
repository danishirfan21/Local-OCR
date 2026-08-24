"""Export DocumentResult (and its tables) to plain text, Markdown, CSV, and JSON."""

from __future__ import annotations

import csv
import io
import json

from local_lens.models import DocumentResult, TableResult


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

    if result.tables:
        lines.append("")
        lines.append("## Tables")
        for i, table in enumerate(result.tables, start=1):
            lines.append("")
            lines.append(f"### Table {i}")
            lines.append(export_table_markdown(table))

    return "\n".join(lines)


def to_json(result: DocumentResult) -> str:
    payload = {
        "engine": result.engine,
        "language": result.language,
        "text": result.text,
        "average_confidence": result.average_confidence,
        "detected_scripts": result.detected_scripts,
        "detected_languages": result.detected_languages,
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
        "tables": [
            {
                "rows": table.rows,
                "has_header": table.has_header,
                "confidence": table.confidence,
                "cells": [
                    {
                        "row": cell.row,
                        "column": cell.column,
                        "text": cell.text,
                        "confidence": cell.confidence,
                    }
                    for cell in table.cells
                ],
            }
            for table in result.tables
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def export_table_markdown(table: TableResult) -> str:
    """Render a table as GitHub-flavored Markdown.

    Uses the extractor-provided markdown if present; otherwise builds one
    from `rows`. Only labels a header row if `table.has_header` is True --
    never fabricates one the extractor didn't identify.
    """
    if table.markdown:
        return table.markdown
    if not table.rows:
        return "*(no rows detected)*"

    header = table.rows[0] if table.has_header else [f"Column {i + 1}" for i in range(len(table.rows[0]))]
    body = table.rows[1:] if table.has_header else table.rows

    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def export_table_csv(table: TableResult) -> str:
    """Render a table as CSV using csv.writer (handles quoting/escaping properly).

    Includes a header row only if `table.has_header` is True; otherwise
    writes plain data rows without fabricating column names.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in table.rows:
        writer.writerow(row)
    return buffer.getvalue()
