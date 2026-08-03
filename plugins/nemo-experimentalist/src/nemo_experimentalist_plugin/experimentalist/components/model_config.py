# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import functools
from typing import Any, cast
from urllib.parse import urlparse

from nemo_experimentalist_plugin.settings import TIERS, ExperimentalistConfig
from nooa.unifiedllm import CompletionClient

_ENV_PREFIX = "NEMO_EXPERIMENTALIST_"


def _settings() -> ExperimentalistConfig:
    """Return the resolved deployment settings.

    ``NemoConfig.get()`` caches, so this is cheap to call per lookup and picks up a
    ``Configuration.clear_cache()`` in tests.
    """
    return ExperimentalistConfig.get()


def _required(value: str | None, env_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{env_name} must be set")
    return value.strip()


def model_name(tier: str) -> str:
    """Return the configured model name for *tier* (``smart``/``mid``/``fast``).

    No default: a model name is only meaningful against a specific endpoint, so there is
    no portable value to fall back to. Failing here beats failing at the first LLM call,
    minutes into a run.

    Raises:
        ValueError: if the tier is unknown, or is configured nowhere.

    """
    if tier not in TIERS:
        raise ValueError(f"unknown model tier {tier!r}")
    configured = getattr(_settings().models, tier)
    return _required(configured, f"{_ENV_PREFIX}MODELS_{tier.upper()}")


@functools.cache
def _client(name: str, api_base: str, api_key: str) -> CompletionClient:
    """Cache on the full identity, not the tier: two tiers may name the same model,
    and a caller may legitimately switch endpoint or key within one process."""
    return CompletionClient(name, api_base=api_base, api_key=api_key)


def api_base() -> str:
    """Return the configured endpoint base URL.

    Raises:
        ValueError: if it is configured nowhere.

    """
    return _required(_settings().api_base, f"{_ENV_PREFIX}API_BASE")


def api_key() -> str:
    """Return the configured endpoint credential.

    Raises:
        ValueError: if it is configured nowhere.

    """
    secret = _settings().api_key
    return _required(secret.get_secret_value() if secret else None, f"{_ENV_PREFIX}API_KEY")


def get_model(tier: str) -> CompletionClient:
    """Build (or reuse) the client for *tier*, resolving settings at call time.

    Raises:
        ValueError: if the endpoint, the credential, or the tier's model name is
            configured nowhere.

    """
    return _client(model_name(tier), api_base(), api_key())


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

    def _shown(tier: str) -> str:
        try:
            return model_name(tier)
        except ValueError:
            return "(unset)"

    smart, mid, fast = (_shown(tier) for tier in TIERS)
    return (
        "Experimentalist model config:\n"
        f"  smart model: {smart}\n"
        f"  mid model:   {mid}\n"
        f"  fast model:  {fast}\n"
        f"  api base:    {_sanitize_url(api_base())}\n"
        f"  api key:     {_mask_key(api_key())}"
    )
