# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import functools
import os
from typing import Any, cast
from urllib.parse import urlparse

from nooa.unifiedllm import CompletionClient


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} must be set")
    return value


def _optional_env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


_DEFAULTS = {
    "smart": "openai/openai/openai/gpt-5.5",
    "mid": "openai/gcp/google/gemini-3.5-flash",
    "fast": "openai/openai/openai/gpt-5-mini",
}


def model_name(tier: str) -> str:
    """Return the configured model name for *tier* (``smart``/``mid``/``fast``)."""
    return _optional_env(f"EXPERIMENTALIST_{tier.upper()}_MODEL_NAME", _DEFAULTS[tier])


@functools.cache
def _client(name: str, api_base: str, api_key: str) -> CompletionClient:
    """Cache on the full identity, not the tier: two tiers may name the same model,
    and a caller may legitimately switch endpoint or key within one process."""
    return CompletionClient(name, api_base=api_base, api_key=api_key)


def get_model(tier: str) -> CompletionClient:
    """Build (or reuse) the client for *tier*, reading credentials at call time.

    Raises:
        ValueError: if ``EXPERIMENTALIST_API_BASE`` or ``EXPERIMENTALIST_API_KEY``
            are unset or empty.

    """
    return _client(
        model_name(tier),
        _required_env("EXPERIMENTALIST_API_BASE"),
        _required_env("EXPERIMENTALIST_API_KEY"),
    )


class LazyModel:
    """Deferred :class:`CompletionClient` for sites that cannot resolve at call time.

    Agent classes resolve their tier in ``__init__``. Method-level overrides
    (``@strategy(..., llm=...)``) are decorator arguments, so they evaluate when the
    module is imported -- before credentials are necessarily set. This proxy keeps the
    override declarative while deferring construction to first use, which is what makes
    importing a component module credential-free.
    """

    def __init__(self, tier: str) -> None:
        self._tier = tier
        self._resolved: CompletionClient | None = None

    def _target(self) -> CompletionClient:
        if self._resolved is None:
            self._resolved = get_model(self._tier)
        return self._resolved

    def __getattr__(self, item: str) -> Any:
        return getattr(self._target(), item)

    def __repr__(self) -> str:
        state = "unresolved" if self._resolved is None else repr(self._resolved)
        return f"LazyModel(tier={self._tier!r}, {state})"


def lazy_model(tier: str) -> CompletionClient:
    """A :class:`LazyModel` typed as a client, for ``@strategy(llm=...)`` overrides.

    The cast is deliberate: ``LazyModel`` is a forwarding proxy, not a subclass. nooa
    accepts the override as ``Any``, stores it with ``setattr`` and reads it back with
    ``getattr`` without an ``isinstance`` check, so a proxy is transparent to it.
    """
    return cast(CompletionClient, LazyModel(tier))


def get_smart_model() -> CompletionClient:
    """Return the smart (high-capability) client, resolved from the environment."""
    return get_model("smart")


def get_mid_model() -> CompletionClient:
    """Return the mid-tier client, resolved from the environment."""
    return get_model("mid")


def get_fast_model() -> CompletionClient:
    """Return the fast (low-latency) client, resolved from the environment."""
    return get_model("fast")


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
    smart, mid, fast = (model_name(tier) for tier in ("smart", "mid", "fast"))
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
