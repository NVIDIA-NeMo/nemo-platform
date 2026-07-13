# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from nemo_deployments_plugin.entities import Deployment
from nemo_deployments_plugin.types import Endpoint
from nmp.core.models.controllers.backends.deployments_plugin.status import (
    aggregate_status,
    map_status,
    project_host_url,
)


@pytest.mark.parametrize(
    ("plugin_status", "model_status"),
    [("PENDING", "PENDING"), ("STARTING", "PENDING"), ("READY", "READY"), ("FAILED", "ERROR"), ("LOST", "LOST")],
)
def test_map_status(plugin_status: str, model_status: str) -> None:
    assert map_status(plugin_status) == model_status


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
