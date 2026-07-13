# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace

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


def test_workload_workspace_get_reads_workspace_via_public_sdk(monkeypatch):
    sdk = _StubSDK()
    sdk_kwargs = {}

    def create_sdk(**kwargs):
        sdk_kwargs.update(kwargs)
        return sdk

    monkeypatch.setenv(TASK_CONFIG_ENVVAR, '{"workspace":"workload-read-target"}')
    monkeypatch.setenv("NEMO_WORKLOAD_TOKEN", "workload-token-123")
    monkeypatch.setattr("nmp.hello_world.tasks.workload_workspace_get.run.NeMoPlatform", create_sdk)

    exit_code = task_run()

    assert exit_code == 0
    assert sdk.workspaces.requested == ["workload-read-target"]
    assert sdk_kwargs == {"default_headers": {"Authorization": "Bearer workload-token-123"}}


def test_workload_workspace_get_requires_workload_token_env(monkeypatch):
    monkeypatch.setenv(TASK_CONFIG_ENVVAR, '{"workspace":"workload-read-target"}')
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN", raising=False)
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN_FILE", raising=False)

    exit_code = task_run()

    assert exit_code == 1


def test_workload_workspace_get_uses_injected_sdk_without_workload_token(monkeypatch):
    sdk = _StubSDK()
    monkeypatch.setenv(TASK_CONFIG_ENVVAR, '{"workspace":"workload-read-target"}')
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN", raising=False)
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN_FILE", raising=False)

    exit_code = task_run(sdk=sdk)

    assert exit_code == 0
    assert sdk.workspaces.requested == ["workload-read-target"]


def test_workload_workspace_get_accepts_workload_token_file_env(monkeypatch, tmp_path):
    sdk = _StubSDK()
    sdk_kwargs = {}

    def create_sdk(**kwargs):
        sdk_kwargs.update(kwargs)
        return sdk

    token_path = tmp_path / "workload.token"
    token_path.write_text("workload-token-from-file\n", encoding="utf-8")
    monkeypatch.setenv(TASK_CONFIG_ENVVAR, '{"workspace":"workload-read-target"}')
    monkeypatch.delenv("NEMO_WORKLOAD_TOKEN", raising=False)
    monkeypatch.setenv("NEMO_WORKLOAD_TOKEN_FILE", str(token_path))
    monkeypatch.setattr("nmp.hello_world.tasks.workload_workspace_get.run.NeMoPlatform", create_sdk)

    exit_code = task_run()

    assert exit_code == 0
    assert sdk.workspaces.requested == ["workload-read-target"]
    assert sdk_kwargs == {"default_headers": {"Authorization": "Bearer workload-token-from-file"}}
