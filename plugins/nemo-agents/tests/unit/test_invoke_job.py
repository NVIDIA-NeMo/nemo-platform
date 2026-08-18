# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nemo_agents_plugin.entities import Agent
from nemo_agents_plugin.fabric.runtime import FabricRuntimeResult
from nemo_agents_plugin.jobs.invoke import (
    FABRIC_ERROR_RESULT_NAME,
    FABRIC_RUN_RESULT_NAME,
    INPUT_WORKDIR_RESULT_NAME,
    OUTPUT_ARTIFACTS_RESULT_NAME,
    OUTPUT_WORKDIR_RESULT_NAME,
    AgentInvocationJob,
    AgentInvocationJobConfig,
    AgentInvocationStepConfig,
    ResolvedAgentConfig,
)
from nemo_agents_plugin.tasks.invoke.workdir import (
    AgentWorkdir,
    AgentWorkdirArtifactMount,
    _canonical_files_ref,
    materialize_agent_workdir,
    validate_agent_workdir,
)
from nemo_platform_plugin.dependencies import get_entity_client, get_sdk_client
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.routes import add_job_routes


def _agent_config(**environment: str) -> dict[str, Any]:
    config = {
        "config_format": "nemo-agents-spec-v1",
        "name": "calc",
        "default_harness": "hermes",
        "harnesses": {"hermes": {"kind": "hermes"}},
        "models": {"default": {"provider": "openai", "model": "openai/gpt-5.4"}},
    }
    if environment:
        config["environment"] = environment
    return config


def _agent(name: str = "calc", workspace: str = "default", config_format: str = "nemo-agents-spec-v1") -> Agent:
    config = _agent_config() if config_format == "nemo-agents-spec-v1" else {"workflow": {}}
    return Agent(name=name, workspace=workspace, config=config, config_format=config_format)


def _sdk_with_files(data: list[object] | None = None) -> MagicMock:
    sdk = MagicMock()
    sdk.files.list = AsyncMock(return_value=SimpleNamespace(data=data if data is not None else [object()]))
    return sdk


def _resolved_agent(name: str = "calc", workspace: str = "default") -> ResolvedAgentConfig:
    return ResolvedAgentConfig(
        name=name,
        workspace=workspace,
        config=_agent_config(),
        config_format="nemo-agents-spec-v1",
    )


@pytest.mark.asyncio
async def test_to_spec_resolves_bare_agent_against_route_workspace() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _agent()

    spec = await AgentInvocationJob.to_spec(
        AgentInvocationJobConfig(agent="calc", input="hello"),
        workspace="default",
        entity_client=entity_client,
        async_sdk=_sdk_with_files(),
        is_local=False,
    )

    step_config = AgentInvocationStepConfig.model_validate(spec)
    assert step_config.agent.name == "calc"
    assert step_config.agent.workspace == "default"
    assert step_config.request.input == "hello"
    assert step_config.workdir is None
    assert (
        step_config.agent.config["models"]["default"]["base_url"]
        == "http://localhost:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1"
    )
    entity_client.get.assert_awaited_once_with(Agent, name="calc", workspace="default")


@pytest.mark.asyncio
async def test_to_spec_preserves_explicit_agent_workspace() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _agent(workspace="research")

    await AgentInvocationJob.to_spec(
        AgentInvocationJobConfig(agent="research/calc", input="hello"),
        workspace="default",
        entity_client=entity_client,
        async_sdk=_sdk_with_files(),
        is_local=False,
    )

    entity_client.get.assert_awaited_once_with(Agent, name="calc", workspace="research")


@pytest.mark.asyncio
async def test_to_spec_rejects_missing_agent() -> None:
    entity_client = AsyncMock()
    entity_client.get.side_effect = NemoEntityNotFoundError("missing")

    with pytest.raises(ValueError, match="Agent 'missing' not found"):
        await AgentInvocationJob.to_spec(
            AgentInvocationJobConfig(agent="missing", input="hello"),
            workspace="default",
            entity_client=entity_client,
            async_sdk=_sdk_with_files(),
            is_local=False,
        )


