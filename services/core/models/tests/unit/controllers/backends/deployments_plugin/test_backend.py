# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from nemo_deployments_plugin.entities import Deployment, DeploymentConfig, Volume
from nemo_deployments_plugin.types import Endpoint
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError
from nmp.common.config import Runtime
from nmp.core.models.app import ModelWeightsType
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.common import DeploymentConfigView
from nmp.core.models.controllers.backends.deployments_plugin.backend import DeploymentsPluginServiceBackend
from nmp.core.models.controllers.backends.deployments_plugin.config import DeploymentsPluginConfig
from nmp.core.models.controllers.backends.deployments_plugin.resolve import ResolvedPluginDeployment


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(
        model_deployment=SimpleNamespace(name="my-dep", workspace="default", status="CREATED"),
        model_deployment_config=SimpleNamespace(engine="vllm"),
        model_entity=None,
    )


def _resolved() -> ResolvedPluginDeployment:
    return ResolvedPluginDeployment(
        deployment=SimpleNamespace(name="my-dep", workspace="default"),
        config=SimpleNamespace(engine="vllm"),
        model_entity=None,
        view=DeploymentConfigView(model_namespace="org", model_name="model"),
        weights_type=ModelWeightsType.FILES_SERVICE,
        model_namespace="org",
        model_name="model",
        model_revision=None,
        files_hf_url="http://files/hf",
        huggingface_model_puller="puller:latest",
        runtime=Runtime.KUBERNETES,
    )


@pytest.mark.asyncio
async def test_get_status_projects_ready_endpoint() -> None:
    backend = DeploymentsPluginServiceBackend(AsyncMock(), {}, "puller:latest")
    backend.init()
    backend._entities = AsyncMock()
    backend._entities.get = AsyncMock(
        side_effect=[
            Deployment(
                name="my-dep-server",
                workspace="default",
                deployment_config="my-dep-server",
                status="READY",
                endpoints=[Endpoint(name="http", url="http://server", protocol="http")],
            ),
            NemoEntityNotFoundError("missing"),
            NemoEntityNotFoundError("missing"),
        ]
    )
    result = await backend.get_model_deployment_status(
        SimpleNamespace(
            model_deployment=SimpleNamespace(
                name="my-dep",
                workspace="default",
                status="PENDING",
                created_at=datetime.now(timezone.utc),
            )
        )
    )
    assert result.status == "READY"
    assert result.host_url == "http://server"


@pytest.mark.asyncio
async def test_missing_ready_server_is_lost() -> None:
    backend = DeploymentsPluginServiceBackend(AsyncMock(), {}, "puller:latest")
    backend.init()
    backend._entities = AsyncMock()
    backend._entities.get = AsyncMock(side_effect=NemoEntityNotFoundError("missing"))
    result = await backend.get_model_deployment_status(
        SimpleNamespace(
            model_deployment=SimpleNamespace(
                name="my-dep",
                workspace="default",
                status="READY",
                created_at=datetime.now(timezone.utc),
            )
        )
    )
    assert result.status == "LOST"


@pytest.mark.asyncio
async def test_create_order_volume_puller_server_with_prerequisite() -> None:
    backend = DeploymentsPluginServiceBackend(AsyncMock(), {}, "puller:latest")
    backend.init()
    backend._entities = AsyncMock()
    created: list[object] = []

    async def _create(entity: object) -> object:
        created.append(entity)
        return entity

    backend._entities.create = AsyncMock(side_effect=_create)
    backend._entities.get = AsyncMock(side_effect=NemoEntityNotFoundError("missing"))
    backend._entities.delete = AsyncMock(side_effect=NemoEntityNotFoundError("missing"))
    with (
        patch(
            "nmp.core.models.controllers.backends.deployments_plugin.backend.resolve_plugin_deployment",
            return_value=_resolved(),
        ),
        patch(
            "nmp.core.models.controllers.backends.deployments_plugin.backend.executor_for_runtime",
            return_value="local-k8s",
        ),
    ):
        result = await backend.create_model_deployment(_ctx())

    assert result.status == "PENDING"
    assert [type(item) for item in created] == [Volume, DeploymentConfig, Deployment, DeploymentConfig, Deployment]
    puller_dep = created[2]
    server_dep = created[4]
    assert isinstance(puller_dep, Deployment) and puller_dep.name == "my-dep-puller"
    assert isinstance(server_dep, Deployment) and server_dep.name == "my-dep-server"
    assert server_dep.prerequisites[0].deployment_name == "my-dep-puller"
    assert server_dep.prerequisites[0].condition == "succeeded"


def _resolved_docker_lora() -> ResolvedPluginDeployment:
    return ResolvedPluginDeployment(
        deployment=SimpleNamespace(name="my-dep", workspace="default"),
        config=SimpleNamespace(engine="vllm"),
        model_entity=None,
        view=DeploymentConfigView(model_namespace="org", model_name="model", lora_enabled=True),
        weights_type=ModelWeightsType.FILES_SERVICE,
        model_namespace="org",
        model_name="model",
        model_revision=None,
        files_hf_url="http://files/hf",
        huggingface_model_puller="puller:latest",
        runtime=Runtime.DOCKER,
    )


