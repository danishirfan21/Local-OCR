"""Generic Deep Analyze provider for OpenAI-compatible vision endpoints.

Targets the `/v1/chat/completions` HTTP contract (system+user messages,
an `image_url` content block carrying a base64 data URL, a `choices[0].
message.content` string reply) that vLLM's OpenAI-compatible server and
most hosted VLM APIs implement. This is the base for both a self-hosted
PaddleOCR-VL-on-vLLM server (see paddle_vllm_provider.py) and any other
OpenAI-compatible host -- nothing here is Paddle-specific.

The request format was not guessed: it matches the publicly documented
OpenAI Chat Completions vision request shape, which is what vLLM's
`--served-model-name` OpenAI-compatible server implements. It has not been
exercised against a live server in this session (that would require a
running remote endpoint, which is out of scope until the user provisions
one) -- request/response handling is covered by mocked-transport unit
tests instead (tests/test_deep_analysis.py).
"""

from __future__ import annotations

import base64
import io
import json
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


class OpenAICompatibleVisionProvider:
    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
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
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _encode_image(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def extract(self, image: Image.Image, langs: list[str]) -> DocumentResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a precise document OCR and layout extraction assistant."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": DEEP_ANALYSIS_PROMPT},
                        {"type": "image_url", "image_url": {"url": self._encode_image(image)}},
                    ],
                },
            ],
            "max_tokens": 4096,
        }

        url = f"{self.base_url}/chat/completions"
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
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DeepAnalysisBadResponse(f"Could not parse response from {self.base_url}: {exc}") from exc

        usage = body.get("usage")
        return self._to_document_result(content, langs, latency_ms, response.status, usage)

    def _to_document_result(
        self,
        content: str,
        langs: list[str],
        latency_ms: float,
        http_status: int,
        usage: dict | None = None,
    ) -> DocumentResult:
        parsed = parse_structured_reply(content)

        metadata = {
            "provider": self.name,
            "remote": True,
            "model": self.model,
            "base_url": self.base_url,
            "latency_ms": round(latency_ms, 1),
            "http_status": http_status,
            "structured_response": parsed.structured,
        }
        if parsed.content_type:
            metadata["content_type"] = parsed.content_type
        if isinstance(usage, dict):
            metadata["usage"] = {
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
            }

        return DocumentResult(
            text="",
            blocks=parsed.blocks,
            language=parsed.language or (langs[0] if langs else None),
            engine=self.name,
            metadata=metadata,
            document_blocks=parsed.document_blocks,
        )