@pytest.mark.asyncio
async def test_to_spec_rejects_non_fabric_agent() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _agent(config_format="nat-workflow-v1")

    with pytest.raises(ValueError, match="only support 'nemo-agents-spec-v1'"):
        await AgentInvocationJob.to_spec(
            AgentInvocationJobConfig(agent="calc", input="hello"),
            workspace="default",
            entity_client=entity_client,
            async_sdk=_sdk_with_files(),
            is_local=False,
        )


@pytest.mark.asyncio
async def test_to_spec_rejects_malformed_fabric_agent_config() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = Agent(
        name="calc",
        workspace="default",
        config={"config_format": "nemo-agents-spec-v1", "name": "calc"},
        config_format="nemo-agents-spec-v1",
    )

    with pytest.raises(ValueError, match="default_harness"):
        await AgentInvocationJob.to_spec(
            AgentInvocationJobConfig(agent="calc", input="hello"),
            workspace="default",
            entity_client=entity_client,
            async_sdk=_sdk_with_files(),
            is_local=False,
        )


@pytest.mark.asyncio
async def test_to_spec_rejects_non_local_fabric_environment() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = Agent(
        name="calc",
        workspace="default",
        config=_agent_config(provider="docker"),
        config_format="nemo-agents-spec-v1",
    )

    with pytest.raises(ValueError, match="only support local Fabric environments"):
        await AgentInvocationJob.to_spec(
            AgentInvocationJobConfig(agent="calc", input="hello"),
            workspace="default",
            entity_client=entity_client,
            async_sdk=_sdk_with_files(),
            is_local=False,
        )


@pytest.mark.asyncio
async def test_to_spec_validates_and_canonicalizes_base_workdir() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _agent()
    sdk = _sdk_with_files()

    spec = await AgentInvocationJob.to_spec(
        AgentInvocationJobConfig(agent="calc", input="hello", workdir=AgentWorkdir(base_workdir="source#project")),
        workspace="default",
        entity_client=entity_client,
        async_sdk=sdk,
        is_local=False,
    )

    step_config = AgentInvocationStepConfig.model_validate(spec)
    assert step_config.workdir is not None
    assert step_config.workdir.base_workdir == "default/source#project/"
    sdk.files.list.assert_awaited_once_with(remote_path="default/source#project/")


@pytest.mark.asyncio
async def test_to_spec_rejects_single_file_base_workdir() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _agent()

    with pytest.raises(ValueError, match="non-empty directory"):
        await AgentInvocationJob.to_spec(
            AgentInvocationJobConfig(
                agent="calc", input="hello", workdir=AgentWorkdir(base_workdir="source#README.md")
            ),
            workspace="default",
            entity_client=entity_client,
            async_sdk=_sdk_with_files(data=[]),
            is_local=False,
        )


def test_canonical_base_workdir_ref_rejects_path_escape() -> None:
    with pytest.raises(ValueError, match="path escapes"):
        _canonical_files_ref(
            "source#../secret",
            default_workspace="default",
            field="workdir.base_workdir",
            directory_like=True,
        )


def test_canonical_base_workdir_ref_rejects_legacy_path_shape() -> None:
    with pytest.raises(ValueError, match="before fileset paths"):
        _canonical_files_ref(
            "default/source/project",
            default_workspace="default",
            field="workdir.base_workdir",
            directory_like=True,
        )


def test_canonical_base_workdir_root_ref_keeps_fileset_delimiter() -> None:
    assert (
        _canonical_files_ref(
            "source",
            default_workspace="default",
            field="workdir.base_workdir",
            directory_like=True,
        )
        == "default/source#"
    )


@pytest.mark.parametrize("mount_path", ["../secret", "data/../../secret", "/abs/path", "", ".", "data\\file"])
def test_workdir_artifact_mount_rejects_escaping_mount_paths(mount_path: str) -> None:
    with pytest.raises(ValueError):
        AgentWorkdirArtifactMount(ref="source#artifact", mount_path=mount_path)


