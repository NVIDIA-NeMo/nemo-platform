# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Eval Author prefers AUTHOR_* and falls back to EXPERIMENTALIST_* for insight-mode compatibility.
# Shared Experimentalist helpers still read EXPERIMENTALIST_*; bridge_author_env_to_experimentalist()
# copies AUTHOR_* into unset EXPERIMENTALIST_* slots for standalone runs.
import functools
import os
from urllib.parse import urlparse

from nooa.unifiedllm import CompletionClient

_GATEWAY_HOST = "inference-api.nvidia.com"


def _env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _required_author_env(primary: str, fallback: str) -> str:
    value = _env(primary, fallback)
    if not value:
        raise ValueError(f"{primary} (or {fallback}) must be set")
    return value


def _api_base() -> str:
    return _required_author_env("AUTHOR_API_BASE", "EXPERIMENTALIST_API_BASE")


def _api_key() -> str:
    """Resolve the LLM API key for Eval Author.

    Preference order:
    1. ``AUTHOR_API_KEY``
    2. ``EXPERIMENTALIST_API_KEY``
    3. ``INFERENCE_API_KEY`` when the resolved base is the NVIDIA Inference Gateway
    """
    key = _env("AUTHOR_API_KEY", "EXPERIMENTALIST_API_KEY")
    if key:
        return key
    base = _api_base()
    try:
        host = urlparse(base).hostname
    except ValueError:
        host = None
    if host == _GATEWAY_HOST:
        inference = _env("INFERENCE_API_KEY")
        if inference:
            return inference
    raise ValueError(
        "AUTHOR_API_KEY (or EXPERIMENTALIST_API_KEY) must be set; "
        "when using the NVIDIA Inference Gateway, INFERENCE_API_KEY is also accepted"
    )


@functools.cache
def get_smart_model() -> CompletionClient:
    """Return the cached smart (high-capability) LLM client configured from environment variables.

    Returns:
        CompletionClient: the singleton smart-model client.

    Raises:
        ValueError: if Eval Author / Experimentalist API credentials are unset or empty.

    """
    name = _env(
        "AUTHOR_SMART_MODEL_NAME",
        "EXPERIMENTALIST_SMART_MODEL_NAME",
        default="openai/openai/openai/gpt-5.5",
    )
    assert name is not None
    return CompletionClient(name, api_base=_api_base(), api_key=_api_key())


@functools.cache
def get_mid_model() -> CompletionClient:
    """Return the cached mid-tier LLM client configured from environment variables.

    Returns:
        CompletionClient: the singleton mid-model client.

    Raises:
        ValueError: if Eval Author / Experimentalist API credentials are unset or empty.

    """
    name = _env(
        "AUTHOR_MID_MODEL_NAME",
        "EXPERIMENTALIST_MID_MODEL_NAME",
        default="openai/gcp/google/gemini-3.5-flash",
    )
    assert name is not None
    return CompletionClient(name, api_base=_api_base(), api_key=_api_key())


@functools.cache
def get_fast_model() -> CompletionClient:
    """Return the cached fast (low-latency) LLM client configured from environment variables.

    Returns:
        CompletionClient: the singleton fast-model client.

    Raises:
        ValueError: if Eval Author / Experimentalist API credentials are unset or empty.

    """
    name = _env(
        "AUTHOR_FAST_MODEL_NAME",
        "EXPERIMENTALIST_FAST_MODEL_NAME",
        default="openai/openai/openai/gpt-5-mini",
    )
    assert name is not None
    return CompletionClient(name, api_base=_api_base(), api_key=_api_key())


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


def bridge_author_env_to_experimentalist() -> None:
    """Copy ``AUTHOR_*`` into unset ``EXPERIMENTALIST_*`` slots.

    Eval Author owns ``AUTHOR_*`` credentials for its own LLM clients. Shared
    Experimentalist helpers (for example ``TraceAnalyzer``) still read
    ``EXPERIMENTALIST_*``. Bridging keeps standalone Author runs working without
    duplicating credentials.
    """
    pairs = (
        ("AUTHOR_API_BASE", "EXPERIMENTALIST_API_BASE"),
        ("AUTHOR_API_KEY", "EXPERIMENTALIST_API_KEY"),
        ("AUTHOR_SMART_MODEL_NAME", "EXPERIMENTALIST_SMART_MODEL_NAME"),
        ("AUTHOR_MID_MODEL_NAME", "EXPERIMENTALIST_MID_MODEL_NAME"),
        ("AUTHOR_FAST_MODEL_NAME", "EXPERIMENTALIST_FAST_MODEL_NAME"),
    )
    for src, dst in pairs:
        value = os.environ.get(src, "").strip()
        if value and not os.environ.get(dst, "").strip():
            os.environ[dst] = value


def log_model_config() -> str:
    """Return a formatted string summarising the current Eval Author model configuration.

    Returns:
        str: a multi-line summary of smart model, fast model, API base, and masked API key.

    """
    smart = _env(
        "AUTHOR_SMART_MODEL_NAME",
        "EXPERIMENTALIST_SMART_MODEL_NAME",
        default="openai/openai/openai/gpt-5.5",
    )
    mid = _env(
        "AUTHOR_MID_MODEL_NAME",
        "EXPERIMENTALIST_MID_MODEL_NAME",
        default="openai/gcp/google/gemini-3.5-flash",
    )
    fast = _env(
        "AUTHOR_FAST_MODEL_NAME",
        "EXPERIMENTALIST_FAST_MODEL_NAME",
        default="openai/openai/openai/gpt-5-mini",
    )
    assert smart is not None and mid is not None and fast is not None
    api_base = _api_base()
    api_key = _api_key()
    return (
        f"smart model: {smart}\n"
        f"mid model:   {mid}\n"
        f"fast model:  {fast}\n"
        f"api base:    {_sanitize_url(api_base)}\n"
        f"api key:     {_mask_key(api_key)}"
    )
