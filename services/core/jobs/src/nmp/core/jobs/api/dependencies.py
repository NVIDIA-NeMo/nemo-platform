# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI dependencies for the Jobs API."""

from fastapi import Depends
from nemo_platform import AsyncNeMoPlatform
from nmp.common.entities.client import EntityClient
from nmp.common.service.dependencies import get_entity_client, get_sdk_client
from nmp.core.jobs.app.dispatcher import JobDispatcher


async def get_sdk_with_auth(
    sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
) -> AsyncNeMoPlatform:
    """Get SDK client with current request's auth headers.

    The platform overrides get_sdk_client with a request-scoped SDK that
    preserves the service provider's HTTP transport.
    """
    return sdk


async def dep_dispatcher(
    entity_client: EntityClient = Depends(get_entity_client),
    sdk: AsyncNeMoPlatform = Depends(get_sdk_with_auth),
) -> JobDispatcher:
    """Dependency to get the job dispatcher with EntityClient and SDK client."""
    return JobDispatcher(
        store=entity_client,
        sdk=sdk,
    )