def test_workdir_artifact_mount_normalizes_relative_mount_path() -> None:
    mount = AgentWorkdirArtifactMount(ref="source#artifact", mount_path="data/output/")
    assert mount.mount_path == "data/output"


@pytest.mark.parametrize(
    ("left", "right"),
    [("data", "data"), ("data", "data/file.txt"), ("data/project", "data/project/subdir")],
)
def test_workdir_spec_rejects_overlapping_mount_paths(left: str, right: str) -> None:
    with pytest.raises(ValueError, match="overlapping mount paths"):
        AgentWorkdir(
            artifact_mounts=[
                AgentWorkdirArtifactMount(ref="source#a", mount_path=left),
                AgentWorkdirArtifactMount(ref="source#b", mount_path=right),
            ]
        )


def test_workdir_spec_allows_sibling_mount_paths() -> None:
    spec = AgentWorkdir(
        artifact_mounts=[
            AgentWorkdirArtifactMount(ref="source#a", mount_path="data/a"),
            AgentWorkdirArtifactMount(ref="source#b", mount_path="data/b"),
        ]
    )
    assert [mount.mount_path for mount in spec.artifact_mounts] == ["data/a", "data/b"]


@pytest.mark.asyncio
async def test_validate_agent_workdir_canonicalizes_refs() -> None:
    files_client = MagicMock()
    files_client.list = AsyncMock(return_value=SimpleNamespace(data=[object()]))

    spec = await validate_agent_workdir(
        AgentWorkdir(
            base_workdir="source#project",
            artifact_mounts=[AgentWorkdirArtifactMount(ref="artifacts#notes.txt", mount_path="notes.txt")],
        ),
        files_client,
        default_workspace="default",
    )

    assert spec is not None
    assert spec.base_workdir == "default/source#project/"
    assert spec.artifact_mounts == [
        AgentWorkdirArtifactMount(ref="default/artifacts#notes.txt", mount_path="notes.txt")
    ]
    files_client.list.assert_has_awaits(
        [call(remote_path="default/source#project/"), call(remote_path="default/artifacts#notes.txt")]
    )


def test_materialize_agent_workdir_downloads_base_and_mounts(tmp_path: Path) -> None:
    files_client = MagicMock()
    calls: list[tuple[str, str]] = []

    def _download(*, remote_path: str, local_path: str) -> None:
        calls.append((remote_path, local_path))
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        if remote_path == "default/source#project/":
            local.mkdir(parents=True, exist_ok=True)
            (local / "config.yaml").write_text("name: calc\n")
        else:
            local.write_text("mounted artifact\n")

    files_client.download.side_effect = _download
    target = tmp_path / "workdir"

    materialize_agent_workdir(
        AgentWorkdir(
            base_workdir="default/source#project/",
            artifact_mounts=[AgentWorkdirArtifactMount(ref="default/artifacts#notes.txt", mount_path="notes.txt")],
        ),
        files_client,
        target,
    )

    assert calls == [
        ("default/source#project/", str(target)),
        ("default/artifacts#notes.txt", str(target / "notes.txt")),
    ]
    assert (target / "config.yaml").read_text() == "name: calc\n"
    assert (target / "notes.txt").read_text() == "mounted artifact\n"


def test_materialize_agent_workdir_replaces_base_directory_for_directory_mount(tmp_path: Path) -> None:
    files_client = MagicMock()
    calls: list[tuple[str, str]] = []

    def _download(*, remote_path: str, local_path: str) -> None:
        calls.append((remote_path, local_path))
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        if remote_path == "default/source#project/":
            (local / "data").mkdir(parents=True)
            (local / "data" / "stale.txt").write_text("stale\n")
        else:
            if local.is_dir():
                raise IsADirectoryError(local)
            local.mkdir(parents=True)
            (local / "mounted.txt").write_text("mounted artifact\n")

    files_client.download.side_effect = _download
    target = tmp_path / "workdir"

    materialize_agent_workdir(
        AgentWorkdir(
            base_workdir="default/source#project/",
            artifact_mounts=[AgentWorkdirArtifactMount(ref="default/artifacts#data/", mount_path="data")],
        ),
        files_client,
        target,
    )

    assert calls == [
        ("default/source#project/", str(target)),
        ("default/artifacts#data/", str(target / "data")),
    ]
    assert not (target / "data" / "stale.txt").exists()
    assert (target / "data" / "mounted.txt").read_text() == "mounted artifact\n"


