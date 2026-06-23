# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Test helpers for docker backend unit tests."""

from __future__ import annotations

from typing import Any

from nemo_deployments_plugin.entities import Container, DeploymentConfig
from nemo_deployments_plugin.types import RestartPolicy


def sample_config(*, restart_policy: RestartPolicy = "Always") -> DeploymentConfig:
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
        restart_policy=restart_policy,
    )


def container_attrs(*, status: str = "running", exit_code: int = 0) -> dict[str, Any]:
    del status
    return {
        "State": {"ExitCode": exit_code, "StartedAt": "2026-01-01T00:00:00Z"},
        "RestartCount": 0,
    }
