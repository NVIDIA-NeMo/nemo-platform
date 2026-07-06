# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Common FastAPI dependency placeholders for NeMo Platform services.

These are stub functions that raise RuntimeError if called directly.
The platform injects real implementations via app.dependency_overrides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nemo_platform import AsyncNeMoPlatform
    from nemo_platform_plugin.config import PlatformConfig
    from nemo_platform_plugin.entities import EntityClient, NemoEntityClient


def get_platform_config() -> "PlatformConfig":
    """FastAPI dependency for getting the platform config.

    This is a placeholder — the actual config is injected via
    app.dependency_overrides in Service.create_app().
    """
    raise RuntimeError(
        "get_platform_config() was called without being overridden. "
        "Ensure your Service subclass calls super().create_app()."
    )


def get_service_config() -> Any:
    """FastAPI dependency for getting the service-specific config.

    DEPRECATED: Use get_service_config_factory(ConfigClass) instead.
    """
    raise RuntimeError(
        "get_service_config() was called without being overridden. "
        "Ensure your Service subclass specifies a config type via Service[YourConfig]."
    )


def get_sdk_client() -> "AsyncNeMoPlatform":
    """FastAPI dependency for getting the async platform SDK client.

    This is a placeholder — the actual client is injected via
    app.dependency_overrides in Service.create_app().
    """
    raise RuntimeError(
        "get_sdk_client() was called without being overridden. Ensure your Service subclass calls super().create_app()."
    )


def get_entity_client() -> "EntityClient":
    """FastAPI dependency for getting the EntityClient.

    This is a placeholder — the actual client is injected via
    app.dependency_overrides in Service.create_app().
    """
    raise RuntimeError(
        "get_entity_client() was called without being overridden. "
        "Ensure your Service subclass calls super().create_app() or "
        "configure entity_client in the service."
    )


def get_nemo_entity_client() -> "NemoEntityClient":
    """Return a NemoClient-backed :class:`NemoEntityClient`.

    Unlike the sibling placeholders (``get_sdk_client``, ``get_entity_client``,
    ``get_platform_config``), this has a real default implementation because
    everything it needs lives in ``nemo_platform_plugin``: the client transport,
    the env-based context/header builder (``client_provider``), and the entity
    client itself — no ``nmp-core`` bits required.

    The default builds an env-scoped client (``NMP_BASE_URL`` / ``NMP_PRINCIPAL``
    via ``client_provider.get_async_nemo_client``), which is the correct context
    for task containers, background jobs, and controllers. For request handling,
    ``Service`` still overrides this via ``app.dependency_overrides`` with a
    request-scoped client (service-principal + on-behalf-of headers).
    """
    from nemo_platform_plugin.client_provider import get_async_nemo_client
    from nemo_platform_plugin.entities import NemoEntityClient

    return NemoEntityClient(get_async_nemo_client())