@pytest.mark.asyncio
async def test_compile_produces_single_cpu_step_with_canonical_config() -> None:
    spec = AgentInvocationStepConfig(
        request=AgentInvocationJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
        workdir=AgentWorkdir(base_workdir="default/source#project/"),
    )

    platform_spec = await AgentInvocationJob.compile(
        workspace="default",
        spec=spec,
        entity_client=MagicMock(),
        job_name=None,
        async_sdk=MagicMock(),
    )

    steps = list(platform_spec["steps"])
    assert len(steps) == 1
    step = steps[0]
    assert step["name"] == "invoke-agent"
    assert step["executor"]["provider"] == "cpu"
    assert step["executor"]["container"]["command"] == ["nemo_agents_plugin.tasks.invoke"]
    assert step["config"] == spec.model_dump(mode="json")
    step_config = cast(dict[str, Any], step["config"])
    assert cast(dict[str, Any], step_config["request"])["input"] == "hello"
    assert step["environment"] == []


def test_run_without_input_workdir_saves_empty_input_snapshot(ctx: JobContext) -> None:
    spec = AgentInvocationStepConfig(
        request=AgentInvocationJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )

    async def _invoke(request: Any) -> FabricRuntimeResult:
        assert request.input == "hello"
        assert request.base_dir == ctx.storage.ephemeral / "fabric"
        (request.base_dir / "workspace" / "answer.txt").write_text("done\n")
        (request.base_dir / "artifacts" / "trace.json").write_text("{}\n")
        return FabricRuntimeResult(
            status="succeeded",
            response="done",
            metadata={"adapter_runner": "python"},
            runtime_id="runtime-1",
            invocation_id="invocation-1",
            request_id="request-1",
        )

    with patch("nemo_agents_plugin.jobs.invoke.invoke_agent_config_request_once", _invoke):
        result = AgentInvocationJob().run(spec.model_dump(mode="json"), ctx=ctx)

    assert result["status"] == "completed"
    assert result["fabric_status"] == "succeeded"
    assert result["input_workdir"]["name"] == INPUT_WORKDIR_RESULT_NAME
    assert result["output_workdir"]["name"] == OUTPUT_WORKDIR_RESULT_NAME
    assert result["output_artifacts"]["name"] == OUTPUT_ARTIFACTS_RESULT_NAME
    assert result["fabric_run_result"]["name"] == FABRIC_RUN_RESULT_NAME
    assert list((ctx.storage.persistent / "results" / INPUT_WORKDIR_RESULT_NAME).iterdir()) == []
    assert (ctx.storage.persistent / "results" / OUTPUT_WORKDIR_RESULT_NAME / "answer.txt").read_text() == "done\n"
    assert (ctx.storage.persistent / "results" / OUTPUT_ARTIFACTS_RESULT_NAME / "trace.json").read_text() == "{}\n"
    payload = json.loads((ctx.storage.persistent / "results" / FABRIC_RUN_RESULT_NAME).read_text())
    assert payload["metadata"] == {"adapter_runner": "python"}
    assert payload["runtime_id"] == "runtime-1"


def test_run_rejects_non_fabric_step_config(ctx: JobContext) -> None:
    spec = AgentInvocationStepConfig(
        request=AgentInvocationJobConfig(agent="calc", input="hello"),
        agent=ResolvedAgentConfig(
            name="calc",
            workspace="default",
            config={"workflow": {}},
            config_format="nat-workflow-v1",
        ),
    )

    with pytest.raises(ValueError, match="only support 'nemo-agents-spec-v1'"):
        AgentInvocationJob().run(spec.model_dump(mode="json"), ctx=ctx)


