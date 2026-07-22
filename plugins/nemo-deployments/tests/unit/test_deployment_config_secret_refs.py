# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public DeploymentConfig API policy tests for secret references."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from nemo_deployments_plugin.api.v2.deployment_configs import (
    _contains_secret_ref,
    create_deployment_config,
)
from nemo_deployments_plugin.entities import Container, EnvVar, SecretRef
from nemo_deployments_plugin.schema import CreateDeploymentConfigRequest


def _request(env: EnvVar) -> CreateDeploymentConfigRequest:
    return CreateDeploymentConfigRequest(
        name="config",
        containers=[Container(name="server", image="example:latest", env=[env])],
    )


def test_secret_ref_detection_ignores_plain_values() -> None:
    assert not _contains_secret_ref(_request(EnvVar(name="PLAIN", value="value")))
    assert _contains_secret_ref(
        _request(
            EnvVar(
                name="NGC_API_KEY",
                secretRef=SecretRef(workspace="system", name="ngc-api-key"),
            )
        )
    )


@pytest.mark.asyncio
async def test_public_create_rejects_controller_managed_secret_ref() -> None:
    body = _request(
        EnvVar(
            name="NGC_API_KEY",
            secretRef=SecretRef(workspace="system", name="ngc-api-key"),
        )
    )
    entity_client = AsyncMock()

    with pytest.raises(HTTPException, match="controller-managed"):
        await create_deployment_config(
            workspace="default",
            body=body,
            entity_client=entity_client,
        )

    entity_client.create.assert_not_awaited()
