# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from helpers import list_response, make_deployment, make_deployment_config
from nemo_deployments_plugin.entities import Container, VolumeMount
from nemo_deployments_plugin.references import (
    deployment_config_names_referencing_volume,
    deployment_names_using_config,
)


@pytest.mark.asyncio
async def test_deployment_names_using_config() -> None:
    client = AsyncMock()
    client.list.return_value = list_response([make_deployment("dep1")])
    names = await deployment_names_using_config(client, workspace="default", config_name="cfg1")
    assert names == ["dep1"]
    client.list.assert_awaited_once()


@pytest.mark.asyncio
async def test_deployment_config_names_referencing_volume() -> None:
    cfg = make_deployment_config("cfg1")
    cfg.volume_mounts = [VolumeMount(name="vol1", mountPath="/data")]
    client = AsyncMock()
    client.list.return_value = list_response([cfg])
    names = await deployment_config_names_referencing_volume(client, workspace="default", volume_name="vol1")
    assert names == ["cfg1"]


@pytest.mark.asyncio
async def test_deployment_config_names_referencing_volume_via_container_mount() -> None:
    cfg = make_deployment_config("cfg1")
    cfg.containers = [
        Container(
            name="main",
            image="nginx",
            volumeMounts=[VolumeMount(name="vol1", mountPath="/data")],
        )
    ]
    client = AsyncMock()
    client.list.return_value = list_response([cfg])
    names = await deployment_config_names_referencing_volume(client, workspace="default", volume_name="vol1")
    assert names == ["cfg1"]
