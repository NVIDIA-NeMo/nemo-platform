# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLM credentials and model selection for the Insights Analyst.

The Analyst owns its own contract — ``ANALYST_API_BASE``, ``ANALYST_API_KEY``, and
``ANALYST_MODEL_NAME`` — and does not fall back to Experimentalist, Eval Author,
``INFERENCE_API_KEY``, or ``OPENAI_*`` credentials. Profile ``.env`` files next to
``optimizer.yaml`` supply them; doctor and preflight report what resolved.

The default path talks Anthropic Messages to the NVIDIA Inference Gateway
(Opus + adaptive thinking). When the base is a plain OpenAI-compatible endpoint,
the analyst builds an OpenAI chat model instead and skips Anthropic-only settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider

_GATEWAY_HOST = "inference-api.nvidia.com"
GATEWAY_ANTHROPIC_BASE = "https://inference-api.nvidia.com"

DEFAULT_MODEL = "aws/anthropic/bedrock-claude-opus-4-8"
_THINKING_EFFORT = "medium"
_MAX_TOKENS = 16000


def _env(name: str) -> str | None:
    """Return a stripped env value, or ``None`` when unset/empty."""
    value = os.environ.get(name, "").strip()
    return value or None


def is_anthropic_host(hostname: str | None) -> bool:
    return hostname in {_GATEWAY_HOST, "api.anthropic.com"}


def strip_openai_v1_suffix(base: str) -> str:
    """Anthropic SDKs append ``/v1/messages``; drop a trailing OpenAI-style ``/v1``."""
    trimmed = base.rstrip("/")
    if trimmed.endswith("/v1"):
        return trimmed[: -len("/v1")]
    return trimmed


def api_base() -> str:
    """Return ``ANALYST_API_BASE``, defaulting to the NVIDIA Inference Gateway root.

    Raises:
        ValueError: if somehow empty after the default (should not happen).
    """
    base = _env("ANALYST_API_BASE") or GATEWAY_ANTHROPIC_BASE
    if not base:
        raise ValueError("ANALYST_API_BASE must be set")
    return base


def api_key() -> str:
    """Return ``ANALYST_API_KEY``.

    Raises:
        ValueError: if ``ANALYST_API_KEY`` is unset or empty.
    """
    key = _env("ANALYST_API_KEY")
    if key:
        return key
    raise ValueError("ANALYST_API_KEY must be set")


def model_name() -> str:
    """Return ``ANALYST_MODEL_NAME`` (default: Opus on the gateway)."""
    return _env("ANALYST_MODEL_NAME") or DEFAULT_MODEL


def uses_anthropic_messages(base: str | None = None) -> bool:
    """Whether the Analyst should speak Anthropic Messages against ``base``."""
    resolved = base if base is not None else api_base()
    try:
        hostname = urlsplit(resolved).hostname
    except ValueError:
        return False
    return is_anthropic_host(hostname)


def _mask_key(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"*****{value[-4:]}"


def sanitize_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}{parsed.path}"


@dataclass(frozen=True)
class ResolvedAnalystModel:
    """Resolved Analyst model identity for doctor / preflight display."""

    model_name: str
    api_base: str
    api_key_set: bool
    transport: str


def resolve_model_config() -> ResolvedAnalystModel:
    """Resolve Analyst model settings without building a client."""
    base = api_base()
    return ResolvedAnalystModel(
        model_name=model_name(),
        api_base=base,
        api_key_set=bool(_env("ANALYST_API_KEY")),
        transport="anthropic-messages" if uses_anthropic_messages(base) else "openai-chat",
    )


def log_model_config() -> str:
    """Return a formatted summary of the resolved Analyst model configuration."""
    resolved = resolve_model_config()
    key = _env("ANALYST_API_KEY") or ""
    return (
        "Analyst model config:\n"
        f"  model:     {resolved.model_name}\n"
        f"  api base:  {sanitize_url(resolved.api_base)}\n"
        f"  api key:   {_mask_key(key) if key else '(unset)'}\n"
        f"  transport: {resolved.transport}"
    )


def build_model_and_settings() -> tuple[Model, Any]:
    """Build the Pydantic AI model and settings for the Analyst.

    Anthropic Messages (gateway / Anthropic) keep adaptive thinking. OpenAI-compatible
    bases use chat completions without Anthropic-only settings.
    """
    base = api_base()
    key = api_key()
    name = model_name()
    if uses_anthropic_messages(base):
        anthropic_base = strip_openai_v1_suffix(base)
        return (
            AnthropicModel(
                name,
                provider=AnthropicProvider(api_key=key, base_url=anthropic_base),
            ),
            AnthropicModelSettings(
                max_tokens=_MAX_TOKENS,
                anthropic_thinking={"type": "adaptive"},
                anthropic_effort=_THINKING_EFFORT,
            ),
        )
    openai_base = base if base.rstrip("/").endswith("/v1") else f"{base.rstrip('/')}/v1"
    return (
        OpenAIChatModel(
            name,
            provider=OpenAIProvider(api_key=key, base_url=openai_base),
        ),
        OpenAIChatModelSettings(max_tokens=_MAX_TOKENS),
    )
