# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mocked docker client tests for DockerDeploymentBackend."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backends.docker.docker_helpers import (
    container_attrs,
    lora_config,
    published_port_config,
    sample_config,
)
from docker.errors import APIError, NotFound
from nemo_deployments_plugin.backends.base import BackendStatusUpdate
from nemo_deployments_plugin.backends.docker import ports as ports_mod
from nemo_deployments_plugin.backends.docker.backend import (
    _PORT_CONFLICT_ATTEMPTS,
    _PORT_CONFLICT_MARKER,
    DockerDeploymentBackend,
)
from nemo_deployments_plugin.backends.labels import (
    BACKOFF_LIMIT_LABEL,
    CONFIG_NAME_LABEL,
    CONTAINER_ROLE_LABEL,
    DEFAULT_RESOURCE_SCOPE,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    MANAGED_BY_KEY,
    RESOURCE_SCOPE_LABEL,
    RESTART_POLICY_LABEL,
    companion_container_name,
    container_name,
    deployment_key,
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_deployments_plugin.entities import Deployment
from nemo_deployments_plugin.types import RestartPolicy
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout


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


def _port_conflict_error(port: int) -> APIError:
    return APIError(
        f"driver failed programming external connectivity: Bind for 0.0.0.0:{port} failed: {_PORT_CONFLICT_MARKER}"
    )


@pytest.fixture
def free_host_ports(monkeypatch: pytest.MonkeyPatch, mock_docker_client: MagicMock) -> None:
    """Make host port allocation deterministic: nothing published, every probe free."""
    mock_docker_client.containers.list.return_value = []
    monkeypatch.setattr(ports_mod, "is_port_free", lambda port: True)


def _published_host_ports(run_mock: MagicMock) -> list[int]:
    return [kwargs["ports"]["8000/tcp"] for _, kwargs in run_mock.call_args_list]


@pytest.mark.asyncio
async def test_create_deployment_reallocates_port_after_docker_conflict(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
    free_host_ports: None,
) -> None:
    """Docker's port reservations are invisible to the probe, so a publish can still lose a race."""
    first_port = docker_backend._executor_config.port_range_start
    leftover = MagicMock()
    mock_entities.get.return_value = published_port_config()
    mock_docker_client.containers.get.side_effect = [NotFound("missing"), leftover]
    mock_docker_client.containers.run.side_effect = [
        _port_conflict_error(first_port),
        MagicMock(id="abc123"),
    ]

    update = await docker_backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "STARTING"
    assert _published_host_ports(mock_docker_client.containers.run) == [first_port, first_port + 1]
    # run() creates then starts, so the container that failed to start still holds the name.
    leftover.remove.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_create_deployment_fails_after_repeated_port_conflicts(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
    free_host_ports: None,
) -> None:
    first_port = docker_backend._executor_config.port_range_start
    mock_entities.get.return_value = published_port_config()
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    mock_docker_client.containers.run.side_effect = [
        _port_conflict_error(first_port + offset) for offset in range(_PORT_CONFLICT_ATTEMPTS)
    ]

    update = await docker_backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "FAILED"
    assert _PORT_CONFLICT_MARKER in (update.status_message or "")
    published = _published_host_ports(mock_docker_client.containers.run)
    assert published == [first_port + offset for offset in range(_PORT_CONFLICT_ATTEMPTS)]


@pytest.mark.asyncio
async def test_create_deployment_does_not_retry_unrelated_start_failure(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
    free_host_ports: None,
) -> None:
    mock_entities.get.return_value = published_port_config()
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    mock_docker_client.containers.run.side_effect = APIError("no such image")

    update = await docker_backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "FAILED"
    mock_docker_client.containers.run.assert_called_once()


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
        patch("nemo_deployments_plugin.backends.docker.backend.client_from_platform"),
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
        patch("nemo_deployments_plugin.backends.docker.backend.client_from_platform"),
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
    server.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESOURCE_SCOPE_LABEL: DEFAULT_RESOURCE_SCOPE,
    }
    sidecar = MagicMock()
    sidecar.name = companion_container_name("default", "srv", "lora-adapters")
    sidecar.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESOURCE_SCOPE_LABEL: DEFAULT_RESOURCE_SCOPE,
    }
    mock_docker_client.containers.list.return_value = [server, sidecar]

    update = await docker_backend.delete_deployment("default", "srv")

    assert update.status == "SUCCEEDED"
    server.remove.assert_called_once()
    sidecar.remove.assert_called_once()


