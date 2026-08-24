# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI dependencies for the Jobs API."""

from fastapi import Depends, Request
from nemo_platform_plugin.client.client import AsyncNemoClient
from nmp.common.entities.client import EntityClient
from nmp.common.sdk_factory import get_async_platform_sdk
from nmp.common.service.dependencies import get_entity_client
from nmp.core.jobs.app.dispatcher import JobDispatcher


async def get_sdk_with_auth(request: Request) -> AsyncNemoClient:
    """Get SDK client with current request's auth headers.

    This dependency creates a new SDK instance with the current user's
    auth context propagated. This is needed for internal service calls
    that require authorization (e.g., creating filesets).

    Args:
        request: The FastAPI request object (needed to ensure we're in request context)
    """
    # By taking request as parameter, we ensure this runs in request context
    # where auth headers are available via context vars
    return get_async_platform_sdk()


async def dep_dispatcher(
    entity_client: EntityClient = Depends(get_entity_client),
    sdk: AsyncNemoClient = Depends(get_sdk_with_auth),
) -> JobDispatcher:
    """Dependency to get the job dispatcher with EntityClient and SDK client."""
    return JobDispatcher(
        store=entity_client,
        sdk=sdk,
    )
