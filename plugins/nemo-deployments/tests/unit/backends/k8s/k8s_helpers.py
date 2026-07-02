# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Test helpers for k8s backend unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from nemo_deployments_plugin.backends.labels import (
    BACKOFF_LIMIT_LABEL,
    CONFIG_NAME_LABEL,
    DEPLOYMENT_NAME_LABEL,
    DEPLOYMENT_WORKSPACE_LABEL,
    MANAGED_BY_KEY,
    RESTART_POLICY_LABEL,
    deployment_identity_labels,
    k8s_deployment_resource_name,
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_deployments_plugin.entities import Container, ContainerPort, Deployment, DeploymentConfig
from nemo_deployments_plugin.types import RestartPolicy


def sample_config(*, restart_policy: RestartPolicy = "Never") -> DeploymentConfig:
    return DeploymentConfig(
        name="config1",
        workspace="default",
        containers=[
            Container(
                name="main",
                image="alpine:latest",
                command=["echo"],
                args=["hello"],
            )
        ],
    ).model_copy(update={"restart_policy": restart_policy})


def sample_deployment(*, config_name: str = "config1") -> Deployment:
    return Deployment(
        name="task",
        workspace="default",
        deployment_config=config_name,
    )


def sample_always_config(*, with_port: bool = True) -> DeploymentConfig:
    ports = [ContainerPort(name="http", containerPort=8080)] if with_port else []
    return DeploymentConfig(
        name="config1",
        workspace="default",
        containers=[
            Container(
                name="main",
                image="nginx:alpine",
                ports=ports,
            )
        ],
    ).model_copy(update={"restart_policy": "Always"})


def always_identity_labels(
    workspace: str = "default",
    name: str = "task",
    *,
    config_name: str = "config1",
    backoff_limit: int = 6,
) -> dict[str, str]:
    return deployment_identity_labels(
        workspace,
        name,
        "Always",
        config_name=config_name,
        backoff_limit=backoff_limit,
    )


def mock_deployment(
    *,
    workspace: str = "default",
    name: str = "task",
    ready_replicas: int = 0,
    deleting: bool = False,
) -> MagicMock:
    labels = always_identity_labels(workspace=workspace, name=name)
    resource_name = k8s_deployment_resource_name(workspace, name)
    deployment = MagicMock()
    deployment.metadata.labels = labels
    deployment.metadata.deletion_timestamp = "2026-01-01T00:00:00Z" if deleting else None
    deployment.status.ready_replicas = ready_replicas
    deployment.status.available_replicas = ready_replicas
    deployment.spec.selector.match_labels = {"app": resource_name}
    return deployment


def mock_pod(
    *,
    waiting_reason: str | None = None,
    waiting_message: str = "",
    restart_count: int = 0,
    phase: str = "Pending",
) -> MagicMock:
    pod = MagicMock()
    pod.metadata.name = "task-pod-1"
    pod.metadata.creation_timestamp = "2026-01-02T00:00:00Z"
    pod.status.phase = phase
    container_status = MagicMock()
    container_status.restart_count = restart_count
    if waiting_reason is None:
        container_status.state.waiting = None
    else:
        container_status.state.waiting.reason = waiting_reason
        container_status.state.waiting.message = waiting_message
    pod.status.container_statuses = [container_status]
    return pod


def deployment_list_item(*, workspace: str, name: str) -> MagicMock:
    item = MagicMock()
    item.metadata.labels = {
        MANAGED_BY_KEY: MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: workspace,
        DEPLOYMENT_NAME_LABEL: name,
        RESTART_POLICY_LABEL: "Always",
        CONFIG_NAME_LABEL: "config1",
        BACKOFF_LIMIT_LABEL: "6",
    }
    return item


def job_identity_labels(
    workspace: str = "default",
    name: str = "task",
    *,
    restart_policy: RestartPolicy = "Never",
    config_name: str = "config1",
    backoff_limit: int = 6,
) -> dict[str, str]:
    return deployment_identity_labels(
        workspace,
        name,
        restart_policy,
        config_name=config_name,
        backoff_limit=backoff_limit,
    )


def mock_job(
    *,
    workspace: str = "default",
    name: str = "task",
    restart_policy: RestartPolicy = "Never",
    config_name: str = "config1",
    active: int = 0,
    complete: bool = False,
    failed: bool = False,
    deleting: bool = False,
) -> MagicMock:
    labels = job_identity_labels(
        workspace,
        name,
        restart_policy=restart_policy,
        config_name=config_name,
    )
    job = MagicMock()
    job.metadata.labels = labels
    job.metadata.deletion_timestamp = "2026-01-01T00:00:00Z" if deleting else None
    job.status.active = active
    job.status.succeeded = 1 if complete else 0
    job.status.failed = 1 if failed else 0
    job.status.conditions = []
    if complete:
        condition = MagicMock()
        condition.type = "Complete"
        condition.status = "True"
        condition.message = None
        job.status.conditions.append(condition)
    if failed:
        condition = MagicMock()
        condition.type = "Failed"
        condition.status = "True"
        condition.message = "BackoffLimitExceeded"
        job.status.conditions.append(condition)
    return job


def job_list_item(*, workspace: str, name: str) -> MagicMock:
    item = MagicMock()
    item.metadata.labels = {
        MANAGED_BY_KEY: MANAGED_BY_LABEL,
        DEPLOYMENT_WORKSPACE_LABEL: workspace,
        DEPLOYMENT_NAME_LABEL: name,
        RESTART_POLICY_LABEL: "Never",
        CONFIG_NAME_LABEL: "config1",
        BACKOFF_LIMIT_LABEL: "0",
    }
    return item
