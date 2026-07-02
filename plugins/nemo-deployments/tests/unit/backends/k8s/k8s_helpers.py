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
)
from nemo_deployments_plugin.constants import MANAGED_BY_LABEL
from nemo_deployments_plugin.entities import Container, Deployment, DeploymentConfig
from nemo_deployments_plugin.types import RestartPolicy


def sample_config(*, restart_policy: RestartPolicy = "Never") -> DeploymentConfig:
    return DeploymentConfig(
        name="cfg1",
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


def sample_deployment(*, config_name: str = "cfg1") -> Deployment:
    return Deployment(
        name="task",
        workspace="default",
        deployment_config=config_name,
    )


def job_identity_labels(
    workspace: str = "default",
    name: str = "task",
    *,
    restart_policy: RestartPolicy = "Never",
    config_name: str = "cfg1",
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
    config_name: str = "cfg1",
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
        CONFIG_NAME_LABEL: "cfg1",
        BACKOFF_LIMIT_LABEL: "0",
    }
    return item
