# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for auth-proxy sidecar compilation in the deployments plugin."""

from __future__ import annotations

from unittest.mock import patch

from nemo_deployments_plugin.auth_proxy import AUTH_PROXY_CONTAINER_NAME, build_auth_proxy_container
from nemo_deployments_plugin.entities import DeploymentConfig

_MOD = "nemo_deployments_plugin.auth_proxy"


def _config(**kwargs) -> DeploymentConfig:
    return DeploymentConfig(name="dep", workspace="default", **kwargs)


def test_no_sidecar_when_not_requested() -> None:
    with patch(f"{_MOD}.platform_auth_enabled", return_value=True):
        assert build_auth_proxy_container(_config(auth_proxy_sidecar=False)) is None


def test_no_sidecar_when_auth_disabled() -> None:
    # Requested but auth off -> no-op.
    with patch(f"{_MOD}.platform_auth_enabled", return_value=False):
        assert (
            build_auth_proxy_container(_config(auth_proxy_sidecar=True, auth_proxy_sidecar_identity="agents")) is None
        )


def test_builds_sidecar_when_requested_and_auth_on() -> None:
    with (
        patch(f"{_MOD}.platform_auth_enabled", return_value=True),
        patch(f"{_MOD}.get_qualified_image", return_value="my-registry/nmp-api:local"),
        patch(f"{_MOD}._upstream_base_url", return_value="http://nemo-platform-api:8080"),
    ):
        container = build_auth_proxy_container(_config(auth_proxy_sidecar=True, auth_proxy_sidecar_identity="agents"))
    assert container is not None
    assert container.name == AUTH_PROXY_CONTAINER_NAME
    assert container.image == "my-registry/nmp-api:local"
    assert container.command == ["nemo", "services", "run", "--sidecars", "auth-proxy"]
    assert container.restart_policy == "Always"
    env = {e.name: e.value for e in container.env}
    assert env["NMP_AUTH_PROXY_PRINCIPAL"] == "agents"
    assert env["NMP_BASE_URL"] == "http://nemo-platform-api:8080"
    # Loopback exec probe (proxy binds 127.0.0.1, so pod-IP httpGet would be refused).
    assert container.readiness_probe is not None
    assert container.readiness_probe.exec_action is not None
    assert "127.0.0.1" in " ".join(container.readiness_probe.exec_action.command)


def test_identity_defaults_to_agents_when_unset() -> None:
    with (
        patch(f"{_MOD}.platform_auth_enabled", return_value=True),
        patch(f"{_MOD}.get_qualified_image", return_value="img"),
        patch(f"{_MOD}._upstream_base_url", return_value="http://x:8080"),
    ):
        container = build_auth_proxy_container(_config(auth_proxy_sidecar=True))
    assert container is not None
    env = {e.name: e.value for e in container.env}
    assert env["NMP_AUTH_PROXY_PRINCIPAL"] == "agents"
