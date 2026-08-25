"""Deep Analyze provider for Anthropic's Messages API.

Unlike Gemini (OpenAI-compatible beta endpoint), Fireworks, or a
self-hosted vLLM server, Claude's Messages API is genuinely NOT
OpenAI-compatible -- confirmed by research, not assumed:

  OpenAI:    {"type": "image_url", "image_url": {"url": "data:...;base64,..."}}
  Anthropic: {"type": "image", "source": {"type": "base64",
                                           "media_type": "image/png",
                                           "data": "<base64>"}}

different field names, different nesting, and the endpoint/auth scheme
differ too (`x-api-key` + `anthropic-version` headers vs. `Authorization:
Bearer`, `/v1/messages` vs. `/v1/chat/completions`). This is exactly the
"protocol differences require it" case the architecture calls for a
dedicated adapter, rather than trying to force it through
OpenAICompatibleVisionProvider (see local_lens/deep_analysis/base.py's
module docstring).

Reuses the same structured prompt (prompts.py) and reply parser
(response_parsing.py) as the OpenAI-compatible provider so bake-off
comparisons stay apples-to-apples.
"""

from __future__ import annotations

import base64
import io
import time

from PIL import Image

from local_lens.deep_analysis.base import (
    DeepAnalysisAuthError,
    DeepAnalysisBadResponse,
    DeepAnalysisError,
    DeepAnalysisRateLimited,
    DeepAnalysisServerError,
    DeepAnalysisTimeout,
)
from local_lens.deep_analysis.http_client import (
    HttpTimeout,
    HttpTransportError,
    Transport,
    post_json_with_retry,
    urllib_transport,
)
from local_lens.deep_analysis.prompts import DEEP_ANALYSIS_PROMPT
from local_lens.deep_analysis.response_parsing import parse_structured_reply
from local_lens.models import DocumentResult

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_BASE_URL = "https://api.anthropic.com/v1"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        max_retries: int = 1,
        transport: Transport = urllib_transport,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "anthropic-version": ANTHROPIC_VERSION}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _encode_image(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def extract(self, image: Image.Image, langs: list[str]) -> DocumentResult:
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": DEEP_ANALYSIS_PROMPT},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": self._encode_image(image),
                            },
                        },
                    ],
                }
            ],
        }

        url = f"{self.base_url}/messages"
        start = time.monotonic()
        try:
            response = post_json_with_retry(
                self._transport, url, self._headers(), payload, self.timeout, self.max_retries
            )
        except HttpTimeout as exc:
            raise DeepAnalysisTimeout(f"Request to {self.base_url} timed out after {self.timeout}s.") from exc
        except HttpTransportError as exc:
            raise DeepAnalysisError(f"Could not reach {self.base_url}: {exc}") from exc
        latency_ms = (time.monotonic() - start) * 1000

        if response.status in (401, 403):
            raise DeepAnalysisAuthError(
                f"{self.base_url} rejected the request as unauthorized (HTTP {response.status}). "
                "Check LOCAL_LENS_DEEP_API_KEY."
            )
        if response.status == 429:
            raise DeepAnalysisRateLimited(f"{self.base_url} rate-limited the request (HTTP 429).")
        if response.status >= 500:
            raise DeepAnalysisServerError(f"{self.base_url} returned a server error (HTTP {response.status}).")
        if response.status >= 400:
            raise DeepAnalysisError(f"{self.base_url} rejected the request (HTTP {response.status}).")

        try:
            body = response.json()
            content_blocks = body["content"]
            text_content = "".join(
                block.get("text", "") for block in content_blocks if block.get("type") == "text"
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DeepAnalysisBadResponse(f"Could not parse response from {self.base_url}: {exc}") from exc

        parsed = parse_structured_reply(text_content)
        metadata = {
            "provider": self.name,
            "remote": True,
            "model": self.model,
            "base_url": self.base_url,
            "latency_ms": round(latency_ms, 1),
            "http_status": response.status,
            "structured_response": parsed.structured,
        }
        if parsed.content_type:
            metadata["content_type"] = parsed.content_type

        return DocumentResult(
            text="",
            blocks=parsed.blocks,
            language=parsed.language or (langs[0] if langs else None),
            engine=self.name,
            metadata=metadata,
            document_blocks=parsed.document_blocks,
        )
