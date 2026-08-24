# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Hello API endpoints."""

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from nmp.common.config import PlatformConfig
from nmp.common.service.dependencies import get_platform_config, get_sdk_client, get_service_config_factory
from nmp.hello_world.api.v1.hello.schemas import ConfigInfoResponse, HelloResponse
from nmp.hello_world.config import HelloWorldConfig

if TYPE_CHECKING:
    from nemo_platform_plugin.client.client import AsyncNemoClient

router = APIRouter()

API_TAG = "Hello"


@router.get(
    "/hello",
    response_model=HelloResponse,
    tags=[API_TAG],
)
async def hello(
    workspace: str,
    sdk: "AsyncNemoClient" = Depends(get_sdk_client),
) -> HelloResponse:
    """Return a hello world message with workspace info from the SDK."""
    workspace_info = await sdk.workspaces.get_workspace(workspace)
    return HelloResponse(message=f"Hello World from workspace '{workspace_info.name}'")


@router.get(
    "/config-info",
    response_model=ConfigInfoResponse,
    tags=[API_TAG],
)
async def config_info(
    platform_config: PlatformConfig = Depends(get_platform_config),
    service_config: HelloWorldConfig = Depends(get_service_config_factory(HelloWorldConfig)),
) -> ConfigInfoResponse:
    """Return configuration info demonstrating config dependency injection.

    This endpoint shows how to inject both platform-wide and service-specific
    configuration using FastAPI's dependency injection.
    """
    return ConfigInfoResponse(
        platform_base_url=platform_config.base_url,
        greeting_prefix=service_config.greeting_prefix,
        max_message_length=service_config.max_message_length,
    )
