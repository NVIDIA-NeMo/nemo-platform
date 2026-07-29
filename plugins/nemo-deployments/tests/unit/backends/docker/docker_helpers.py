# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Test helpers for docker backend unit tests."""

from __future__ import annotations

from typing import Any

from nemo_deployments_plugin.entities import Container, ContainerPort, DeploymentConfig, VolumeMount
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
        restart_policy=restart_policy,  # ty: ignore[unknown-argument]
    )


def published_port_config(*, restart_policy: RestartPolicy = "Always") -> DeploymentConfig:
    """Single-container config that publishes a host port."""
    return DeploymentConfig(
        name="cfg1",
        workspace="default",
        containers=[
            Container(
                name="main",
                image="alpine:latest",
                ports=[ContainerPort(name="http", containerPort=8000)],
            )
        ],
        restart_policy=restart_policy,  # ty: ignore[unknown-argument]
    )


def lora_config(*, restart_policy: RestartPolicy = "Always") -> DeploymentConfig:
    """A LoRA-shaped multi-container config: init + server + adapters sidecar.

    Mirrors what the models compiler emits for docker + LoRA (server publishes
    :8000, adapters sidecar shares the server netns and the scratch volume).
    """
    return DeploymentConfig(
        name="cfg1",
        workspace="default",
        initContainers=[
            Container(
                name="lora-cache-init",
                image="docker.io/library/busybox:latest",
                command=["sh", "-c", "mkdir -p /scratch/loras && chmod -R 777 /scratch/loras"],
                volumeMounts=[VolumeMount(name="scratch", mountPath="/scratch")],
            )
        ],
        containers=[
            Container(
                name="server",
                image="vllm/vllm-openai:v0.22.1",
                command=["vllm", "serve"],
                args=["/model-store"],
                ports=[ContainerPort(name="http", containerPort=8000)],
                volumeMounts=[
                    VolumeMount(name="weights", mountPath="/model-store", readOnly=True),
                    VolumeMount(name="scratch", mountPath="/scratch"),
                ],
            ),
            Container(
                name="lora-adapters",
                image="my-registry/nmp-api:local",
                command=["nemo", "services", "run", "--sidecars", "adapters"],
                volumeMounts=[
                    VolumeMount(name="weights", mountPath="/model-store", readOnly=True),
                    VolumeMount(name="scratch", mountPath="/scratch"),
                ],
            ),
        ],
        restart_policy=restart_policy,  # ty: ignore[unknown-argument]
    )


def container_attrs(*, status: str = "running", exit_code: int = 0) -> dict[str, Any]:
    del status
    return {
        "State": {"ExitCode": exit_code, "StartedAt": "2026-01-01T00:00:00Z"},
        "RestartCount": 0,
    }