@pytest.mark.asyncio
async def test_docker_lora_fails_fast_before_touching_substrate() -> None:
    backend = DeploymentsPluginServiceBackend(AsyncMock(), {}, "puller:latest")
    backend.init()
    backend._entities = AsyncMock()
    with (
        patch(
            "nmp.core.models.controllers.backends.deployments_plugin.backend.resolve_plugin_deployment",
            return_value=_resolved_docker_lora(),
        ),
        patch.object(backend, "delete_model_deployment", AsyncMock()) as delete_mock,
    ):
        result = await backend.create_model_deployment(_ctx())
    assert result.status == "ERROR"
    assert "docker" in result.status_message.lower()
    assert "lora" in result.status_message.lower()
    delete_mock.assert_not_called()
    backend._entities.create.assert_not_called()


@pytest.mark.asyncio
async def test_create_waits_when_prior_teardown_incomplete() -> None:
    backend = DeploymentsPluginServiceBackend(AsyncMock(), {}, "puller:latest")
    backend.init()
    backend._entities = AsyncMock()
    with (
        patch(
            "nmp.core.models.controllers.backends.deployments_plugin.backend.resolve_plugin_deployment",
            return_value=_resolved(),
        ),
        patch.object(
            backend,
            "delete_model_deployment",
            AsyncMock(return_value=DeploymentStatusUpdate(status="DELETING", status_message="waiting")),
        ),
    ):
        result = await backend.create_model_deployment(_ctx())
    assert result.status == "PENDING"
    assert "teardown" in result.status_message.lower()
    backend._entities.create.assert_not_called()


@pytest.mark.asyncio
async def test_missing_executor_fails_fast_before_touching_substrate() -> None:
    backend = DeploymentsPluginServiceBackend(AsyncMock(), {}, "puller:latest")
    backend.init()
    backend._entities = AsyncMock()
    backend._entities.get = AsyncMock(side_effect=NemoEntityNotFoundError("missing"))
    backend._entities.delete = AsyncMock(side_effect=NemoEntityNotFoundError("missing"))
    with (
        patch(
            "nmp.core.models.controllers.backends.deployments_plugin.backend.resolve_plugin_deployment",
            return_value=_resolved(),
        ),
        patch(
            "nmp.core.models.controllers.backends.deployments_plugin.backend.executor_for_runtime",
            return_value=None,
        ),
    ):
        result = await backend.create_model_deployment(_ctx())
    assert result.status == "ERROR"
    assert "executor" in result.status_message.lower()
    assert result.error_details is not None
    assert result.error_details["reason"] == "executor_not_configured"
    backend._entities.create.assert_not_called()


@pytest.mark.asyncio
async def test_pending_timeout_escalates_stuck_deployment() -> None:
    backend = DeploymentsPluginServiceBackend(AsyncMock(), {}, "puller:latest")
    backend.init()
    backend._backend_config = DeploymentsPluginConfig(pending_timeout_seconds=60)
    backend._entities = AsyncMock()
    server = Deployment(
        name="my-dep-server",
        workspace="default",
        deployment_config="my-dep-server",
        status="STARTING",
    )
    backend._entities.get = AsyncMock(
        side_effect=[
            server,
            NemoEntityNotFoundError("missing"),
            NemoEntityNotFoundError("missing"),
        ]
    )
    created_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    result = await backend.get_model_deployment_status(
        SimpleNamespace(
            model_deployment=SimpleNamespace(
                name="my-dep",
                workspace="default",
                status="PENDING",
                created_at=created_at,
            )
        )
    )
    assert result.status == "ERROR"
    assert result.error_details is not None
    assert result.error_details["reason"] == "pending_timeout"
    assert result.error_details["timeout_seconds"] == 60


@pytest.mark.asyncio
async def test_delete_waits_for_server_before_config() -> None:
    backend = DeploymentsPluginServiceBackend(AsyncMock(), {}, "puller:latest")
    backend._backend_config = DeploymentsPluginConfig(delete_wait_seconds=0.02, delete_poll_seconds=0.005)
    backend._entities = AsyncMock()
    server = Deployment(
        name="my-dep-server",
        workspace="default",
        deployment_config="my-dep-server",
        status="READY",
    )

    async def _get(entity_type: type, name: str, workspace: str | None = None) -> Deployment:
        del entity_type, name, workspace
        return server

    backend._entities.get = AsyncMock(side_effect=_get)
    backend._entities.update = AsyncMock(side_effect=lambda entity: entity)
    backend._entities.delete = AsyncMock()

    result = await backend.delete_model_deployment("default", "my-dep")
    assert result.status == "DELETING"
    backend._entities.delete.assert_not_called()