def test_run_downloads_and_registers_input_workdir(ctx: JobContext) -> None:
    spec = AgentInvocationStepConfig(
        request=AgentInvocationJobConfig(
            agent="calc",
            input="hello",
            workdir=AgentWorkdir(base_workdir="source#project/"),
        ),
        agent=_resolved_agent(),
        workdir=AgentWorkdir(
            base_workdir="default/source#project/",
            artifact_mounts=[AgentWorkdirArtifactMount(ref="default/artifacts#notes.txt", mount_path="notes.txt")],
        ),
    )
    sdk = MagicMock()
    download_calls: list[tuple[str, str]] = []

    def _download(*, remote_path: str, local_path: str) -> None:
        download_calls.append((remote_path, local_path))
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        if remote_path == "default/source#project/":
            local.mkdir(parents=True, exist_ok=True)
            Path(local_path, "config.yaml").write_text("name: calc\n")
        else:
            local.write_text("mounted artifact\n")

    sdk.files.download.side_effect = _download

    async def _invoke(request: Any) -> FabricRuntimeResult:
        (request.base_dir / "workspace" / "answer.txt").write_text("done\n")
        (request.base_dir / "artifacts" / "artifact.txt").write_text("artifact\n")
        return FabricRuntimeResult(status="succeeded", response="done")

    with patch("nemo_agents_plugin.jobs.invoke.invoke_agent_config_request_once", _invoke):
        result = AgentInvocationJob().run(spec.model_dump(mode="json"), ctx=ctx, sdk=sdk)

    assert result["status"] == "completed"
    assert result["input_workdir"]["name"] == "input_workdir"
    assert [remote_path for remote_path, _ in download_calls] == [
        "default/source#project/",
        "default/artifacts#notes.txt",
    ]
    assert (ctx.storage.persistent / "results" / "input_workdir" / "config.yaml").read_text() == "name: calc\n"
    assert (ctx.storage.persistent / "results" / "input_workdir" / "notes.txt").read_text() == "mounted artifact\n"
    assert (ctx.storage.persistent / "results" / "output_workdir" / "answer.txt").read_text() == "done\n"
    assert (ctx.storage.persistent / "results" / "output_artifacts" / "artifact.txt").read_text() == "artifact\n"


def test_run_clears_stale_input_workdir_before_materializing(ctx: JobContext) -> None:
    spec = AgentInvocationStepConfig(
        request=AgentInvocationJobConfig(
            agent="calc",
            input="hello",
            workdir=AgentWorkdir(base_workdir="source#project/"),
        ),
        agent=_resolved_agent(),
        workdir=AgentWorkdir(base_workdir="default/source#project/"),
    )
    stale_workdir = ctx.storage.ephemeral / "fabric" / "workspace"
    stale_workdir.mkdir(parents=True)
    (stale_workdir / "stale.txt").write_text("stale\n")
    sdk = MagicMock()

    def _download(*, remote_path: str, local_path: str) -> None:
        assert remote_path == "default/source#project/"
        local = Path(local_path)
        assert not (local / "stale.txt").exists()
        local.mkdir(parents=True, exist_ok=True)
        (local / "config.yaml").write_text("name: calc\n")

    sdk.files.download.side_effect = _download

    async def _invoke(request: Any) -> FabricRuntimeResult:
        return FabricRuntimeResult(status="succeeded")

    with patch("nemo_agents_plugin.jobs.invoke.invoke_agent_config_request_once", _invoke):
        result = AgentInvocationJob().run(spec.model_dump(mode="json"), ctx=ctx, sdk=sdk)

    assert result["status"] == "completed"
    assert result["input_workdir"]["name"] == "input_workdir"
    saved_workdir = ctx.storage.persistent / "results" / "input_workdir"
    assert not (saved_workdir / "stale.txt").exists()
    assert (saved_workdir / "config.yaml").read_text() == "name: calc\n"


