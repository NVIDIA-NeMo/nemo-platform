# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mocked docker client tests for DockerDeploymentBackend."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from backends.docker.docker_helpers import container_attrs, lora_config, sample_config
from docker.errors import APIError, NotFound
from nemo_deployments_plugin.backends.docker.backend import DockerDeploymentBackend
from nemo_deployments_plugin.backends.labels import (
    CONFIG_NAME_LABEL,
    CONTAINER_ROLE_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    RESTART_POLICY_LABEL,
    companion_container_name,
    container_name,
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_deployments_plugin.entities import Deployment


@pytest.mark.asyncio
async def test_create_deployment_starts_container(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config()
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    mock_docker_client.containers.run.return_value = MagicMock(id="abc123")

    update = await docker_backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "STARTING"
    mock_docker_client.containers.run.assert_called_once()
    mock_entities.get.assert_awaited()


@pytest.mark.asyncio
async def test_create_deployment_maps_command_to_entrypoint(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    """A spec's ``command`` overrides the image ENTRYPOINT; ``args`` is the CMD.

    This mirrors Kubernetes semantics and is required so a driven container
    (e.g. a packaged agent that bakes its own ``ENTRYPOINT``) runs the
    platform-supplied command instead of the image default.
    """
    mock_entities.get.return_value = sample_config()  # command=["echo"], args=["hello"]
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    mock_docker_client.containers.run.return_value = MagicMock(id="abc123")

    await docker_backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    _, run_kwargs = mock_docker_client.containers.run.call_args
    assert run_kwargs["entrypoint"] == ["echo"]
    assert run_kwargs["command"] == ["hello"]


@pytest.mark.asyncio
async def test_create_lora_group_runs_init_server_and_sidecar(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    """A LoRA-shaped config runs init-to-completion, then server, then sidecar.

    The sidecar shares the server's network namespace (network=container:<server>)
    and publishes no host ports; only the server maps ports.
    """
    mock_entities.get.return_value = lora_config()
    mock_docker_client.containers.get.side_effect = NotFound("missing")

    # Init container is run+waited: containers.run returns a container whose
    # wait() reports success.
    init_container = MagicMock()
    init_container.wait.return_value = {"StatusCode": 0}
    server_container = MagicMock(id="server123")
    sidecar_container = MagicMock(id="sidecar123")
    mock_docker_client.containers.run.side_effect = [init_container, server_container, sidecar_container]

    update = await docker_backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "STARTING"
    calls = mock_docker_client.containers.run.call_args_list
    assert len(calls) == 3

    # 1) init container ran to completion (detached then waited + removed)
    init_container.wait.assert_called_once()
    init_container.remove.assert_called_once()

    # 2) server publishes ports, no shared netns
    server_kwargs = calls[1].kwargs
    assert server_kwargs["name"] == container_name("default", "srv")
    assert server_kwargs["labels"][CONTAINER_ROLE_LABEL] == "server"
    assert "ports" in server_kwargs
    assert server_kwargs.get("network", "") == ""

    # 3) sidecar shares the server netns, publishes no ports
    sidecar_kwargs = calls[2].kwargs
    assert sidecar_kwargs["name"] == companion_container_name("default", "srv", "lora-adapters")
    assert sidecar_kwargs["labels"][CONTAINER_ROLE_LABEL] == "lora-adapters"
    assert sidecar_kwargs["network"] == f"container:{container_name('default', 'srv')}"
    assert "ports" not in sidecar_kwargs


@pytest.mark.asyncio
async def test_create_lora_group_fails_when_init_nonzero(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    """A non-zero init container fails the deployment before the server starts."""
    mock_entities.get.return_value = lora_config()
    mock_docker_client.containers.get.side_effect = NotFound("missing")

    init_container = MagicMock()
    init_container.wait.return_value = {"StatusCode": 1}
    mock_docker_client.containers.run.return_value = init_container

    update = await docker_backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "FAILED"
    assert "init" in update.status_message.lower()
    # only the init container was run (server/sidecar never started)
    assert mock_docker_client.containers.run.call_count == 1


@pytest.mark.asyncio
async def test_create_falls_back_to_local_image_when_pull_fails(
    mock_sdk: MagicMock,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    """A pull failure is tolerated when the image is already present locally.

    Local-only images (e.g. the LoRA adapters sidecar ``nmp-api:local``) are not
    pullable from a registry; the backend uses the local copy instead of failing.
    """
    from unittest.mock import patch

    with (
        patch("nemo_deployments_plugin.backends.docker.backend.AsyncEntitiesResource"),
        patch("nemo_deployments_plugin.backends.docker.backend.NemoEntitiesClient", return_value=mock_entities),
        patch("nemo_deployments_plugin.backends.docker.backend.get_shared_gpu_pool", return_value=None),
        patch("docker.from_env", return_value=mock_docker_client),
    ):
        # pull_images enabled so the pull path runs
        backend = DockerDeploymentBackend(mock_sdk, {"docker_timeout": 60, "pull_images": True})
        backend._client = mock_docker_client

    mock_entities.get.return_value = sample_config()
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    mock_docker_client.images.pull.side_effect = APIError("404 not found")
    mock_docker_client.images.get.return_value = MagicMock()  # present locally
    mock_docker_client.containers.run.return_value = MagicMock(id="abc123")

    update = await backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "STARTING"
    mock_docker_client.images.get.assert_called_once()
    mock_docker_client.containers.run.assert_called_once()


@pytest.mark.asyncio
async def test_create_fails_when_pull_fails_and_no_local_image(
    mock_sdk: MagicMock,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    """If the image cannot be pulled AND is not present locally, create fails."""
    from unittest.mock import patch

    with (
        patch("nemo_deployments_plugin.backends.docker.backend.AsyncEntitiesResource"),
        patch("nemo_deployments_plugin.backends.docker.backend.NemoEntitiesClient", return_value=mock_entities),
        patch("nemo_deployments_plugin.backends.docker.backend.get_shared_gpu_pool", return_value=None),
        patch("docker.from_env", return_value=mock_docker_client),
    ):
        backend = DockerDeploymentBackend(mock_sdk, {"docker_timeout": 60, "pull_images": True})
        backend._client = mock_docker_client

    mock_entities.get.return_value = sample_config()
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    mock_docker_client.images.pull.side_effect = APIError("404 not found")
    mock_docker_client.images.get.side_effect = NotFound("missing locally")

    update = await backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "FAILED"
    assert "pull image" in update.status_message.lower()
    mock_docker_client.containers.run.assert_not_called()


@pytest.mark.asyncio
async def test_delete_removes_whole_group(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    """delete_deployment stops+removes every container in the group."""
    server = MagicMock()
    server.name = container_name("default", "srv")
    sidecar = MagicMock()
    sidecar.name = companion_container_name("default", "srv", "lora-adapters")
    mock_docker_client.containers.list.return_value = [server, sidecar]

    update = await docker_backend.delete_deployment("default", "srv")

    assert update.status == "SUCCEEDED"
    server.remove.assert_called_once()
    sidecar.remove.assert_called_once()


@pytest.mark.asyncio
async def test_create_volume_runs_init_chmod_container(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    """initChmod/initImage in the docker volume backend_config trigger an init
    chmod container so a non-root workload (the HF weight-puller) can write the
    otherwise root-owned named volume. This is the docker analogue of k8s fsGroup.
    """
    mock_docker_client.volumes.get.side_effect = NotFound("missing")
    mock_docker_client.volumes.create.return_value = MagicMock(name="vol")

    update = await docker_backend.create_volume(
        workspace="default",
        name="weights",
        size="40Gi",
        access_modes=["ReadWriteOnce"],
        backend_config={"docker": {"initChmod": "0777", "initImage": "docker.io/library/busybox"}},
    )

    assert update.status == "BOUND"
    mock_docker_client.containers.run.assert_called_once()
    args, run_kwargs = mock_docker_client.containers.run.call_args
    assert args[0] == "docker.io/library/busybox"
    # chmod is invoked directly (no `sh -c`) so the mode is never shell-interpolated
    assert run_kwargs["entrypoint"] == ["chmod"]
    assert run_kwargs["command"] == ["0777", "/vol"]
    assert run_kwargs["remove"] is True
    # the init container must mount the volume it is fixing up
    assert any(b.get("bind") == "/vol" for b in run_kwargs["volumes"].values())


@pytest.mark.asyncio
async def test_create_volume_without_init_chmod_skips_container(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    mock_docker_client.volumes.get.side_effect = NotFound("missing")
    mock_docker_client.volumes.create.return_value = MagicMock(name="vol")

    update = await docker_backend.create_volume(
        workspace="default",
        name="weights",
        size="40Gi",
        access_modes=["ReadWriteOnce"],
        backend_config={},
    )

    assert update.status == "BOUND"
    mock_docker_client.containers.run.assert_not_called()


@pytest.mark.asyncio
async def test_create_volume_skips_init_chmod_when_volume_exists(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    """The init chmod container runs only on a fresh create, not when reusing an
    already-initialized volume — otherwise every reconcile would spin one up.
    """
    mock_docker_client.volumes.get.return_value = MagicMock(name="vol")  # already exists

    update = await docker_backend.create_volume(
        workspace="default",
        name="weights",
        size="40Gi",
        access_modes=["ReadWriteOnce"],
        backend_config={"docker": {"initChmod": "0777", "initImage": "docker.io/library/busybox"}},
    )

    assert update.status == "BOUND"
    mock_docker_client.volumes.create.assert_not_called()
    mock_docker_client.containers.run.assert_not_called()


@pytest.mark.asyncio
async def test_read_status_ready_when_running_without_probe(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    container = MagicMock()
    container.id = "abc123def456"
    container.status = "running"
    container.labels = {
        "managed-by": MANAGED_BY_LABEL,
        RESTART_POLICY_LABEL: "Always",
        CONFIG_NAME_LABEL: "cfg1",
    }
    container.ports = {}
    container.attrs = container_attrs()
    mock_docker_client.containers.get.return_value = container
    mock_entities.get.return_value = sample_config()

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "READY"


@pytest.mark.asyncio
async def test_read_status_lost_when_missing_always(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_docker_client.containers.get.side_effect = NotFound("missing")

    deployment_entity = MagicMock()
    deployment_entity.deployment_config = "cfg1"

    async def get_side_effect(entity_type, name, workspace=None):
        if entity_type is Deployment:
            return deployment_entity
        return sample_config(restart_policy="Always")

    mock_entities.get.side_effect = get_side_effect

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "LOST"


@pytest.mark.asyncio
async def test_read_status_unknown_on_transient_docker_error(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    mock_docker_client.containers.get.side_effect = APIError("connection reset")

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "UNKNOWN"
    assert "Docker API error" in update.status_message


@pytest.mark.asyncio
async def test_delete_deployment_idempotent(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    mock_docker_client.containers.get.side_effect = NotFound("missing")

    update = await docker_backend.delete_deployment("default", "srv")

    assert update.status == "SUCCEEDED"


@pytest.mark.asyncio
async def test_list_managed_deployment_names(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    container = MagicMock()
    container.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
    }
    mock_docker_client.containers.list.return_value = [container]

    names = await docker_backend.list_managed_deployment_names()

    assert names == ["default/srv"]


@pytest.mark.asyncio
async def test_create_volume_bound(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    volume = MagicMock()
    volume.name = "dep-vol-default-data"
    mock_docker_client.volumes.get.side_effect = NotFound("missing")
    mock_docker_client.volumes.create.return_value = volume

    update = await docker_backend.create_volume(
        workspace="default",
        name="data",
        size="1Gi",
        access_modes=["ReadWriteOnce"],
        backend_config={},
    )

    assert update.status == "BOUND"
