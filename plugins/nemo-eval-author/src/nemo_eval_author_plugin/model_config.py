# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLM clients for Eval Author.

This module deliberately imports nothing from Experimentalist. Eval Author is meant to
become a standalone plugin, so its credential handling duplicates Experimentalist's rather
than sharing it. See the plugin README for the wider split, and
``tests/test_plugin_boundary.py`` for the check that holds this module independent.

``AUTHOR_*`` is the real contract. The ``EXPERIMENTALIST_*`` fallback and
:func:`bridge_author_env_to_experimentalist` are both transitional, and exist only while
Eval Author still reuses Experimentalist agents.

TODO(eval-author-standalone): drop the ``EXPERIMENTALIST_*`` fallback and the bridge once
this plugin imports nothing from ``nemo_experimentalist_plugin``. Concretely: delete
``_BRIDGED_ENV_PAIRS`` and :func:`bridge_author_env_to_experimentalist`, delete
``_env_bridge.py`` and its import in ``eval_author/agent.py``, and narrow every ``_env`` /
``_env_or_default`` call here to its ``AUTHOR_*`` name. That is a breaking change for
anyone running insight mode from an Experimentalist-only profile ``.env``, so it needs a
release note. ``rg 'eval-author-standalone'`` finds the other sites.
"""

import functools
import logging
import os
from urllib.parse import urlsplit

from nooa.unifiedllm import CompletionClient

logger = logging.getLogger(__name__)

# Duplicated from `nemo_experimentalist_plugin.cli` on purpose: sharing it would mean
# importing Experimentalist from a module that is otherwise already standalone.
_GATEWAY_HOST = "inference-api.nvidia.com"

_SMART_MODEL_DEFAULT = "openai/openai/openai/gpt-5.5"
_FAST_MODEL_DEFAULT = "openai/openai/openai/gpt-5-mini"

# Transitional; see TODO(eval-author-standalone) above. Every pair targets an Experimentalist
# helper rather than a client Eval Author owns, which is why the mid tier appears here
# despite Eval Author having no mid-tier client of its own.
_BRIDGED_ENV_PAIRS = (
    ("AUTHOR_API_BASE", "EXPERIMENTALIST_API_BASE"),
    ("AUTHOR_API_KEY", "EXPERIMENTALIST_API_KEY"),
    ("AUTHOR_SMART_MODEL_NAME", "EXPERIMENTALIST_SMART_MODEL_NAME"),
    ("AUTHOR_MID_MODEL_NAME", "EXPERIMENTALIST_MID_MODEL_NAME"),
    ("AUTHOR_FAST_MODEL_NAME", "EXPERIMENTALIST_FAST_MODEL_NAME"),
)


def _env(*names: str) -> str | None:
    """Return the first non-empty value among ``names``, or ``None`` when all are empty."""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _env_or_default(*names: str, default: str) -> str:
    """Return the first non-empty value among ``names``, falling back to ``default``."""
    return _env(*names) or default


def _api_base() -> str:
    base = _env("AUTHOR_API_BASE", "EXPERIMENTALIST_API_BASE")
    if not base:
        raise ValueError("AUTHOR_API_BASE (or EXPERIMENTALIST_API_BASE) must be set")
    return base


def _is_gateway_base(value: str) -> bool:
    """Report whether ``value`` is the NVIDIA Inference Gateway reached over HTTPS.

    Mirrors ``nemo_experimentalist_plugin.cli._is_gateway_base``. The scheme check is not
    cosmetic: a host-only match would forward ``INFERENCE_API_KEY`` to a plain-HTTP base.
    """
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname == _GATEWAY_HOST


def _api_key() -> str:
    """Resolve the LLM API key for Eval Author.

    Preference order:
    1. ``AUTHOR_API_KEY``
    2. ``EXPERIMENTALIST_API_KEY``
    3. ``INFERENCE_API_KEY``, but only when the resolved base is the HTTPS NVIDIA
       Inference Gateway, matching how the Experimentalist CLI forwards that key.

    Returns:
        str: the resolved API key.

    Raises:
        ValueError: if no key is available for the resolved base.

    """
    key = _env("AUTHOR_API_KEY", "EXPERIMENTALIST_API_KEY")
    if key:
        return key
    if _is_gateway_base(_api_base()):
        inference = _env("INFERENCE_API_KEY")
        if inference:
            return inference
    raise ValueError(
        "AUTHOR_API_KEY (or EXPERIMENTALIST_API_KEY) must be set; "
        "when using the NVIDIA Inference Gateway, INFERENCE_API_KEY is also accepted"
    )


@functools.cache
def _completion_client(name: str, api_base: str, api_key: str) -> CompletionClient:
    """Return Eval Author's client for an already-resolved model triple.

    Cached on the triple rather than per tier so that two tiers pointing at the same model
    share a connection pool. Experimentalist caches its own clients separately; that
    duplication is the price of Eval Author not importing from it.

    Args:
        name: Fully qualified model name, as ``CompletionClient`` expects it.
        api_base: Resolved API base URL.
        api_key: Resolved API key.

    Returns:
        CompletionClient: the client for this triple.

    """
    return CompletionClient(name, api_base=api_base, api_key=api_key)


@functools.cache
def get_smart_model() -> CompletionClient:
    """Return the cached smart (high-capability) LLM client configured from environment variables.

    Returns:
        CompletionClient: the singleton smart-model client.

    Raises:
        ValueError: if Eval Author API credentials are unset or empty.

    """
    name = _env_or_default(
        "AUTHOR_SMART_MODEL_NAME",
        "EXPERIMENTALIST_SMART_MODEL_NAME",
        default=_SMART_MODEL_DEFAULT,
    )
    return _completion_client(name, _api_base(), _api_key())


@functools.cache
def get_fast_model() -> CompletionClient:
    """Return the cached fast (low-latency) LLM client configured from environment variables.

    Returns:
        CompletionClient: the singleton fast-model client.

    Raises:
        ValueError: if Eval Author API credentials are unset or empty.

    """
    name = _env_or_default(
        "AUTHOR_FAST_MODEL_NAME",
        "EXPERIMENTALIST_FAST_MODEL_NAME",
        default=_FAST_MODEL_DEFAULT,
    )
    return _completion_client(name, _api_base(), _api_key())


def bridge_author_env_to_experimentalist() -> list[str]:
    """Copy ``AUTHOR_*`` into unset ``EXPERIMENTALIST_*`` slots.

    Eval Author owns ``AUTHOR_*`` for its own clients, but the Experimentalist helpers it
    reuses (``TraceAnalyzer`` and the summarizers it pulls in) bind their LLM in the class
    body from ``EXPERIMENTALIST_*``. Bridging lets a standalone ``AUTHOR_*``-only run
    supply those helpers without the caller duplicating credentials. Values already present
    in ``EXPERIMENTALIST_*`` always win, so insight-mode runs are left alone.

    Returns:
        list[str]: the ``EXPERIMENTALIST_*`` names this call populated, in declaration
            order. Empty once everything is in place, which makes repeat calls no-ops.

    """
    applied: list[str] = []
    for src, dst in _BRIDGED_ENV_PAIRS:
        value = os.environ.get(src, "").strip()
        if value and not os.environ.get(dst, "").strip():
            os.environ[dst] = value
            applied.append(dst)
    if applied:
        logger.info("Bridged Eval Author credentials into %s", ", ".join(applied))
    return applied