def test_run_clears_stale_artifacts_dir_before_invoking(ctx: JobContext) -> None:
    spec = AgentInvocationStepConfig(
        request=AgentInvocationJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )
    stale_artifacts = ctx.storage.ephemeral / "fabric" / "artifacts"
    stale_artifacts.mkdir(parents=True)
    (stale_artifacts / "stale.txt").write_text("stale\n")

    async def _invoke(request: Any) -> FabricRuntimeResult:
        assert not (request.base_dir / "artifacts" / "stale.txt").exists()
        (request.base_dir / "artifacts" / "fresh.txt").write_text("fresh\n")
        return FabricRuntimeResult(status="succeeded")

    with patch("nemo_agents_plugin.jobs.invoke.invoke_agent_config_request_once", _invoke):
        result = AgentInvocationJob().run(spec.model_dump(mode="json"), ctx=ctx)

    assert result["status"] == "completed"
    saved_artifacts = ctx.storage.persistent / "results" / "output_artifacts"
    assert not (saved_artifacts / "stale.txt").exists()
    assert (saved_artifacts / "fresh.txt").read_text() == "fresh\n"


def test_run_failed_download_does_not_register_partial_result(ctx: JobContext) -> None:
    spec = AgentInvocationStepConfig(
        request=AgentInvocationJobConfig(
            agent="calc",
            input="hello",
            workdir=AgentWorkdir(base_workdir="source#project/"),
        ),
        agent=_resolved_agent(),
        workdir=AgentWorkdir(base_workdir="default/source#project/"),
    )
    sdk = MagicMock()
    sdk.files.download.side_effect = RuntimeError("download failed")

    with pytest.raises(RuntimeError, match="download failed"):
        AgentInvocationJob().run(spec.model_dump(mode="json"), ctx=ctx, sdk=sdk)

    assert not (ctx.storage.persistent / "results" / "input_workdir").exists()


def test_run_failed_fabric_result_saves_results_and_marks_job_failed(ctx: JobContext) -> None:
    spec = AgentInvocationStepConfig(
        request=AgentInvocationJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )

    async def _invoke(request: Any) -> FabricRuntimeResult:
        (request.base_dir / "workspace" / "partial.txt").write_text("partial\n")
        return FabricRuntimeResult(
            status="failed",
            error={"stage": "invoke", "message": "adapter failed"},
        )

    with patch("nemo_agents_plugin.jobs.invoke.invoke_agent_config_request_once", _invoke):
        result = AgentInvocationJob().run(spec.model_dump(mode="json"), ctx=ctx)

    assert result["status"] == "failed"
    assert result["fabric_status"] == "failed"
    assert (ctx.storage.persistent / "results" / OUTPUT_WORKDIR_RESULT_NAME / "partial.txt").read_text() == "partial\n"
    payload = json.loads((ctx.storage.persistent / "results" / FABRIC_RUN_RESULT_NAME).read_text())
    assert payload["status"] == "failed"
    assert payload["error"] == {"stage": "invoke", "message": "adapter failed"}
    assert not (ctx.storage.persistent / "results" / FABRIC_ERROR_RESULT_NAME).exists()


def test_run_fabric_exception_saves_best_effort_error_results(ctx: JobContext) -> None:
    spec = AgentInvocationStepConfig(
        request=AgentInvocationJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )

    async def _invoke(request: Any) -> FabricRuntimeResult:
        (request.base_dir / "workspace" / "partial.txt").write_text("partial\n")
        raise RuntimeError("fabric exploded")

    with (
        patch("nemo_agents_plugin.jobs.invoke.invoke_agent_config_request_once", _invoke),
        pytest.raises(RuntimeError, match="fabric exploded"),
    ):
        AgentInvocationJob().run(spec.model_dump(mode="json"), ctx=ctx)

    assert (ctx.storage.persistent / "results" / INPUT_WORKDIR_RESULT_NAME).is_dir()
    assert (ctx.storage.persistent / "results" / OUTPUT_WORKDIR_RESULT_NAME / "partial.txt").read_text() == "partial\n"
    assert (ctx.storage.persistent / "results" / OUTPUT_ARTIFACTS_RESULT_NAME).is_dir()
    payload = json.loads((ctx.storage.persistent / "results" / FABRIC_ERROR_RESULT_NAME).read_text())
    assert payload["type"] == "RuntimeError"
    assert payload["message"] == "fabric exploded"
    assert payload["fabric_status"] == "error"


