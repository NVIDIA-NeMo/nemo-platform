# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""API dependencies for the Guardrails service."""

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from nemo_platform_plugin.client.client import AsyncNemoClient
from nmp.common.entities.client import EntityClient
from nmp.common.http_clients import shared_async_http_client
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


# Dependency for NeMo Platform
def get_nemo_platform() -> AsyncNemoClient:
    nim_endpoint_url = settings.nim_endpoint_settings.base_url
    # Remove the /v1 from the end of the URL if it exists
    # This is necessary because the NeMo Platform API SDK expects the base URL to not have the /v1 suffix unlike OpenAI SDK
    if nim_endpoint_url.endswith("/v1"):
        nim_endpoint_url = nim_endpoint_url[: -len("/v1")]
    return AsyncNemoClient(
        inference_base_url=nim_endpoint_url,
        http_client=shared_async_http_client(),
    )


RailsServiceDep = Annotated[RailsService, Depends(get_rails_service)]
NemoClientDep = Annotated[AsyncNemoClient, Depends(get_nemo_platform)]
