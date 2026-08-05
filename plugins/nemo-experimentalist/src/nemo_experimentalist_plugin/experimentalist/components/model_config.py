# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import functools
from collections.abc import Callable
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

    def _or_unset(resolve: Callable[[], str]) -> str | None:
        """Return the resolved value, or None when it is configured nowhere.

        Every field is optional here on purpose: this banner is most useful on exactly
        the misconfigured install that cannot resolve one, so it must never be the thing
        that raises. The callers that actually need a value still go through
        ``api_base()`` / ``api_key()`` / ``model_name()`` and fail there.
        """
        try:
            return resolve()
        except ValueError:
            return None

    smart, mid, fast = (_or_unset(lambda t=tier: model_name(t)) or "(unset)" for tier in TIERS)
    base = _or_unset(api_base)
    key = _or_unset(api_key)
    return (
        "Experimentalist model config:\n"
        f"  smart model: {smart}\n"
        f"  mid model:   {mid}\n"
        f"  fast model:  {fast}\n"
        f"  api base:    {_sanitize_url(base) if base else '(unset)'}\n"
        f"  api key:     {_mask_key(key) if key else '(unset)'}"
    )
