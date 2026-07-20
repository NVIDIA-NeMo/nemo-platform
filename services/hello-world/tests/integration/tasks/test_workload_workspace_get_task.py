# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from typing import cast

import httpx
import respx
from nemo_platform import NeMoPlatform
from nemo_platform.auth.helpers import NMPOIDCConfig
from nemo_platform_plugin.client.constants import WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR
from nmp.common.jobs.constants import TASK_CONFIG_ENVVAR
from nmp.hello_world.tasks.workload_workspace_get.run import run as task_run


class _StubWorkspaces:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def retrieve(self, workspace: str) -> SimpleNamespace:
        self.requested.append(workspace)
        return SimpleNamespace(name=workspace)


class _StubSDK:
    def __init__(self) -> None:
        self.workspaces = _StubWorkspaces()


@respx.mock
def test_workload_workspace_get_reads_workspace_via_public_sdk(monkeypatch, tmp_path):
    subject_token_file = tmp_path / "workload-token"
    subject_token_file.write_text("subject-token-from-file\n", encoding="utf-8")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("{}\n", encoding="utf-8")
    discovery_requests: list[str] = []
    exchange_requests: list[dict] = []

    def discover_nmp_config(base_url: str) -> NMPOIDCConfig:
        discovery_requests.append(base_url)
        return NMPOIDCConfig(
            auth_enabled=True,
            workload_token_exchange_enabled=True,
            workload_client_id="workload-client",
            workload_token_endpoint="https://idp.example.test/oauth2/token",
            workload_audience="nemo-platform",
            workload_scope="openid email groups",
        )

    def token_exchange_grant(**kwargs):
        exchange_requests.append(kwargs)
        return {"access_token": "exchanged-access-token", "expires_in": 300}

    monkeypatch.setenv(TASK_CONFIG_ENVVAR, '{"workspace":"workload-read-target"}')
    monkeypatch.setenv("NMP_CONFIG_FILE", str(config_file))
    monkeypatch.setenv(WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR, str(subject_token_file))
    monkeypatch.delenv("NMP_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr("nemo_platform.client.factory.discover_nmp_config", discover_nmp_config)
    monkeypatch.setattr("nemo_platform.auth.workload_exchange.token_exchange_grant", token_exchange_grant)

    workspace_route = respx.get("http://nmp.example.test/apis/entities/v2/workspaces/workload-read-target").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "workspace-id",
                "name": "workload-read-target",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )
    )

    sdk = NeMoPlatform(base_url="http://nmp.example.test")
    try:
        exit_code = task_run(sdk=sdk)
    finally:
        sdk.close()

    assert exit_code == 0
    assert workspace_route.called
    assert workspace_route.calls[0].request.headers["Authorization"] == "Bearer exchanged-access-token"
    assert [url.rstrip("/") for url in discovery_requests] == ["http://nmp.example.test"]
    assert exchange_requests == [
        {
            "token_endpoint": "https://idp.example.test/oauth2/token",
            "client_id": "workload-client",
            "subject_token": "subject-token-from-file",
            "audience": "nemo-platform",
            "scope": "openid email groups",
        }
    ]


def test_workload_workspace_get_uses_injected_sdk_without_workload_token(monkeypatch):
    sdk = _StubSDK()
    monkeypatch.setenv(TASK_CONFIG_ENVVAR, '{"workspace":"workload-read-target"}')
    monkeypatch.delenv(WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR, raising=False)
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN", raising=False)
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN_FILE", raising=False)

    exit_code = task_run(sdk=cast(NeMoPlatform, sdk))

    assert exit_code == 0
    assert sdk.workspaces.requested == ["workload-read-target"]
