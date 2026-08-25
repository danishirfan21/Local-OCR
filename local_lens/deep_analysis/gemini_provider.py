"""Deep Analyze provider for Google Gemini's native `generateContent` API.

Google does run an OpenAI-compatibility beta endpoint, but Google's own
docs mark it "still in beta while we extend feature support," and its
structured-output mechanism (`response_format`) doesn't map onto Gemini's
native one (`response_mime_type` + `response_schema`) -- see
docs/DEEP_PROVIDER_EVALUATION.md's Gemini section. This adapter targets the
native REST API directly instead of routing through the beta compatibility
layer, so structured JSON output and usage-metadata extraction are both
real, not best-effort through a shim.

Secret hygiene note: Gemini's REST docs commonly show the API key as a
`?key=...` query parameter. This adapter deliberately uses the
`x-goog-api-key` HEADER instead (documented as an equally valid current
auth method) so the key is never embedded in a URL that could end up in a
log line, error message, or stored request record -- consistent with this
project's "never log a credential" rule.
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

DEFAULT_MODEL = "gemini-3.1-flash-lite"  # gemini-2.5-flash-lite is scheduled to retire no earlier than 2026-10-16
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    name = "gemini"

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
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        return headers

    def _encode_image(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def extract(self, image: Image.Image, langs: list[str]) -> DocumentResult:
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": DEEP_ANALYSIS_PROMPT},
                        {"inline_data": {"mime_type": "image/png", "data": self._encode_image(image)}},
                    ]
                }
            ],
            "generationConfig": {"response_mime_type": "application/json"},
        }

        # Model + action are in the URL path (no key), matching Gemini's
        # documented REST shape -- e.g. /v1beta/models/gemini-2.5-flash-lite:generateContent
        url = f"{self.base_url}/models/{self.model}:generateContent"
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
                "Check the Gemini API key."
            )
        if response.status == 429:
            raise DeepAnalysisRateLimited(f"{self.base_url} rate-limited the request (HTTP 429).")
        if response.status >= 500:
            raise DeepAnalysisServerError(f"{self.base_url} returned a server error (HTTP {response.status}).")
        if response.status >= 400:
            # Gemini uses 400 for some invalid-API-key cases too, not just
            # malformed requests -- surfaced as a generic error rather than
            # guessing which, since the body's exact shape isn't guaranteed.
            raise DeepAnalysisError(f"{self.base_url} rejected the request (HTTP {response.status}).")

        try:
            body = response.json()
            candidates = body["candidates"]
            parts = candidates[0]["content"]["parts"]
            text_content = "".join(part.get("text", "") for part in parts)
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

        usage = body.get("usageMetadata")
        if isinstance(usage, dict):
            metadata["usage"] = {
                "input_tokens": usage.get("promptTokenCount"),
                "output_tokens": usage.get("candidatesTokenCount"),
            }

        return DocumentResult(
            text="",
            blocks=parsed.blocks,
            language=parsed.language or (langs[0] if langs else None),
            engine=self.name,
            metadata=metadata,
            document_blocks=parsed.document_blocks,
        )
