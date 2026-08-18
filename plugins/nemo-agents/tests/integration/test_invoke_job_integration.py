# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest
from nemo_agents_plugin.jobs.invoke import AgentInvocationJob
from nemo_agents_plugin.service import AgentsService
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import PlatformJobResults
from nmp.core.files.service import FilesService
from nmp.core.jobs.service import JobsService
from nmp.platform_runner.plugin_adapter import NemoServiceAdapter
from nmp.testing import ClientContext, create_test_client

pytestmark = pytest.mark.integration


class _TestAgentsService(NemoServiceAdapter):
    def __init__(self) -> None:
        super().__init__(AgentsService())


def _extract_tar_members(content: bytes, target_dir: Path) -> dict[str, str]:
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
        tar.extractall(target_dir, filter="data")

    files: dict[str, str] = {}
    for path in target_dir.rglob("*"):
        if path.is_file():
            relative = path.relative_to(target_dir)
            files[relative.as_posix()] = path.read_text()
    return files


def test_invoke_job_materializes_layered_input_workspace(tmp_path: Path) -> None:
    with create_test_client(
        _TestAgentsService,
        FilesService,
        JobsService,
        client_type=ClientContext,
        workspace="default",
    ) as ctx:
        # Create an Agent through the public Agents API so the job's to_spec
        # resolution path sees the same entity shape as a real caller.
        agent_response = ctx.test_client.post(
            "/apis/agents/v2/workspaces/default/agents",
            json={"name": "calc", "config": {}},
        )
        assert agent_response.status_code == 201, agent_response.text

        ctx.sdk.files.upload_content(
            workspace="default",
            fileset="base-workdir",
            remote_path="README.md",
            content="base readme\n",
            fileset_auto_create=True,
        )
        ctx.sdk.files.upload_content(
            workspace="default",
            fileset="base-workdir",
            remote_path="app/config.yaml",
            content="source: base\n",
        )
        ctx.sdk.files.upload_content(
            workspace="default",
            fileset="config-artifact",
            remote_path="config.yaml",
            content="source: artifact\n",
            fileset_auto_create=True,
        )
        ctx.sdk.files.upload_content(
            workspace="default",
            fileset="notes-artifact",
            remote_path="notes.txt",
            content="mounted notes\n",
            fileset_auto_create=True,
        )

        job_name = "invoke-layered-workdir"
        create_response = ctx.test_client.post(
            "/apis/agents/v2/workspaces/default/jobs/invoke",
            json={
                "name": job_name,
                "spec": {
                    "agent": "calc",
                    "input": "hello",
                    "workdir": {
                        "base_workdir": "base-workdir",
                        "artifact_mounts": [
                            {"ref": "config-artifact#config.yaml", "mount_path": "app/config.yaml"},
                            {"ref": "notes-artifact#notes.txt", "mount_path": "notes/notes.txt"},
                        ],
                    },
                },
            },
        )
        assert create_response.status_code == 201, create_response.text
        job = create_response.json()
        assert job["name"] == job_name
        assert job["spec"]["workdir"]["base_workdir"] == "default/base-workdir#"
        assert job["spec"]["workdir"]["artifact_mounts"] == [
            {"ref": "default/config-artifact#config.yaml", "mount_path": "app/config.yaml"},
            {"ref": "default/notes-artifact#notes.txt", "mount_path": "notes/notes.txt"},
        ]

        storage_root = tmp_path / "job-storage"
        ephemeral = storage_root / "ephemeral"
        persistent = storage_root / "persistent"
        ephemeral.mkdir(parents=True)
        persistent.mkdir(parents=True)
        job_ctx = JobContext(
            workspace="default",
            storage=StoragePaths(ephemeral=ephemeral, persistent=persistent),
            results=PlatformJobResults(job_name=job_name, workspace="default", sdk=ctx.sdk),
            job_id=job["id"],
        )

        result = AgentInvocationJob().run(job["spec"], ctx=job_ctx, sdk=ctx.sdk)
        assert result["status"] == "completed"
        assert result["input_workdir"]["name"] == "input_workdir"

        results_response = ctx.test_client.get(f"/apis/agents/v2/workspaces/default/jobs/invoke/{job_name}/results")
        assert results_response.status_code == 200, results_response.text
        assert [item["name"] for item in results_response.json()["data"]] == ["input_workdir"]

        result_response = ctx.test_client.get(
            f"/apis/agents/v2/workspaces/default/jobs/invoke/{job_name}/results/input_workdir"
        )
        assert result_response.status_code == 200, result_response.text
        assert result_response.json()["name"] == "input_workdir"

        download_response = ctx.test_client.get(
            f"/apis/agents/v2/workspaces/default/jobs/invoke/{job_name}/results/input_workdir/download"
        )
        assert download_response.status_code == 200, download_response.text
        files = _extract_tar_members(download_response.content, tmp_path / "downloaded-input-workdir")

        assert any(path.endswith("README.md") and content == "base readme\n" for path, content in files.items())
        assert any(
            path.endswith("app/config.yaml") and content == "source: artifact\n" for path, content in files.items()
        )
        assert any(path.endswith("notes/notes.txt") and content == "mounted notes\n" for path, content in files.items())
        assert "source: base\n" not in files.values()
