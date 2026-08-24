"""Centralized "Auto" engine selection policy.

Kept out of Streamlit entirely so the routing decision (and its rationale)
is reusable by a future CLI/API and independently testable. The policy is
intentionally conservative -- it picks a *reasonable default*, not a
provably optimal one, and always explains itself rather than acting as
opaque magic.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from local_lens.input_analysis import (
    INPUT_DOCUMENT_SCAN,
    INPUT_PHOTO,
    INPUT_SCREENSHOT,
    classify_input,
)


@dataclass
class RoutingDecision:
    engine: str
    reason: str
    input_type: str
    input_type_confidence: float


# Conservative policy, informed by the V2 benchmark finding that PaddleOCR's
# default document-oriented pipeline underperformed EasyOCR on small, clean
# digital screenshots (see benchmarks/README.md). Document-like/photographed
# input is routed to PaddleOCR, whose pipeline includes doc
# orientation/unwarping steps that are actively useful there.
_INPUT_TYPE_TO_ENGINE = {
    INPUT_SCREENSHOT: ("easyocr", "short/clean digital screenshot"),
    INPUT_DOCUMENT_SCAN: ("paddleocr", "document-like layout, benefits from orientation/unwarping"),
    INPUT_PHOTO: ("paddleocr", "photographed input, benefits from orientation/unwarping"),
}
_DEFAULT_ENGINE = ("easyocr", "input type unclear, defaulting to the faster/lighter engine")


def choose_engine(image: Image.Image, available_engines: list[str]) -> RoutingDecision:
    """Pick an engine for `image`, preferring available_engines' order as fallback.

    If the routed engine isn't in `available_engines` (e.g. PaddleOCR isn't
    installed), falls back to the first available engine and says so in the
    reason -- never silently substitutes without explanation.
    """
    input_type, confidence = classify_input(image)
    engine, base_reason = _INPUT_TYPE_TO_ENGINE.get(input_type, _DEFAULT_ENGINE)

    if engine not in available_engines:
        if not available_engines:
            raise RuntimeError("No OCR engines available to route to.")
        fallback = available_engines[0]
        return RoutingDecision(
            engine=fallback,
            reason=f"{base_reason}, but {engine} isn't installed -- using {fallback} instead",
            input_type=input_type,
            input_type_confidence=confidence,
        )

    return RoutingDecision(
        engine=engine,
        reason=base_reason,
        input_type=input_type,
        input_type_confidence=confidence,
    )
