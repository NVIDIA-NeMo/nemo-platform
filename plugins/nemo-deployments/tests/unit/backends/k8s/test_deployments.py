# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from backends.k8s.k8s_helpers import (
    always_identity_labels,
    deployment_list_item,
    mock_deployment,
    mock_pod,
    sample_always_config,
    sample_deployment,
)
from kubernetes.client.rest import ApiException
from nemo_deployments_plugin.backends.k8s import deployments as deployment_ops
from nemo_deployments_plugin.backends.k8s.client import KubernetesClients
from nemo_deployments_plugin.backends.k8s.compiler import validate_config_for_deployment
from nemo_deployments_plugin.backends.k8s.deployments import (
    build_in_cluster_endpoints,
)
from nemo_deployments_plugin.backends.labels import (
    MANAGED_BY_KEY,
    k8s_deployment_configmap_name,
    k8s_deployment_resource_name,
)
from nemo_deployments_plugin.entities import ConfigFile, Container, ContainerPort
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError


@pytest.fixture
def always_deployment_context(mock_entities: AsyncMock) -> None:
    mock_entities.get.side_effect = [sample_deployment(), sample_always_config()]


@pytest.fixture
def deployment_ops_clients(mock_k8s_clients: MagicMock) -> MagicMock:
    clients = MagicMock(spec=KubernetesClients)
    clients.apps_v1 = mock_k8s_clients.apps_v1
    clients.core_v1 = mock_k8s_clients.core_v1
    clients.request_timeout = mock_k8s_clients.request_timeout
    return clients


def test_validate_config_for_deployment_rejects_never() -> None:
    from nemo_deployments_plugin.backends.k8s.compiler import DeploymentConfigError

    with pytest.raises(DeploymentConfigError, match="Always"):
        validate_config_for_deployment(sample_always_config().model_copy(update={"restart_policy": "Never"}))


def test_build_in_cluster_endpoints_uses_cluster_dns() -> None:
    resource_name = k8s_deployment_resource_name("default", "task")
    endpoints = build_in_cluster_endpoints(
        resource_name=resource_name,
        namespace="nemo-deployments",
        containers=tuple(sample_always_config().containers),
    )
    assert endpoints[0].url == f"http://{resource_name}.nemo-deployments.svc.cluster.local:8080"


def test_build_in_cluster_endpoints_uses_tcp_scheme_for_udp() -> None:
    resource_name = k8s_deployment_resource_name("default", "task")
    container = (
        sample_always_config()
        .containers[0]
        .model_copy(update={"ports": [ContainerPort(name="metrics", containerPort=9090, protocol="UDP")]})
    )
    endpoints = build_in_cluster_endpoints(
        resource_name=resource_name,
        namespace="nemo-deployments",
        containers=(container,),
    )
    assert endpoints[0].protocol == "tcp"
    assert endpoints[0].url == f"tcp://{resource_name}.nemo-deployments.svc.cluster.local:9090"


