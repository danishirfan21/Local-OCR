"""PaddleOCR-VL over a self-hosted vLLM server, called directly over HTTP.

PaddleOCR-VL's own docs (see docs/V4_DIRECTION.md's hosted-inference
research) describe `vl_rec_backend="vllm-server"` /
`vl_rec_server_url=...` as the officially supported way to run recognition
against a remote vLLM deployment, and vLLM's OpenAI-compatible server
exposes that model over the same `/v1/chat/completions` contract as any
other OpenAI-compatible host. So this is intentionally a thin
configuration wrapper around `OpenAICompatibleVisionProvider` -- calling
the server's HTTP API directly -- rather than installing `paddlex`/
`paddleocr` locally to use their client convenience wrapper, which would
reintroduce the multi-GB dependency stack this V4 pass removed from the
laptop.
"""

from __future__ import annotations

from local_lens.deep_analysis.http_client import Transport, urllib_transport
from local_lens.deep_analysis.openai_compatible_provider import OpenAICompatibleVisionProvider

DEFAULT_MODEL = "PaddleOCR-VL-1.6"


class PaddleVLLMProvider(OpenAICompatibleVisionProvider):
    name = "paddle-vllm"

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        max_retries: int = 1,
        transport: Transport = urllib_transport,
    ):
        # Deep Analyze's own audit measured 8-132s CPU latency for
        # PaddleOCR-VL locally; a remote GPU server should be faster, but
        # the default timeout stays generous rather than assuming.
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
        )
