# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# TODO(shared-module): exact copy of experimentalist components/model_config.py; unify into a shared package.
import functools
import os
from urllib.parse import urlparse

from nooa.unifiedllm import CompletionClient


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} must be set")
    return value


def _optional_env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


@functools.cache
def get_smart_model() -> CompletionClient:
    """Return the cached smart (high-capability) LLM client configured from environment variables.

    Returns:
        CompletionClient: the singleton smart-model client.

    Raises:
        ValueError: if ``EXPERIMENTALIST_API_BASE`` or ``EXPERIMENTALIST_API_KEY`` are unset or empty.

    """
    api_base = _required_env("EXPERIMENTALIST_API_BASE")
    api_key = _required_env("EXPERIMENTALIST_API_KEY")
    name = _optional_env("EXPERIMENTALIST_SMART_MODEL_NAME", "openai/openai/openai/gpt-5.5")
    return CompletionClient(name, api_base=api_base, api_key=api_key)


@functools.cache
def get_mid_model() -> CompletionClient:
    """Return the cached mid-tier LLM client configured from environment variables.

    Returns:
        CompletionClient: the singleton mid-model client.

    Raises:
        ValueError: if ``EXPERIMENTALIST_API_BASE`` or ``EXPERIMENTALIST_API_KEY`` are unset or empty.

    """
    api_base = _required_env("EXPERIMENTALIST_API_BASE")
    api_key = _required_env("EXPERIMENTALIST_API_KEY")
    name = _optional_env("EXPERIMENTALIST_MID_MODEL_NAME", "openai/gcp/google/gemini-3.5-flash")
    return CompletionClient(name, api_base=api_base, api_key=api_key)


@functools.cache
def get_fast_model() -> CompletionClient:
    """Return the cached fast (low-latency) LLM client configured from environment variables.

    Returns:
        CompletionClient: the singleton fast-model client.

    Raises:
        ValueError: if ``EXPERIMENTALIST_API_BASE`` or ``EXPERIMENTALIST_API_KEY`` are unset or empty.

    """
    api_base = _required_env("EXPERIMENTALIST_API_BASE")
    api_key = _required_env("EXPERIMENTALIST_API_KEY")
    name = _optional_env("EXPERIMENTALIST_FAST_MODEL_NAME", "openai/openai/openai/gpt-5-mini")
    return CompletionClient(name, api_base=api_base, api_key=api_key)


def _mask_key(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"*****{value[-4:]}"


def _sanitize_url(url: str) -> str:
    """Strip userinfo, query, and fragment so credentials never leak via the log banner."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}{parsed.path}"


def log_model_config() -> str:
    """Return a formatted string summarising the current optimizer model configuration.

    Returns:
        str: a multi-line summary of smart model, fast model, API base, and masked API key.

    """
    smart = _optional_env("EXPERIMENTALIST_SMART_MODEL_NAME", "openai/openai/openai/gpt-5.5")
    mid = _optional_env("EXPERIMENTALIST_MID_MODEL_NAME", "openai/gcp/google/gemini-3.5-flash")
    fast = _optional_env("EXPERIMENTALIST_FAST_MODEL_NAME", "openai/openai/openai/gpt-5-mini")
    api_base = _required_env("EXPERIMENTALIST_API_BASE")
    api_key = _required_env("EXPERIMENTALIST_API_KEY")
    return (
        "Experimentalist model config:\n"
        f"  smart model: {smart}\n"
        f"  mid model:   {mid}\n"
        f"  fast model:  {fast}\n"
        f"  api base:    {_sanitize_url(api_base)}\n"
        f"  api key:     {_mask_key(api_key)}"
    )
