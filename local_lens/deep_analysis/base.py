"""Deep Analyze provider interface.

A `DeepAnalysisProvider` deliberately has the same shape as `OCREngine`
(`name`, `extract(image, langs) -> DocumentResult`) so any provider slots
directly into the existing `OCRService` without special-casing -- Deep
Analyze is "just another engine" from the service's point of view. The
separate protocol name exists so call sites can express intent ("this is a
remote, opt-in, image-leaves-the-device backend") and so future providers
aren't forced to conform to OCREngine's local-only assumptions if that ever
matters.

No provider here is hardwired to Paddle. PaddleOCR-VL is reachable only
through `PaddleVLLMProvider` (local_lens/deep_analysis/paddle_vllm_provider.py),
which talks to a self-hosted vLLM server over plain HTTP -- it does not
import or require the `paddleocr`/`paddlex` packages at all.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from PIL import Image

from local_lens.models import DocumentResult


@runtime_checkable
class DeepAnalysisProvider(Protocol):
    name: str

    def extract(self, image: Image.Image, langs: list[str]) -> DocumentResult:
        """Send `image` to the configured remote backend and return a result.

        Implementations must raise `DeepAnalysisError` (or a subclass) on
        failure with an actionable, secret-free message -- callers degrade
        to Fast mode rather than crashing.
        """
        ...


class DeepAnalysisError(Exception):
    """Base class for Deep Analyze provider failures."""


class DeepAnalysisNotConfigured(DeepAnalysisError):
    """No remote provider is configured (missing base URL/provider choice)."""


class DeepAnalysisAuthError(DeepAnalysisError):
    """Provider rejected the request as unauthenticated/unauthorized (401/403)."""


class DeepAnalysisRateLimited(DeepAnalysisError):
    """Provider returned 429."""


class DeepAnalysisServerError(DeepAnalysisError):
    """Provider returned 5xx."""


class DeepAnalysisTimeout(DeepAnalysisError):
    """Request exceeded the configured timeout."""


class DeepAnalysisBadResponse(DeepAnalysisError):
    """Provider responded but the payload could not be parsed."""
