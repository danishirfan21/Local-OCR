"""Minimal HTTP transport for remote Deep Analyze providers.

Deliberately stdlib-only (`urllib.request`) rather than adding `requests`/
`httpx` as a dependency -- Deep Analyze is one HTTP POST per request, not
enough to justify a new dependency for a laptop that's meant to stay lean.
`Transport` is a small injectable seam so provider tests can swap in a fake
transport instead of hitting the network (see tests/test_deep_analysis.py).

Retries are conservative on purpose: only transient failures (timeout,
5xx, 429) get one retry; 401/403/other 4xx never retry, since a wrong API
key or malformed request won't fix itself, and Deep Analyze providers may
charge per request.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_REDACTED = "***REDACTED***"


@dataclass
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self) -> dict:
        return json.loads(self.body.decode("utf-8"))


class HttpTimeout(Exception):
    pass


class HttpTransportError(Exception):
    """Network-level failure (DNS, connection refused, etc.) -- not an HTTP status."""


Transport = Callable[[str, dict[str, str], bytes, float], HttpResponse]


def urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> HttpResponse:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(
                status=response.status,
                body=response.read(),
                headers=dict(response.headers),
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(status=exc.code, body=exc.read(), headers=dict(exc.headers or {}))
    except TimeoutError as exc:
        raise HttpTimeout(str(exc)) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise HttpTimeout(str(exc)) from exc
        raise HttpTransportError(str(exc)) from exc


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """For logging only -- never emit Authorization/API-key header values."""
    redacted = {}
    for key, value in headers.items():
        if key.lower() in ("authorization", "x-api-key", "api-key"):
            redacted[key] = _REDACTED
        else:
            redacted[key] = value
    return redacted


def post_json_with_retry(
    transport: Transport,
    url: str,
    headers: dict[str, str],
    payload: dict,
    timeout: float,
    max_retries: int = 1,
    backoff_seconds: float = 1.0,
) -> HttpResponse:
    body = json.dumps(payload).encode("utf-8")
    attempt = 0
    last_exc: Exception | None = None

    while attempt <= max_retries:
        try:
            response = transport(url, headers, body, timeout)
        except HttpTimeout as exc:
            last_exc = exc
            if attempt == max_retries:
                raise
        else:
            if response.status not in _RETRYABLE_STATUSES or attempt == max_retries:
                return response
            last_exc = None

        attempt += 1
        if attempt <= max_retries:
            time.sleep(backoff_seconds)

    if last_exc is not None:
        raise last_exc
    raise HttpTransportError("Request failed with no response and no exception -- this should not happen.")
