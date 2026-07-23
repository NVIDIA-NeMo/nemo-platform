# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public DeploymentConfig API policy tests for secret references."""

from unittest.mock import AsyncMock

import pytest
from nemo_deployments_plugin.api.v2.deployment_configs import create_deployment_config
from nemo_deployments_plugin.entities import DeploymentConfig
from nemo_deployments_plugin.schema import CreateDeploymentConfigRequest, RequestContainer, RequestEnvVar
from pydantic import ValidationError


def test_request_env_var_rejects_secret_ref() -> None:
    with pytest.raises(ValidationError, match="secretRef"):
        RequestEnvVar.model_validate(
            {
                "name": "NGC_API_KEY",
                "secretRef": {"workspace": "system", "name": "ngc-api-key"},
            }
        )


def test_create_request_accepts_plain_env_values() -> None:
    body = CreateDeploymentConfigRequest(
        name="config",
        containers=[
            RequestContainer(
                name="server",
                image="example:latest",
                env=[RequestEnvVar(name="PLAIN", value="value")],
            )
        ],
    )
    assert body.containers[0].env[0].value == "value"


@pytest.mark.asyncio
async def test_public_create_persists_plain_env_without_secret_ref() -> None:
    body = CreateDeploymentConfigRequest(
        name="config",
        containers=[
            RequestContainer(
                name="server",
                image="example:latest",
                env=[RequestEnvVar(name="PLAIN", value="value")],
            )
        ],
    )
    created = DeploymentConfig(name="config", workspace="default", containers=[])
    entity_client = AsyncMock()
    entity_client.create.return_value = created

    result = await create_deployment_config(
        workspace="default",
        body=body,
        entity_client=entity_client,
    )

    assert result is created
    persisted = entity_client.create.await_args.args[0]
    assert persisted.containers[0].env[0].value == "value"
    assert persisted.containers[0].env[0].secret_ref is None
