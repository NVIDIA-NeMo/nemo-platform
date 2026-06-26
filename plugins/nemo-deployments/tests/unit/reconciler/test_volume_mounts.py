# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from helpers import make_deployment_config, make_volume
from nemo_deployments_plugin.entities import Container, VolumeMount
from nemo_deployments_plugin.reconciler.volume_mounts import collect_volume_mount_names, volume_mounts_ready


def test_collect_volume_mount_names_from_config_and_containers() -> None:
    cfg = make_deployment_config()
    cfg.volume_mounts = [VolumeMount(name="data", mountPath="/data")]
    cfg.containers = [
        Container(
            name="main",
            image="nginx",
            volumeMounts=[VolumeMount(name="cache", mountPath="/cache")],
        )
    ]
    assert collect_volume_mount_names(cfg) == {"cache", "data"}


def test_volume_mounts_ready_when_all_bound() -> None:
    cfg = make_deployment_config()
    cfg.volume_mounts = [VolumeMount(name="data", mountPath="/data")]
    vol = make_volume("data")
    vol.status = "BOUND"
    result = volume_mounts_ready(cfg, "default", {("default", "data"): vol})
    assert result.ready is True


def test_volume_mounts_wait_when_pending() -> None:
    cfg = make_deployment_config()
    cfg.volume_mounts = [VolumeMount(name="data", mountPath="/data")]
    vol = make_volume("data")
    result = volume_mounts_ready(cfg, "default", {("default", "data"): vol})
    assert result.ready is False
    assert "BOUND" in result.reason
