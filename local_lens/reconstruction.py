"""Reading-order text reconstruction from spatial OCR blocks.

This replaces the old `" ".join(text for _, text, _ in results)` (which
discarded layout entirely and produced one giant line) with a deterministic,
bounding-box-based line grouping. It is intentionally simple -- a real
layout-aware model can replace this function later without touching callers.

Mixed-direction (Urdu+English) lines: because blocks within a line are
sorted by `bbox.left` -- their actual on-screen horizontal position -- this
already produces the correct visual reading order for mixed-script lines
without any script-aware reversal logic, since "left to right on screen" is
the right order regardless of which script sits where. What this can't fix:
if the OCR engine itself mis-orders characters *within* a single detected
block (a recognition error), that's upstream of this function.
"""

from __future__ import annotations

from local_lens.models import TextBlock


def reconstruct_text(blocks: list[TextBlock]) -> str:
    """Join blocks into multi-line text approximating natural reading order.

    Blocks are grouped into lines by vertical center proximity (rather than
    a fixed absolute pixel gap from a single running cursor, which drifts on
    tilted/noisy detections), then each line is sorted left-to-right and
    lines are ordered top-to-bottom.
    """
    positioned = [b for b in blocks if b.bbox is not None]
    unpositioned = [b for b in blocks if b.bbox is None]

    if not positioned:
        return " ".join(b.text for b in unpositioned)

    # Sort by vertical position first so line-grouping sees blocks roughly
    # top-to-bottom already.
    positioned.sort(key=lambda b: b.bbox.center_y)

    lines: list[list[TextBlock]] = []
    for block in positioned:
        placed = False
        for line in lines:
            # A block belongs to a line if its center falls within the
            # vertical span of the line's reference block (average height),
            # which tolerates minor baseline jitter without merging distinct
            # lines that happen to be close together.
            ref = line[0]
            half_height = max(ref.bbox.height, block.bbox.height) / 2
            if abs(block.bbox.center_y - ref.bbox.center_y) <= half_height:
                line.append(block)
                placed = True
                break
        if not placed:
            lines.append([block])

    lines.sort(key=lambda line: min(b.bbox.top for b in line))

    line_texts = []
    for line in lines:
        line.sort(key=lambda b: b.bbox.left)
        line_texts.append(" ".join(b.text for b in line))

    reconstructed = "\n".join(line_texts)
    if unpositioned:
        extra = " ".join(b.text for b in unpositioned)
        reconstructed = f"{reconstructed}\n{extra}" if reconstructed else extra

    return reconstructed