@pytest.mark.asyncio
async def test_delete_scoped_deployment_does_not_remove_foreign_primary(
    mock_sdk: MagicMock,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    with (
        patch("nemo_deployments_plugin.backends.docker.backend.client_from_platform"),
        patch("nemo_deployments_plugin.backends.docker.backend.NemoEntitiesClient", return_value=mock_entities),
        patch("nemo_deployments_plugin.backends.docker.backend.get_shared_gpu_pool", return_value=None),
        patch("docker.from_env", return_value=mock_docker_client),
    ):
        backend = DockerDeploymentBackend(
            mock_sdk,
            {"docker_timeout": 60, "pull_images": False, "resource_scope": "e2e-abc123"},
        )

    foreign = MagicMock()
    foreign.name = container_name("default", "srv")
    foreign.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESOURCE_SCOPE_LABEL: "other-scope",
    }
    mock_docker_client.containers.list.return_value = []
    mock_docker_client.containers.get.return_value = foreign

    update = await backend.delete_deployment("default", "srv")

    assert update.status == "SUCCEEDED"
    foreign.stop.assert_not_called()
    foreign.remove.assert_not_called()


@pytest.mark.asyncio
async def test_delete_default_scoped_deployment_does_not_remove_foreign_primary(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    scoped = MagicMock()
    scoped.name = container_name("default", "srv")
    scoped.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESOURCE_SCOPE_LABEL: "e2e-abc123",
    }
    mock_docker_client.containers.list.return_value = [scoped]
    mock_docker_client.containers.get.return_value = scoped

    update = await docker_backend.delete_deployment("default", "srv")

    assert update.status == "SUCCEEDED"
    scoped.stop.assert_not_called()
    scoped.remove.assert_not_called()


@pytest.mark.asyncio
async def test_create_lora_group_does_not_remove_foreign_stale_init_container(
    mock_sdk: MagicMock,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    with (
        patch("nemo_deployments_plugin.backends.docker.backend.client_from_platform"),
        patch("nemo_deployments_plugin.backends.docker.backend.NemoEntitiesClient", return_value=mock_entities),
        patch("nemo_deployments_plugin.backends.docker.backend.get_shared_gpu_pool", return_value=None),
        patch("docker.from_env", return_value=mock_docker_client),
    ):
        backend = DockerDeploymentBackend(
            mock_sdk,
            {"docker_timeout": 60, "pull_images": False, "resource_scope": "e2e-abc123"},
        )

    foreign_stale = MagicMock()
    foreign_stale.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESOURCE_SCOPE_LABEL: "other-scope",
    }
    init_container = MagicMock()
    init_container.wait.return_value = {"StatusCode": 0}
    server_container = MagicMock(id="server123")
    sidecar_container = MagicMock(id="sidecar123")
    mock_entities.get.return_value = lora_config()
    mock_docker_client.containers.get.side_effect = [NotFound("missing"), foreign_stale]
    mock_docker_client.containers.run.side_effect = [init_container, server_container, sidecar_container]

    update = await backend.create_deployment(
        workspace="default",
        name="srv",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "STARTING"
    foreign_stale.remove.assert_not_called()


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
    labels = mock_docker_client.volumes.create.call_args.kwargs["labels"]
    assert labels[RESOURCE_SCOPE_LABEL] == DEFAULT_RESOURCE_SCOPE
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
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESTART_POLICY_LABEL: "Always",
        CONFIG_NAME_LABEL: "cfg1",
        RESOURCE_SCOPE_LABEL: DEFAULT_RESOURCE_SCOPE,
    }
    container.ports = {}
    container.attrs = container_attrs()
    mock_docker_client.containers.get.return_value = container
    mock_entities.get.return_value = sample_config()

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "READY"


def _running_server_container() -> MagicMock:
    container = MagicMock()
    container.id = "abc123def456"
    container.status = "running"
    container.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESTART_POLICY_LABEL: "Always",
        CONFIG_NAME_LABEL: "cfg1",
        RESOURCE_SCOPE_LABEL: DEFAULT_RESOURCE_SCOPE,
    }
    container.ports = {}
    container.attrs = container_attrs()
    return container


def _sidecar_container(role: str, status: str) -> MagicMock:
    sidecar = MagicMock()
    sidecar.status = status
    sidecar.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        CONTAINER_ROLE_LABEL: role,
        RESOURCE_SCOPE_LABEL: DEFAULT_RESOURCE_SCOPE,
    }
    return sidecar