def test_run_fabric_exception_preserves_original_error_if_result_save_fails(ctx: JobContext) -> None:
    spec = AgentInvocationStepConfig(
        request=AgentInvocationJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )
    original_save = ctx.results.save

    async def _invoke(request: Any) -> FabricRuntimeResult:
        (request.base_dir / "workspace" / "partial.txt").write_text("partial\n")
        raise RuntimeError("fabric exploded")

    def _save(name: str, local_path: str | Path, **kwargs: Any) -> Any:
        if name == OUTPUT_WORKDIR_RESULT_NAME:
            raise RuntimeError("save failed")
        return original_save(name, local_path, **kwargs)

    cast(Any, ctx.results).save = _save

    with (
        patch("nemo_agents_plugin.jobs.invoke.invoke_agent_config_request_once", _invoke),
        pytest.raises(RuntimeError, match="fabric exploded"),
    ):
        AgentInvocationJob().run(spec.model_dump(mode="json"), ctx=ctx)

    assert (ctx.storage.persistent / "results" / FABRIC_ERROR_RESULT_NAME).exists()


def test_invoke_job_create_route_stores_canonical_step_config() -> None:
    app = FastAPI()
    app.include_router(add_job_routes(AgentInvocationJob), prefix="/apis/agents/v2/workspaces/{workspace}")

    entity_client = AsyncMock()
    entity_client.get.return_value = _agent()
    sdk = _sdk_with_files()
    app.dependency_overrides[get_entity_client] = lambda: entity_client
    app.dependency_overrides[get_sdk_client] = lambda: sdk

    captured_body: dict[str, Any] = {}

    async def _create_job(*, workspace: str, body: object) -> MagicMock:
        del workspace
        typed_body = cast(Any, body)
        captured_body["body"] = body
        response = MagicMock()
        response.data.return_value = SimpleNamespace(
            id="job-1",
            name="invoke-1",
            description=None,
            workspace="default",
            created_at=None,
            updated_at=None,
            spec=typed_body.spec,
            status="created",
            status_details=None,
            error_details=None,
            ownership=None,
            custom_fields=None,
        )
        return response

    fake_jobs = SimpleNamespace(create_job=_create_job)
    with patch("nemo_platform_plugin.jobs.api_factory.client_from_platform", return_value=fake_jobs):
        response = TestClient(app).post(
            "/apis/agents/v2/workspaces/default/jobs/invoke",
            json={
                "name": "invoke-1",
                "spec": {"agent": "calc", "input": "hello", "workdir": {"base_workdir": "source#project"}},
            },
        )

    assert response.status_code == 201, response.text
    body = captured_body["body"]
    assert body.source == "nemo-agents-plugin"
    assert body.spec["agent"]["name"] == "calc"
    assert body.spec["agent"]["workspace"] == "default"
    assert body.spec["agent"]["config_format"] == "nemo-agents-spec-v1"
    assert body.spec["agent"]["config"]["environment"] == {
        "provider": "local",
        "workspace": "./workspace",
        "artifacts": "./artifacts",
        "settings": {},
    }
    assert (
        body.spec["agent"]["config"]["models"]["default"]["base_url"]
        == "http://localhost:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1"
    )
    assert body.spec["request"] == {
        "agent": "calc",
        "input": "hello",
        "workdir": {"base_workdir": "source#project", "artifact_mounts": []},
    }
    assert body.spec["workdir"] == {"base_workdir": "default/source#project/", "artifact_mounts": []}
    assert body.platform_spec.steps[0].name == "invoke-agent"
    assert response.json()["spec"]["workdir"]["base_workdir"] == "default/source#project/"
