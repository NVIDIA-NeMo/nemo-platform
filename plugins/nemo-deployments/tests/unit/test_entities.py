# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from nemo_deployments_plugin.entities import Container, Deployment, DeploymentConfig, Volume
from nemo_deployments_plugin.validation import PrerequisiteCycleError, detect_prerequisite_cycle
from pydantic import ValidationError


def test_deployment_defaults_to_pending() -> None:
    dep = Deployment(name="d1", workspace="default", deployment_config="cfg")
    assert dep.status == "PENDING"
    assert dep.desired_state == "READY"


def test_deployment_config_requires_containers_shape() -> None:
    cfg = DeploymentConfig(
        name="cfg",
        workspace="default",
        containers=[Container(name="main", image="nginx:latest")],
    )
    assert cfg.containers[0].image == "nginx:latest"


def test_volume_default_status_pending() -> None:
    vol = Volume(name="v1", workspace="default")
    assert vol.status == "PENDING"
    assert vol.size == "1Gi"


def test_prerequisite_cycle_detected() -> None:
    with pytest.raises(PrerequisiteCycleError):
        detect_prerequisite_cycle(
            config_name="c",
            prerequisites=["a"],
            existing={"a": ["b"], "b": ["c"]},
        )


def test_invalid_deployment_status_rejected() -> None:
    with pytest.raises(ValidationError):
        Deployment.model_validate(
            {
                "name": "d1",
                "workspace": "default",
                "deployment_config": "cfg",
                "status": "not-a-status",
            }
        )
