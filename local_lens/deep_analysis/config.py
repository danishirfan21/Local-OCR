"""BYOK configuration for Deep Analyze, read from environment variables.

Local Lens does not own or operate any inference infrastructure -- Deep
Analyze is bring-your-own-endpoint by design (see docs/V4_DIRECTION.md /
docs/V4_IMPLEMENTATION.md "Deep Analyze providers"). No default provider,
base URL, or API key ships with the app; if nothing is configured, Deep
Analyze is simply unavailable and Fast mode is unaffected.

    LOCAL_LENS_DEEP_PROVIDER   "openai-compatible" | "paddle-vllm"
    LOCAL_LENS_DEEP_BASE_URL   e.g. https://your-endpoint/v1
    LOCAL_LENS_DEEP_API_KEY    optional -- omit for unauthenticated servers
    LOCAL_LENS_DEEP_MODEL      optional -- provider-specific default if unset
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from local_lens.backends import BackendStatus
from local_lens.deep_analysis.base import DeepAnalysisProvider

_PROVIDER_NAMES = ("openai-compatible", "paddle-vllm")
_DEFAULT_MODEL_BY_PROVIDER = {
    "openai-compatible": "gpt-4o-mini",
    "paddle-vllm": "PaddleOCR-VL-1.6",
}


@dataclass(frozen=True)
class DeepProviderConfig:
    provider: str
    base_url: str
    api_key: str | None
    model: str


def load_deep_provider_config(env: dict | None = None) -> DeepProviderConfig | None:
    """Read config from `env` (defaults to os.environ). Returns None if
    Deep Analyze isn't configured at all (no base URL set)."""
    env = env if env is not None else os.environ

    base_url = env.get("LOCAL_LENS_DEEP_BASE_URL", "").strip()
    if not base_url:
        return None

    provider = env.get("LOCAL_LENS_DEEP_PROVIDER", "openai-compatible").strip() or "openai-compatible"
    api_key = env.get("LOCAL_LENS_DEEP_API_KEY", "").strip() or None
    model = env.get("LOCAL_LENS_DEEP_MODEL", "").strip() or _DEFAULT_MODEL_BY_PROVIDER.get(
        provider, "gpt-4o-mini"
    )

    return DeepProviderConfig(provider=provider, base_url=base_url, api_key=api_key, model=model)


def describe_deep_provider_config(env: dict | None = None) -> BackendStatus:
    """Status for the "model availability" UI/CLI -- never raises."""
    config = load_deep_provider_config(env)
    if config is None:
        return BackendStatus(
            name="deep_analyze",
            available=False,
            mode="remote",
            reason="not configured -- set LOCAL_LENS_DEEP_BASE_URL to enable",
        )
    if config.provider not in _PROVIDER_NAMES:
        return BackendStatus(
            name="deep_analyze",
            available=False,
            mode="remote",
            reason=f"unknown provider '{config.provider}' (expected one of {_PROVIDER_NAMES})",
        )
    return BackendStatus(
        name="deep_analyze",
        available=True,
        mode="remote",
        reason=f"{config.provider} @ {config.base_url}",
    )


def build_deep_provider(env: dict | None = None) -> DeepAnalysisProvider | None:
    """Construct the configured provider, or None if unconfigured/invalid.
    Never makes a network call -- construction is pure configuration."""
    config = load_deep_provider_config(env)
    if config is None or config.provider not in _PROVIDER_NAMES:
        return None

    if config.provider == "paddle-vllm":
        from local_lens.deep_analysis.paddle_vllm_provider import PaddleVLLMProvider

        return PaddleVLLMProvider(base_url=config.base_url, api_key=config.api_key, model=config.model)

    from local_lens.deep_analysis.openai_compatible_provider import OpenAICompatibleVisionProvider

    return OpenAICompatibleVisionProvider(base_url=config.base_url, api_key=config.api_key, model=config.model)
