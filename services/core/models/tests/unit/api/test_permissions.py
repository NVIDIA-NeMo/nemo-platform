# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock

import pytest
from nmp.core.models.api.permissions import (
    check_deployment_access,
    check_deployment_config_access,
    check_model_entity_access,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("check", "reference", "read_permission", "export_permission"),
    [
        (check_model_entity_access, "source/model-a", "models.read", "models.export"),
        (
            check_deployment_access,
            "source/deployment-a",
            "inference.deployments.read",
            "inference.deployments.export",
        ),
        (
            check_deployment_config_access,
            "source/config-a",
            "inference.deployment-configs.read",
            "inference.deployment-configs.export",
        ),
    ],
)
async def test_cross_workspace_reference_requires_read_and_export(
    check,
    reference: str,
    read_permission: str,
    export_permission: str,
) -> None:
    auth_client = AsyncMock()
    auth_client.has_permissions.return_value = True

    await check(auth_client, reference, "destination")

    auth_client.has_permissions.assert_awaited_once_with("source", [read_permission, export_permission])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("check", "reference", "read_permission"),
    [
        (check_model_entity_access, "model-a", "models.read"),
        (check_deployment_access, "deployment-a", "inference.deployments.read"),
        (check_deployment_config_access, "config-a", "inference.deployment-configs.read"),
    ],
)
async def test_same_workspace_reference_requires_only_read(check, reference: str, read_permission: str) -> None:
    auth_client = AsyncMock()
    auth_client.has_permissions.return_value = True

    await check(auth_client, reference, "destination")

    auth_client.has_permissions.assert_awaited_once_with("destination", [read_permission])