@pytest.mark.asyncio
async def test_read_status_ready_when_sidecar_running(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    """Server ready + adapters sidecar running => READY."""
    mock_docker_client.containers.get.return_value = _running_server_container()
    mock_entities.get.return_value = lora_config()  # server + lora-adapters sidecar
    mock_docker_client.containers.list.return_value = [_sidecar_container("lora-adapters", "running")]

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "READY"


@pytest.mark.asyncio
async def test_read_status_starting_when_sidecar_stopped(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    """Server ready but the adapters sidecar is stopped => drop back to STARTING.

    Locks in the readiness gating: a present-but-not-running sidecar keeps the
    deployment out of READY.
    """
    mock_docker_client.containers.get.return_value = _running_server_container()
    mock_entities.get.return_value = lora_config()
    mock_docker_client.containers.list.return_value = [_sidecar_container("lora-adapters", "exited")]

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "STARTING"
    assert "sidecar" in update.status_message.lower()


@pytest.mark.asyncio
async def test_read_status_starting_when_sidecar_removed(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    """Server ready but the expected adapters sidecar is entirely gone => STARTING.

    A removed (not merely exited) sidecar is detected by comparing the expected
    sidecar roles from the config against the containers actually present.
    """
    mock_docker_client.containers.get.return_value = _running_server_container()
    mock_entities.get.return_value = lora_config()
    # The sidecar container has been removed: only unrelated containers remain.
    mock_docker_client.containers.list.return_value = []

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "STARTING"
    assert "sidecar" in update.status_message.lower()


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
    gpu_pool = MagicMock()
    docker_backend._gpu_pool = gpu_pool

    update = await docker_backend.read_status(workspace="default", name="srv")

    assert update.status == "LOST"
    gpu_pool.release_gpu.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("restart_policy", ["Never", "OnFailure"])
async def test_read_status_failed_and_releases_gpu_when_missing_one_shot(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
    restart_policy: RestartPolicy,
) -> None:
    expected_container_name = container_name("default", "job")
    mock_docker_client.containers.get.side_effect = NotFound("missing")

    deployment_entity = MagicMock()
    deployment_entity.deployment_config = "cfg1"

    async def get_side_effect(entity_type, name, workspace=None):
        if entity_type is Deployment:
            return deployment_entity
        return sample_config(restart_policy=restart_policy)

    mock_entities.get.side_effect = get_side_effect
    gpu_pool = MagicMock()
    docker_backend._gpu_pool = gpu_pool

    update = await docker_backend.read_status(workspace="default", name="job")

    assert update.status == "FAILED"
    assert update.exit_code is None
    assert update.error_details == {
        "expected_container_name": expected_container_name,
    }
    gpu_pool.release_gpu.assert_called_once_with(deployment_key("default", "job"))


@pytest.mark.asyncio
async def test_read_status_treats_foreign_container_as_missing(
    mock_sdk: MagicMock,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    with (
        patch("nemo_deployments_plugin.backends.docker.backend.client_from_platform"),
        patch("nemo_deployments_plugin.backends.docker.backend.NemoEntitiesClient", return_value=mock_entities),
        patch("nemo_deployments_plugin.backends.docker.backend.get_shared_gpu_pool", return_value=None),
        patch("docker.from_env", return_value=mock_docker_client),
    ):
        backend = DockerDeploymentBackend(
            mock_sdk,
            {"docker_timeout": 60, "pull_images": False, "resource_scope": "e2e-abc123"},
        )

    foreign = MagicMock()
    foreign.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESOURCE_SCOPE_LABEL: "other-scope",
    }
    mock_docker_client.containers.get.return_value = foreign

    deployment_entity = MagicMock()
    deployment_entity.deployment_config = "cfg1"

    async def get_side_effect(entity_type, name, workspace=None):
        if entity_type is Deployment:
            return deployment_entity
        return sample_config(restart_policy="Always")

    mock_entities.get.side_effect = get_side_effect

    update = await backend.read_status(workspace="default", name="srv")

    assert update.status == "LOST"
    foreign.reload.assert_not_called()


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
        RESOURCE_SCOPE_LABEL: DEFAULT_RESOURCE_SCOPE,
    }
    mock_docker_client.containers.list.return_value = [container]

    names = await docker_backend.list_managed_deployment_names()

    assert names == ["default/srv"]


def _one_shot_server_container(
    *,
    restart_policy: str,
    status: str = "exited",
    exit_code: int = 0,
    restart_count: int = 0,
    backoff_limit: str = "6",
) -> MagicMock:
    container = MagicMock()
    container.name = container_name("default", "job")
    container.wait.return_value = {"StatusCode": exit_code}
    container.labels = {
        RESTART_POLICY_LABEL: restart_policy,
        BACKOFF_LIMIT_LABEL: backoff_limit,
    }
    container.status = status
    container.attrs = {
        **container_attrs(exit_code=exit_code),
        "RestartCount": restart_count,
    }
    return container


@pytest.mark.asyncio
async def test_create_never_job_returns_succeeded_when_container_exits_immediately(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config(restart_policy="Never")
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    mock_docker_client.containers.run.return_value = _one_shot_server_container(
        restart_policy="Never",
        exit_code=0,
    )

    update = await docker_backend.create_deployment(
        workspace="default",
        name="job",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "SUCCEEDED"
    assert update.exit_code == 0
    mock_docker_client.containers.run.return_value.wait.assert_called_once_with(timeout=5)


@pytest.mark.asyncio
async def test_create_never_job_uses_configured_oneshot_observe_timeout(
    mock_sdk: MagicMock,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    with (
        patch("nemo_deployments_plugin.backends.docker.backend.client_from_platform"),
        patch("nemo_deployments_plugin.backends.docker.backend.NemoEntitiesClient", return_value=mock_entities),
        patch("nemo_deployments_plugin.backends.docker.backend.get_shared_gpu_pool", return_value=None),
        patch("docker.from_env", return_value=mock_docker_client),
    ):
        backend = DockerDeploymentBackend(
            mock_sdk,
            {"docker_timeout": 600, "oneshot_observe_timeout_seconds": 7, "pull_images": False},
        )
        backend._client = mock_docker_client

    mock_entities.get.return_value = sample_config(restart_policy="Never")
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    mock_docker_client.containers.run.return_value = _one_shot_server_container(
        restart_policy="Never",
        exit_code=0,
    )

    update = await backend.create_deployment(
        workspace="default",
        name="job",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "SUCCEEDED"
    mock_docker_client.containers.run.return_value.wait.assert_called_once_with(timeout=7)


@pytest.mark.asyncio
async def test_create_never_job_returns_failed_on_non_zero_exit(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config(restart_policy="Never")
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    mock_docker_client.containers.run.return_value = _one_shot_server_container(
        restart_policy="Never",
        exit_code=42,
    )

    update = await docker_backend.create_deployment(
        workspace="default",
        name="job",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "FAILED"
    assert update.exit_code == 42


@pytest.mark.asyncio
async def test_create_on_failure_returns_succeeded_when_already_exited_zero(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config(restart_policy="OnFailure")
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    server = _one_shot_server_container(restart_policy="OnFailure", exit_code=0)
    mock_docker_client.containers.run.return_value = server

    update = await docker_backend.create_deployment(
        workspace="default",
        name="job",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "SUCCEEDED"
    assert update.exit_code == 0
    server.wait.assert_not_called()


@pytest.mark.asyncio
async def test_create_on_failure_returns_starting_when_failed_under_backoff(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config(restart_policy="OnFailure")
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    server = _one_shot_server_container(
        restart_policy="OnFailure",
        exit_code=1,
        restart_count=2,
        backoff_limit="6",
    )
    mock_docker_client.containers.run.return_value = server

    update = await docker_backend.create_deployment(
        workspace="default",
        name="job",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "STARTING"
    assert update.exit_code == 1
    assert "retry 2/6" in update.status_message


@pytest.mark.asyncio
async def test_create_on_failure_returns_starting_when_still_running(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config(restart_policy="OnFailure")
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    server = _one_shot_server_container(restart_policy="OnFailure", status="running", exit_code=0)
    mock_docker_client.containers.run.return_value = server

    update = await docker_backend.create_deployment(
        workspace="default",
        name="job",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "STARTING"
    assert "created" in update.status_message.lower()
    server.wait.assert_not_called()


@pytest.mark.asyncio
async def test_create_never_job_returns_starting_when_wait_times_out(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config(restart_policy="Never")
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    server = _one_shot_server_container(restart_policy="Never", exit_code=0)
    server.wait.side_effect = ReadTimeout("timed out")
    mock_docker_client.containers.run.return_value = server

    update = await docker_backend.create_deployment(
        workspace="default",
        name="job",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "STARTING"
    assert "after observe wait (5s)" in update.status_message
    server.wait.assert_called_once_with(timeout=5)


@pytest.mark.asyncio
async def test_create_never_job_returns_starting_when_wait_connection_error(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config(restart_policy="Never")
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    server = _one_shot_server_container(restart_policy="Never", exit_code=0)
    server.wait.side_effect = RequestsConnectionError("connection reset")
    mock_docker_client.containers.run.return_value = server

    update = await docker_backend.create_deployment(
        workspace="default",
        name="job",
        config_name="cfg1",
        labels={"managed-by": MANAGED_BY_LABEL},
        backend_config={},
    )

    assert update.status == "STARTING"
    assert "after observe wait (5s)" in update.status_message
    server.wait.assert_called_once_with(timeout=5)


@pytest.mark.asyncio
async def test_create_never_job_cleans_up_on_wait_error(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config(restart_policy="Never")
    mock_docker_client.containers.get.side_effect = NotFound("missing")
    server = _one_shot_server_container(restart_policy="Never", exit_code=0)
    server.wait.side_effect = RuntimeError("boom")
    mock_docker_client.containers.run.return_value = server

    with patch.object(
        docker_backend,
        "delete_deployment",
        new_callable=AsyncMock,
        return_value=BackendStatusUpdate(status="SUCCEEDED", status_message="deleted"),
    ) as mock_delete:
        update = await docker_backend.create_deployment(
            workspace="default",
            name="job",
            config_name="cfg1",
            labels={"managed-by": MANAGED_BY_LABEL},
            backend_config={},
        )

    assert update.status == "FAILED"
    mock_delete.assert_awaited_once_with("default", "job")


@pytest.mark.asyncio
async def test_create_always_still_returns_starting(
    docker_backend: DockerDeploymentBackend,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    mock_entities.get.return_value = sample_config(restart_policy="Always")
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
    mock_docker_client.containers.run.return_value.wait.assert_not_called()


@pytest.mark.asyncio
async def test_default_list_managed_deployment_names_ignores_foreign_scoped_resources(
    docker_backend: DockerDeploymentBackend,
    mock_docker_client: MagicMock,
) -> None:
    default_scoped = MagicMock()
    default_scoped.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESOURCE_SCOPE_LABEL: DEFAULT_RESOURCE_SCOPE,
    }
    scoped = MagicMock()
    scoped.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "foreign",
        RESOURCE_SCOPE_LABEL: "e2e-abc123",
    }
    mock_docker_client.containers.list.return_value = [default_scoped, scoped]

    names = await docker_backend.list_managed_deployment_names()

    assert names == ["default/srv"]


@pytest.mark.asyncio
async def test_list_managed_deployment_names_scopes_docker_query(
    mock_sdk: MagicMock,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    with (
        patch("nemo_deployments_plugin.backends.docker.backend.client_from_platform"),
        patch("nemo_deployments_plugin.backends.docker.backend.NemoEntitiesClient", return_value=mock_entities),
        patch("nemo_deployments_plugin.backends.docker.backend.get_shared_gpu_pool", return_value=None),
        patch("docker.from_env", return_value=mock_docker_client),
    ):
        backend = DockerDeploymentBackend(
            mock_sdk,
            {"docker_timeout": 60, "pull_images": False, "resource_scope": "e2e-abc123"},
        )

    container = MagicMock()
    container.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESOURCE_SCOPE_LABEL: "e2e-abc123",
    }
    mock_docker_client.containers.list.return_value = [container]

    names = await backend.list_managed_deployment_names()

    assert names == ["default/srv"]
    mock_docker_client.containers.list.assert_called_once_with(
        all=True,
        filters={
            "label": [
                f"{MANAGED_BY_KEY}={MANAGED_BY_LABEL}",
                f"{RESOURCE_SCOPE_LABEL}=e2e-abc123",
            ]
        },
    )


@pytest.mark.asyncio
async def test_get_logs_treats_foreign_container_as_missing(
    mock_sdk: MagicMock,
    mock_entities: AsyncMock,
    mock_docker_client: MagicMock,
) -> None:
    with (
        patch("nemo_deployments_plugin.backends.docker.backend.client_from_platform"),
        patch("nemo_deployments_plugin.backends.docker.backend.NemoEntitiesClient", return_value=mock_entities),
        patch("nemo_deployments_plugin.backends.docker.backend.get_shared_gpu_pool", return_value=None),
        patch("docker.from_env", return_value=mock_docker_client),
    ):
        backend = DockerDeploymentBackend(
            mock_sdk,
            {"docker_timeout": 60, "pull_images": False, "resource_scope": "e2e-abc123"},
        )

    foreign = MagicMock()
    foreign.labels = {
        "managed-by": MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: "default",
        DEPLOYMENT_NAME_LABEL: "srv",
        RESOURCE_SCOPE_LABEL: "other-scope",
    }
    mock_docker_client.containers.get.return_value = foreign

    logs = await backend.get_logs(workspace="default", name="srv")

    assert logs.lines == [f"Container {container_name('default', 'srv')} not found"]
    foreign.logs.assert_not_called()


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
