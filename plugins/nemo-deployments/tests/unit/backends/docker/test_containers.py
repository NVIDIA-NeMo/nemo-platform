# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the docker DeploymentConfig -> orchestration plan builder."""

from __future__ import annotations

import pytest
from backends.docker.docker_helpers import lora_config, sample_config
from nemo_deployments_plugin.backends.docker.containers import (
    DeploymentConfigError,
    build_docker_plan,
    validate_config_for_docker,
)
from nemo_deployments_plugin.entities import Container, ContainerPort, DeploymentConfig


def test_single_container_plan_has_no_init_or_sidecars() -> None:
    plan = build_docker_plan(sample_config())
    assert plan.primary.name == "main"
    assert plan.init_containers == []
    assert plan.sidecars == []
    assert plan.is_multi_container is False


def test_lora_plan_splits_init_primary_and_sidecar() -> None:
    plan = build_docker_plan(lora_config())
    assert plan.primary.name == "server"
    assert [c.name for c in plan.init_containers] == ["lora-cache-init"]
    assert [c.name for c in plan.sidecars] == ["lora-adapters"]
    assert plan.is_multi_container is True


def test_plan_rejects_sidecar_with_ports() -> None:
    config = DeploymentConfig(
        name="cfg1",
        workspace="default",
        containers=[
            Container(name="server", image="img", ports=[ContainerPort(name="http", containerPort=8000)]),
            Container(name="sidecar", image="img2", ports=[ContainerPort(name="x", containerPort=9000)]),
        ],
    )
    with pytest.raises(DeploymentConfigError, match="may not declare ports"):
        build_docker_plan(config)


def test_plan_rejects_empty_config() -> None:
    config = DeploymentConfig(name="cfg1", workspace="default", containers=[])
    with pytest.raises(DeploymentConfigError, match="at least one container"):
        build_docker_plan(config)


def test_validate_config_returns_primary_for_back_compat() -> None:
    assert validate_config_for_docker(sample_config()).name == "main"
    assert validate_config_for_docker(lora_config()).name == "server"
