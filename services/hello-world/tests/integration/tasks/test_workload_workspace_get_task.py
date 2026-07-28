# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
import respx
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.client.constants import WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR
from nmp.common.config import Configuration, PlatformConfig
from nmp.common.jobs.constants import TASK_CONFIG_ENVVAR
from nmp.hello_world.tasks.workload_workspace_get.run import run as task_run


@pytest.fixture(autouse=True)
def clear_config_cache():
    Configuration.clear_cache()
    try:
        yield
    finally:
        Configuration.clear_cache()


@pytest.fixture
def platform_base_url():
    base_url = "http://nmp.example.test"
    Configuration.set_override(PlatformConfig(base_url=base_url))
    try:
        yield base_url
    finally:
        Configuration.clear_override(PlatformConfig)


class _StubWorkspaces:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def retrieve(self, workspace: str) -> SimpleNamespace:
        self.requested.append(workspace)
        return SimpleNamespace(name=workspace)


class _StubSDK:
    def __init__(self) -> None:
        self.workspaces = _StubWorkspaces()


def test_workload_workspace_get_uses_task_sdk_factory(monkeypatch):
    sdk = _StubSDK()
    sdk_factory_calls: list[str] = []

    def get_task_sdk(*, as_service: str) -> NeMoPlatform:
        sdk_factory_calls.append(as_service)
        return cast(NeMoPlatform, sdk)

    monkeypatch.setenv(TASK_CONFIG_ENVVAR, '{"workspace":"workload-read-target"}')
    monkeypatch.setattr("nmp.hello_world.tasks.workload_workspace_get.run.get_task_sdk", get_task_sdk)

    exit_code = task_run()

    assert exit_code == 0
    assert sdk_factory_calls == ["jobs"]
    assert sdk.workspaces.requested == ["workload-read-target"]


def test_workload_workspace_get_uses_injected_sdk_without_workload_token(monkeypatch):
    sdk = _StubSDK()
    monkeypatch.setenv(TASK_CONFIG_ENVVAR, '{"workspace":"workload-read-target"}')
    monkeypatch.delenv(WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR, raising=False)
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN", raising=False)
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN_FILE", raising=False)

    exit_code = task_run(sdk=cast(NeMoPlatform, sdk))

    assert exit_code == 0
    assert sdk.workspaces.requested == ["workload-read-target"]


@respx.mock
def test_workload_workspace_get_uses_task_sdk_without_workload_token(monkeypatch, tmp_path, platform_base_url):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("{}\n", encoding="utf-8")

    monkeypatch.setenv(TASK_CONFIG_ENVVAR, '{"workspace":"workload-read-target"}')
    monkeypatch.setenv("NMP_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("NMP_BASE_URL", platform_base_url)
    monkeypatch.setenv(
        "NMP_PRINCIPAL",
        json.dumps(
            {
                "id": "creator@example.com",
                "email": "creator@example.com",
                "groups": ["engineering"],
            }
        ),
    )
    monkeypatch.delenv(WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR, raising=False)
    monkeypatch.delenv("NMP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN", raising=False)
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN_FILE", raising=False)

    def workspace_response(request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-NMP-Principal-Id") != "service:jobs":
            return httpx.Response(401, json={"detail": "Unauthorized"})
        if request.headers.get("X-NMP-Principal-On-Behalf-Of") != "creator@example.com":
            return httpx.Response(403, json={"detail": "Forbidden"})
        if request.headers.get("Authorization") == "Bearer service:jobs":
            return httpx.Response(401, json={"detail": "Unauthorized"})
        return httpx.Response(
            200,
            json={
                "id": "workspace-id",
                "name": "workload-read-target",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )

    workspace_route = respx.get(f"{platform_base_url}/apis/entities/v2/workspaces/workload-read-target").mock(
        side_effect=workspace_response
    )

    exit_code = task_run()

    assert exit_code == 0
    assert workspace_route.called
