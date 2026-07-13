# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_deployments_plugin.entities import Deployment, Volume
from nemo_deployments_plugin.types import Endpoint
from nmp.core.models.controllers.backends.deployments_plugin.status import (
    aggregate_status,
    map_status,
    project_host_url,
)


@pytest.mark.parametrize(
    ("plugin_status", "model_status"),
    [
        ("PENDING", "PENDING"),
        ("STARTING", "PENDING"),
        ("READY", "READY"),
        ("FAILED", "ERROR"),
        ("LOST", "LOST"),
        ("UNKNOWN", "UNKNOWN"),
        ("DELETING", "DELETING"),
        ("SUCCEEDED", "PENDING"),
    ],
)
def test_map_status(plugin_status: str, model_status: str) -> None:
    assert map_status(plugin_status) == model_status


def test_map_status_defaults_to_unknown() -> None:
    assert map_status("SOMETHING_NEW") == "UNKNOWN"


def test_ready_projects_http_endpoint() -> None:
    server = Deployment(
        name="server",
        workspace="default",
        deployment_config="server",
        status="READY",
        endpoints=[Endpoint(name="http", url="https://server", protocol="https")],
    )
    assert project_host_url(server.endpoints) == "https://server"
    assert aggregate_status(None, None, server).host_url == "https://server"


def test_missing_ready_server_is_lost_and_failed_puller_is_error() -> None:
    assert aggregate_status(None, None, None, previously_ready=True).status == "LOST"
    puller = Deployment(name="puller", workspace="default", deployment_config="puller", status="FAILED")
    assert aggregate_status(None, puller, None).status == "ERROR"


def test_no_substrate_yet_is_pending() -> None:
    result = aggregate_status(None, None, None)
    assert result.status == "PENDING"


def test_failed_volume_is_error() -> None:
    volume = Volume(name="volume", workspace="default", size="1Gi", status="FAILED")
    assert aggregate_status(volume, None, None).status == "ERROR"


def test_lost_puller_is_error() -> None:
    puller = Deployment(name="puller", workspace="default", deployment_config="puller", status="LOST")
    assert aggregate_status(None, puller, None).status == "ERROR"


def test_unknown_puller_surfaces_unknown() -> None:
    puller = Deployment(name="puller", workspace="default", deployment_config="puller", status="UNKNOWN")
    assert aggregate_status(None, puller, None).status == "UNKNOWN"
