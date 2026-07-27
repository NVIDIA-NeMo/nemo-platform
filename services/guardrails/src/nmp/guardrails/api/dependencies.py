# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""API dependencies for the Guardrails service."""

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from nemo_platform import AsyncNeMoPlatform
from nmp.common.entities.client import EntityClient
from nmp.common.service.dependencies import get_entity_client
from nmp.guardrails.app.services.configs.registry import ConfigRegistry
from nmp.guardrails.app.services.rails.registry import RailsRegistry
from nmp.guardrails.app.services.rails.service import RailsService
from nmp.guardrails.config import settings

logger = logging.getLogger(__name__)


def get_config_registry(
    entities_client: EntityClient = Depends(get_entity_client),
) -> ConfigRegistry:
    """Get the ConfigRegistry instance."""
    return ConfigRegistry(entities_client=entities_client)


ConfigRegistryDep = Annotated[ConfigRegistry, Depends(get_config_registry)]


# Dependency for RailsRegistry
@lru_cache()
def get_rails_registry() -> RailsRegistry:
    return RailsRegistry()


RailsRegistryDep = Annotated[RailsRegistry, Depends(get_rails_registry)]


# Dependency for RailsService
def get_rails_service(
    config_registry: ConfigRegistryDep,
    rails_registry: RailsRegistryDep,
) -> RailsService:
    return RailsService(config_registry=config_registry, rails_registry=rails_registry)


def _guardrails_inference_base_url() -> str:
    nim_endpoint_url = settings.nim_endpoint_settings.base_url
    # Remove the /v1 from the end of the URL if it exists.
    # The platform SDK base URL does not include the OpenAI-compatible suffix.
    if nim_endpoint_url.endswith("/v1"):
        return nim_endpoint_url[: -len("/v1")]
    return nim_endpoint_url


class _NeMoPlatformClientProvider:
    def __init__(self) -> None:
        self._sdk: AsyncNeMoPlatform | None = None

    def get(self) -> AsyncNeMoPlatform:
        if self._sdk is None:
            self._sdk = AsyncNeMoPlatform(inference_base_url=_guardrails_inference_base_url())
        return self._sdk

    async def aclose(self) -> None:
        sdk = self._sdk
        self._sdk = None
        if sdk is not None:
            await sdk.close()


_nemo_platform_client_provider = _NeMoPlatformClientProvider()


# Dependency for NeMo Platform
def get_nemo_platform() -> AsyncNeMoPlatform:
    return _nemo_platform_client_provider.get()


async def close_nemo_platform() -> None:
    await _nemo_platform_client_provider.aclose()


RailsServiceDep = Annotated[RailsService, Depends(get_rails_service)]
NeMoPlatformDep = Annotated[AsyncNeMoPlatform, Depends(get_nemo_platform)]
