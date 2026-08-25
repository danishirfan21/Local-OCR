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
from local_lens.models import BoundingBox, DocumentBlock, DocumentResult, TextBlock

_STRUCTURE_PROMPT = (
    "Extract all text from this image. Respond with ONLY a JSON object "
    "(no markdown fences, no commentary) matching this schema: "
    '{"text": "<full extracted text, reading order>", '
    '"content_type": "<text|code|table|unknown>", '
    '"language": "<best-guess ISO 639-1 code or null>", '
    '"blocks": [{"type": "<text|title|table|formula|image|unknown>", '
    '"text": "<block text>"}]}. '
    "Omit fields you cannot determine rather than guessing. If the image "
    "contains a table, represent it as a markdown table inside the "
    "relevant block's text."
)


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
                        {"type": "text", "text": _STRUCTURE_PROMPT},
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

        return self._to_document_result(content, langs, latency_ms, response.status)

    def _to_document_result(
        self, content: str, langs: list[str], latency_ms: float, http_status: int
    ) -> DocumentResult:
        structured: dict | None = None
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:]
            stripped = stripped.strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                structured = parsed
        except json.JSONDecodeError:
            structured = None

        blocks: list[TextBlock] = []
        document_blocks: list[DocumentBlock] = []

        if structured is not None:
            text = str(structured.get("text") or "")
            language = structured.get("language")
            for raw_block in structured.get("blocks") or []:
                if not isinstance(raw_block, dict):
                    continue
                block_text = str(raw_block.get("text") or "")
                block_type = str(raw_block.get("type") or "text")
                bbox = _bbox_from_raw(raw_block.get("bbox"))
                document_blocks.append(DocumentBlock(type=block_type, text=block_text, bbox=bbox, metadata={}))
                if block_text:
                    blocks.append(TextBlock(text=block_text, confidence=None, bbox=bbox))
            content_type = structured.get("content_type")
        else:
            text = content
            language = None
            content_type = None
            if text.strip():
                blocks.append(TextBlock(text=text.strip(), confidence=None, bbox=None))

        metadata = {
            "provider": self.name,
            "remote": True,
            "model": self.model,
            "base_url": self.base_url,
            "latency_ms": round(latency_ms, 1),
            "http_status": http_status,
            "structured_response": structured is not None,
        }
        if content_type:
            metadata["content_type"] = content_type

        return DocumentResult(
            text="",
            blocks=blocks,
            language=language or (langs[0] if langs else None),
            engine=self.name,
            metadata=metadata,
            document_blocks=document_blocks,
        )


def _bbox_from_raw(raw) -> BoundingBox | None:
    if not raw or not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    x1, y1, x2, y2 = raw[0], raw[1], raw[2], raw[3]
    return BoundingBox(left=int(x1), top=int(y1), width=int(x2 - x1), height=int(y2 - y1))