@pytest.mark.asyncio
async def test_create_deployment_emits_deployment_and_service(
    k8s_backend, mock_k8s_clients: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_entities.get.return_value = sample_always_config()
    mock_k8s_clients.apps_v1.create_namespaced_deployment.return_value = mock_deployment()
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = mock_deployment()
    mock_k8s_clients.core_v1.list_namespaced_pod.return_value = MagicMock(items=[])

    await k8s_backend.create_deployment(
        workspace="default",
        name="task",
        config_name="config1",
        labels={},
        backend_config={},
    )

    deployment_body = mock_k8s_clients.apps_v1.create_namespaced_deployment.call_args.kwargs["body"]
    service_body = mock_k8s_clients.core_v1.create_namespaced_service.call_args.kwargs["body"]
    assert deployment_body.kind == "Deployment"
    assert deployment_body.spec.replicas == 1
    assert deployment_body.spec.selector.match_labels["app"] == deployment_body.metadata.name
    assert service_body.spec.type == "ClusterIP"
    assert service_body.spec.selector["app"] == service_body.metadata.name


@pytest.mark.asyncio
async def test_create_deployment_ready_reports_endpoints(
    k8s_backend, mock_k8s_clients: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_entities.get.return_value = sample_always_config()
    ready = mock_deployment(ready_replicas=1)
    mock_k8s_clients.apps_v1.create_namespaced_deployment.return_value = ready
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = ready
    mock_k8s_clients.core_v1.list_namespaced_pod.return_value = MagicMock(items=[])

    update = await k8s_backend.create_deployment(
        workspace="default",
        name="task",
        config_name="config1",
        labels={},
        backend_config={},
    )

    assert update.status == "READY"
    assert update.endpoints
    assert "svc.cluster.local" in update.endpoints[0].url


@pytest.mark.asyncio
async def test_create_deployment_conflict_rejects_foreign(
    deployment_ops_clients: MagicMock, mock_k8s_clients: MagicMock
) -> None:
    foreign = mock_deployment()
    foreign.metadata.labels = {MANAGED_BY_KEY: "other-plugin"}
    mock_k8s_clients.apps_v1.create_namespaced_deployment.side_effect = ApiException(status=409)
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = foreign

    update = await deployment_ops.create_deployment(
        deployment_ops_clients,
        default_namespace="default",
        workspace="default",
        name="task",
        config_name="config1",
        labels={},
        backend_config={},
        config=sample_always_config(),
    )

    assert update.status == "FAILED"
    assert "not managed" in update.status_message
    mock_k8s_clients.core_v1.create_namespaced_service.assert_not_called()


@pytest.mark.asyncio
async def test_create_deployment_service_conflict_rejects_foreign(
    deployment_ops_clients: MagicMock, mock_k8s_clients: MagicMock
) -> None:
    mock_k8s_clients.apps_v1.create_namespaced_deployment.return_value = mock_deployment()
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = mock_deployment()
    foreign_service = MagicMock()
    foreign_service.metadata.labels = {MANAGED_BY_KEY: "other-plugin"}
    mock_k8s_clients.core_v1.create_namespaced_service.side_effect = ApiException(status=409)
    mock_k8s_clients.core_v1.read_namespaced_service.return_value = foreign_service

    update = await deployment_ops.create_deployment(
        deployment_ops_clients,
        default_namespace="default",
        workspace="default",
        name="task",
        config_name="config1",
        labels={},
        backend_config={},
        config=sample_always_config(),
    )

    assert update.status == "FAILED"
    mock_k8s_clients.apps_v1.delete_namespaced_deployment.assert_called_once()


@pytest.mark.asyncio
async def test_create_deployment_rolls_back_when_service_create_fails(
    deployment_ops_clients: MagicMock, mock_k8s_clients: MagicMock
) -> None:
    mock_k8s_clients.apps_v1.create_namespaced_deployment.return_value = mock_deployment()
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = mock_deployment()
    mock_k8s_clients.core_v1.create_namespaced_service.side_effect = ApiException(status=500)

    update = await deployment_ops.create_deployment(
        deployment_ops_clients,
        default_namespace="default",
        workspace="default",
        name="task",
        config_name="config1",
        labels={},
        backend_config={},
        config=sample_always_config(),
    )

    assert update.status == "FAILED"
    mock_k8s_clients.apps_v1.delete_namespaced_deployment.assert_called_once()


@pytest.mark.asyncio
async def test_create_deployment_rolls_back_configmap_when_service_create_fails(
    deployment_ops_clients: MagicMock, mock_k8s_clients: MagicMock
) -> None:
    config = sample_always_config().model_copy(
        update={"config_files": [ConfigFile(path="/etc/app/config.yaml", content="key: value")]}
    )
    mock_k8s_clients.apps_v1.create_namespaced_deployment.return_value = mock_deployment()
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = mock_deployment()
    mock_k8s_clients.core_v1.create_namespaced_service.side_effect = ApiException(status=500)
    identity_labels = always_identity_labels(backoff_limit=config.backoff_limit)
    mock_k8s_clients.core_v1.read_namespaced_config_map.return_value = SimpleNamespace(
        metadata=SimpleNamespace(labels=identity_labels),
    )

    update = await deployment_ops.create_deployment(
        deployment_ops_clients,
        default_namespace="default",
        workspace="default",
        name="task",
        config_name="config1",
        labels={},
        backend_config={},
        config=config,
    )

    assert update.status == "FAILED"
    mock_k8s_clients.core_v1.create_namespaced_config_map.assert_called_once()
    mock_k8s_clients.core_v1.read_namespaced_config_map.assert_called_once_with(
        name=k8s_deployment_configmap_name("default", "task"),
        namespace="default",
        _request_timeout=mock_k8s_clients.request_timeout,
    )
    mock_k8s_clients.core_v1.delete_namespaced_config_map.assert_called_once()


@pytest.mark.asyncio
async def test_create_deployment_adopted_service_failure_keeps_configmap(
    deployment_ops_clients: MagicMock, mock_k8s_clients: MagicMock
) -> None:
    config = sample_always_config().model_copy(
        update={"config_files": [ConfigFile(path="/etc/app/config.yaml", content="key: value")]}
    )
    mock_k8s_clients.apps_v1.create_namespaced_deployment.side_effect = ApiException(status=409)
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = mock_deployment()
    mock_k8s_clients.core_v1.create_namespaced_service.side_effect = ApiException(status=500)

    update = await deployment_ops.create_deployment(
        deployment_ops_clients,
        default_namespace="default",
        workspace="default",
        name="task",
        config_name="config1",
        labels={},
        backend_config={},
        config=config,
    )

    assert update.status == "FAILED"
    mock_k8s_clients.apps_v1.delete_namespaced_deployment.assert_not_called()
    mock_k8s_clients.core_v1.delete_namespaced_config_map.assert_not_called()


@pytest.mark.asyncio
async def test_read_status_accepts_init_containers(
    k8s_backend, mock_k8s_clients: MagicMock, mock_entities: AsyncMock
) -> None:
    config = sample_always_config().model_copy(update={"init_containers": [Container(name="init", image="busybox")]})
    mock_entities.get.side_effect = [sample_deployment(), config]
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = mock_deployment()
    mock_k8s_clients.core_v1.list_namespaced_pod.return_value = MagicMock(items=[])

    update = await k8s_backend.read_status(workspace="default", name="task")

    assert update.status == "STARTING"


@pytest.mark.asyncio
async def test_read_deployment_status_lost_on_404(
    k8s_backend, mock_k8s_clients: MagicMock, always_deployment_context: None
) -> None:
    mock_k8s_clients.apps_v1.read_namespaced_deployment.side_effect = ApiException(status=404)

    update = await k8s_backend.read_status(workspace="default", name="task")

    assert update.status == "LOST"
    assert "not found" in update.status_message


@pytest.mark.asyncio
async def test_read_deployment_status_image_pull_backoff(
    k8s_backend, mock_k8s_clients: MagicMock, always_deployment_context: None
) -> None:
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = mock_deployment(ready_replicas=0)
    mock_k8s_clients.core_v1.list_namespaced_pod.return_value = MagicMock(
        items=[mock_pod(waiting_reason="ImagePullBackOff", waiting_message="pull access denied")]
    )

    update = await k8s_backend.read_status(workspace="default", name="task")

    assert update.status == "STARTING"
    assert "ImagePullBackOff" in update.status_message


@pytest.mark.asyncio
async def test_read_deployment_status_crash_loop_failed(
    k8s_backend, mock_k8s_clients: MagicMock, always_deployment_context: None
) -> None:
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = mock_deployment(ready_replicas=0)
    mock_k8s_clients.core_v1.list_namespaced_pod.return_value = MagicMock(
        items=[mock_pod(waiting_reason="CrashLoopBackOff", waiting_message="back-off", restart_count=3)]
    )

    update = await k8s_backend.read_status(workspace="default", name="task")

    assert update.status == "FAILED"
    assert "CrashLoopBackOff" in update.status_message


@pytest.mark.asyncio
async def test_delete_deployment_removes_service(
    k8s_backend, mock_k8s_clients: MagicMock, always_deployment_context: None
) -> None:
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = mock_deployment()

    update = await k8s_backend.delete_deployment("default", "task")

    assert update.status == "SUCCEEDED"
    mock_k8s_clients.apps_v1.delete_namespaced_deployment.assert_called_once()
    mock_k8s_clients.core_v1.delete_namespaced_service.assert_called_once()


@pytest.mark.asyncio
async def test_delete_deployment_rejects_foreign(
    deployment_ops_clients: MagicMock, mock_k8s_clients: MagicMock
) -> None:
    foreign = mock_deployment()
    foreign.metadata.labels = {MANAGED_BY_KEY: "other-plugin"}
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = foreign
    mock_k8s_clients.core_v1.read_namespaced_config_map.return_value = SimpleNamespace(
        metadata=SimpleNamespace(labels=always_identity_labels()),
    )

    update = await deployment_ops.delete_deployment(
        deployment_ops_clients,
        default_namespace="default",
        workspace="default",
        name="task",
        backend_config={},
        expected_labels=always_identity_labels(),
    )

    assert update.status == "FAILED"
    mock_k8s_clients.apps_v1.delete_namespaced_deployment.assert_not_called()
    mock_k8s_clients.core_v1.read_namespaced_config_map.assert_called_once_with(
        name=k8s_deployment_configmap_name("default", "task"),
        namespace="default",
        _request_timeout=mock_k8s_clients.request_timeout,
    )


@pytest.mark.asyncio
async def test_list_managed_deployment_names_includes_always(k8s_backend, mock_k8s_clients: MagicMock) -> None:
    listed = MagicMock()
    listed.items = [deployment_list_item(workspace="default", name="server")]
    mock_k8s_clients.apps_v1.list_namespaced_deployment.return_value = listed
    mock_k8s_clients.batch_v1.list_namespaced_job.return_value = MagicMock(items=[])

    names = await k8s_backend.list_managed_deployment_names()

    assert names == ["default/server"]


@pytest.mark.asyncio
async def test_get_deployment_logs(k8s_backend, mock_k8s_clients: MagicMock, always_deployment_context: None) -> None:
    pod = mock_pod()
    mock_k8s_clients.core_v1.list_namespaced_pod.return_value = MagicMock(items=[pod])
    mock_k8s_clients.core_v1.read_namespaced_pod_log.return_value = "listening\n"

    result = await k8s_backend.get_logs(workspace="default", name="task", tail=10)

    assert result.lines == ["listening"]


@pytest.mark.asyncio
async def test_delete_deployment_orphan_returns_deployment_failure(
    k8s_backend, mock_k8s_clients: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_entities.get.side_effect = NemoEntityNotFoundError("missing")
    foreign = mock_deployment()
    foreign.metadata.labels = {MANAGED_BY_KEY: "other-plugin"}
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = foreign
    mock_k8s_clients.batch_v1.read_namespaced_job.side_effect = ApiException(status=404)

    update = await k8s_backend.delete_deployment("default", "task")

    assert update.status == "FAILED"
    assert "not managed" in update.status_message
    mock_k8s_clients.apps_v1.delete_namespaced_deployment.assert_not_called()


@pytest.mark.asyncio
async def test_delete_deployment_orphan_skips_foreign_service(
    deployment_ops_clients: MagicMock, mock_k8s_clients: MagicMock
) -> None:
    foreign_service = MagicMock()
    foreign_service.metadata.labels = {MANAGED_BY_KEY: "other-plugin"}
    mock_k8s_clients.apps_v1.read_namespaced_deployment.side_effect = ApiException(status=404)
    mock_k8s_clients.core_v1.read_namespaced_service.return_value = foreign_service

    update = await deployment_ops.delete_deployment(
        deployment_ops_clients,
        default_namespace="default",
        workspace="default",
        name="task",
        backend_config={},
        expected_labels=always_identity_labels(),
    )

    assert update.status == "SUCCEEDED"
    mock_k8s_clients.core_v1.delete_namespaced_service.assert_not_called()


@pytest.mark.asyncio
async def test_delete_deployment_orphan_when_entity_missing(
    k8s_backend, mock_k8s_clients: MagicMock, mock_entities: AsyncMock
) -> None:
    mock_entities.get.side_effect = NemoEntityNotFoundError("missing")
    mock_k8s_clients.apps_v1.read_namespaced_deployment.return_value = mock_deployment()
    mock_k8s_clients.batch_v1.read_namespaced_job.side_effect = ApiException(status=404)

    update = await k8s_backend.delete_deployment("default", "task")

    assert update.status == "SUCCEEDED"
    mock_k8s_clients.apps_v1.delete_namespaced_deployment.assert_called_once()
