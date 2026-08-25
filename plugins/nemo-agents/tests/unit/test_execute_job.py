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
from nemo_agents_plugin.entities import (
    Agent,
    AgentComputeSpec,
    AgentEnvironment,
    AgentEnvironmentInline,
    AgentEnvironmentSpec,
    ComputeResources,
    ComputeSpecInline,
    EnvironmentSpecInline,
    McpFulfillment,
)
from nemo_agents_plugin.fabric.runtime import FabricRuntimeResult
from nemo_agents_plugin.jobs.execute import (
    DEFAULT_AGENT_EXECUTION_TIMEOUT_SECONDS,
    FABRIC_ERROR_RESULT_NAME,
    FABRIC_RUN_RESULT_NAME,
    INPUT_WORKDIR_RESULT_NAME,
    OUTPUT_ARTIFACTS_RESULT_NAME,
    OUTPUT_WORKDIR_RESULT_NAME,
    ExecuteAgentJob,
    ExecuteAgentJobConfig,
    ExecuteAgentStepConfig,
    ResolvedAgentConfig,
)
from nemo_agents_plugin.tasks.execute.workdir import (
    AgentWorkdir,
    AgentWorkdirArtifactMount,
    _canonical_files_ref,
    materialize_agent_workdir,
    validate_agent_workdir,
)
from nemo_platform_plugin.dependencies import get_entity_client, get_sdk_client
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
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


def test_job_config_defaults_to_bounded_fabric_timeout() -> None:
    config = ExecuteAgentJobConfig(agent="calc", input="hello")

    assert config.timeout_seconds == DEFAULT_AGENT_EXECUTION_TIMEOUT_SECONDS


def test_job_config_rejects_non_positive_fabric_timeout() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        ExecuteAgentJobConfig(agent="calc", input="hello", timeout_seconds=0)


@pytest.mark.asyncio
async def test_to_spec_resolves_bare_agent_against_route_workspace() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _agent()

    spec = await ExecuteAgentJob.to_spec(
        ExecuteAgentJobConfig(agent="calc", input="hello"),
        workspace="default",
        entity_client=entity_client,
        async_sdk=_sdk_with_files(),
        is_local=False,
    )

    step_config = ExecuteAgentStepConfig.model_validate(spec)
    assert step_config.agent.name == "calc"
    assert step_config.agent.workspace == "default"
    assert step_config.request.input == "hello"
    assert step_config.request.timeout_seconds == DEFAULT_AGENT_EXECUTION_TIMEOUT_SECONDS
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

    await ExecuteAgentJob.to_spec(
        ExecuteAgentJobConfig(agent="research/calc", input="hello"),
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
        await ExecuteAgentJob.to_spec(
            ExecuteAgentJobConfig(agent="missing", input="hello"),
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
        await ExecuteAgentJob.to_spec(
            ExecuteAgentJobConfig(agent="calc", input="hello"),
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
        await ExecuteAgentJob.to_spec(
            ExecuteAgentJobConfig(agent="calc", input="hello"),
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
        await ExecuteAgentJob.to_spec(
            ExecuteAgentJobConfig(agent="calc", input="hello"),
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

    spec = await ExecuteAgentJob.to_spec(
        ExecuteAgentJobConfig(agent="calc", input="hello", workdir=AgentWorkdir(base_workdir="source#project")),
        workspace="default",
        entity_client=entity_client,
        async_sdk=sdk,
        is_local=False,
    )

    step_config = ExecuteAgentStepConfig.model_validate(spec)
    assert step_config.workdir is not None
    assert step_config.workdir.base_workdir == "default/source#project/"
    sdk.files.list.assert_awaited_once_with(remote_path="default/source#project/")


@pytest.mark.asyncio
async def test_to_spec_rejects_single_file_base_workdir() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _agent()

    with pytest.raises(ValueError, match="non-empty directory"):
        await ExecuteAgentJob.to_spec(
            ExecuteAgentJobConfig(agent="calc", input="hello", workdir=AgentWorkdir(base_workdir="source#README.md")),
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
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
        workdir=AgentWorkdir(base_workdir="default/source#project/"),
    )

    with patch("nemo_agents_plugin.jobs.execute.AgentsConfig.get") as get_config:
        get_config.return_value.deployments.default_image = "registry.example/nmp-api:test"
        platform_spec = await ExecuteAgentJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )

    steps = list(platform_spec["steps"])
    assert len(steps) == 1
    step = steps[0]
    assert step["name"] == "execute-agent"
    assert step["executor"]["provider"] == "cpu"
    assert step["executor"]["container"]["image"] == "registry.example/nmp-api:test"
    assert step["executor"]["container"]["command"] == ["nemo_agents_plugin.tasks.execute"]
    assert step["config"] == spec.model_dump(mode="json")
    step_config = cast(dict[str, Any], step["config"])
    assert cast(dict[str, Any], step_config["request"])["input"] == "hello"
    assert step["environment"] == []


@pytest.mark.asyncio
async def test_compile_falls_back_to_qualified_api_image() -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )

    with (
        patch("nemo_agents_plugin.jobs.execute.AgentsConfig.get") as get_config,
        patch("nemo_agents_plugin.jobs.execute.get_qualified_image", return_value="qualified/nmp-api:dev"),
    ):
        get_config.return_value.deployments.default_image = ""
        platform_spec = await ExecuteAgentJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )

    steps = list(platform_spec["steps"])
    assert len(steps) == 1
    step = steps[0]
    assert step["executor"]["provider"] == "cpu"
    assert step["executor"]["container"]["image"] == "qualified/nmp-api:dev"


# --- environment / compute / secrets wiring ------------------------------------


def _env_ref_entity_client() -> AsyncMock:
    """Entity client that dereferences an AgentEnvironment ref chain.

    Dispatches ``entity_client.get`` by entity type: the Agent, then the
    AgentEnvironment and its EnvironmentSpec/ComputeSpec, all resolved by name.
    """
    entity_client = AsyncMock()

    env = AgentEnvironment(
        name="prod",
        workspace="default",
        environment_spec="default/prod-spec",
        compute_spec="default/prod-compute",
    )
    env_spec = AgentEnvironmentSpec(
        name="prod-spec",
        workspace="default",
        secrets={"OPENAI_API_KEY": "default/openai-key"},
    )
    compute_spec = AgentComputeSpec(
        name="prod-compute",
        workspace="default",
        resources=ComputeResources(limits={"cpu": "2", "memory": "4Gi", "nvidia.com/gpu": "1"}),
    )

    async def _get(entity_type: type, *, name: str, workspace: str) -> object:
        if entity_type is Agent:
            return _agent()
        if entity_type is AgentEnvironment:
            return env
        if entity_type is AgentEnvironmentSpec:
            return env_spec
        if entity_type is AgentComputeSpec:
            return compute_spec
        raise AssertionError(f"unexpected entity type {entity_type!r}")

    entity_client.get.side_effect = _get
    return entity_client


@pytest.mark.asyncio
async def test_to_spec_snapshots_resolved_environment_ref() -> None:
    entity_client = _env_ref_entity_client()

    spec = await ExecuteAgentJob.to_spec(
        ExecuteAgentJobConfig(agent="calc", input="hello", environment="default/prod"),
        workspace="default",
        entity_client=entity_client,
        async_sdk=_sdk_with_files(),
        is_local=False,
    )

    step_config = ExecuteAgentStepConfig.model_validate(spec)
    # Raw environment retained for provenance on the stored request.
    assert step_config.request.environment == "default/prod"
    # Secret refs collected from the EnvironmentSpec top-level secrets.
    assert step_config.secrets == {"OPENAI_API_KEY": "default/openai-key"}
    # Compute spec snapshotted (k8s-style resource maps preserved as-is).
    assert step_config.compute is not None
    assert step_config.compute.resources.limits == {"cpu": "2", "memory": "4Gi", "nvidia.com/gpu": "1"}


@pytest.mark.asyncio
async def test_to_spec_merges_inline_environment_into_config() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _agent()

    environment = AgentEnvironmentInline(
        environment_spec=EnvironmentSpecInline(
            env={"MY_FLAG": "on"},
            secrets={"OPENAI_API_KEY": "default/openai-key"},
        ),
        compute_spec=ComputeSpecInline(resources=ComputeResources(limits={"cpu": "500m"})),
    )

    spec = await ExecuteAgentJob.to_spec(
        ExecuteAgentJobConfig(agent="calc", input="hello", environment=environment),
        workspace="default",
        entity_client=entity_client,
        async_sdk=_sdk_with_files(),
        is_local=False,
    )

    step_config = ExecuteAgentStepConfig.model_validate(spec)
    # Inline env resolution never touches the entity store beyond the Agent.
    entity_client.get.assert_awaited_once_with(Agent, name="calc", workspace="default")
    # Plaintext env merged into the config's environment block.
    assert step_config.agent.config["environment"]["env"] == {"MY_FLAG": "on"}
    assert step_config.secrets == {"OPENAI_API_KEY": "default/openai-key"}
    assert step_config.compute is not None
    assert step_config.compute.resources.limits == {"cpu": "500m"}


@pytest.mark.asyncio
async def test_to_spec_mcp_secret_indirection_through_environment() -> None:
    """An Agent-declared MCP server is fulfilled with a secret ref via env-name
    indirection: the ref is collected into ``secrets`` (never written into the
    config), and the server's env references the value by name so the running
    step reads it from the process env the substrate populates.
    """
    mcp_agent_config = {
        "config_format": "nemo-agents-spec-v1",
        "name": "calc",
        "default_harness": "hermes",
        "harnesses": {"hermes": {"kind": "hermes"}},
        "models": {"default": {"provider": "openai", "model": "openai/gpt-5.4"}},
        "mcp": {"servers": {"search": {"transport": "streamable-http", "url": "http://agent-url"}}},
    }
    entity_client = AsyncMock()
    entity_client.get.return_value = Agent(
        name="calc",
        workspace="default",
        config=mcp_agent_config,
        config_format="nemo-agents-spec-v1",
    )

    environment = AgentEnvironmentInline(
        environment_spec=EnvironmentSpecInline(
            mcp={
                "search": McpFulfillment(
                    url="http://env-url",
                    env={"SEARCH_MODE": "fast"},
                    secrets={"SEARCH_TOKEN": "default/search-token"},
                ),
            },
        ),
    )

    spec = await ExecuteAgentJob.to_spec(
        ExecuteAgentJobConfig(agent="calc", input="hello", environment=environment),
        workspace="default",
        entity_client=entity_client,
        async_sdk=_sdk_with_files(),
        is_local=False,
    )

    step_config = ExecuteAgentStepConfig.model_validate(spec)
    server = step_config.agent.config["mcp"]["servers"]["search"]
    # Fulfillment url wins; non-secret env merged into the server config.
    assert server["url"] == "http://env-url"
    assert server["env"] == {"SEARCH_MODE": "fast"}
    # Secret ref collected for injection, NOT written into the server config.
    assert step_config.secrets == {"SEARCH_TOKEN": "default/search-token"}
    assert "SEARCH_TOKEN" not in server.get("env", {})


@pytest.mark.asyncio
async def test_to_spec_with_no_environment_leaves_snapshot_empty() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _agent()

    spec = await ExecuteAgentJob.to_spec(
        ExecuteAgentJobConfig(agent="calc", input="hello"),
        workspace="default",
        entity_client=entity_client,
        async_sdk=_sdk_with_files(),
        is_local=False,
    )

    step_config = ExecuteAgentStepConfig.model_validate(spec)
    assert step_config.request.environment is None
    assert step_config.compute is None
    assert step_config.secrets == {}


@pytest.mark.asyncio
async def test_to_spec_rejects_missing_environment_ref() -> None:
    entity_client = AsyncMock()

    async def _get(entity_type: type, *, name: str, workspace: str) -> object:
        if entity_type is Agent:
            return _agent()
        raise NemoEntityNotFoundError("missing")

    entity_client.get.side_effect = _get

    with pytest.raises(ValueError, match="AgentEnvironment 'prod' not found"):
        await ExecuteAgentJob.to_spec(
            ExecuteAgentJobConfig(agent="calc", input="hello", environment="default/prod"),
            workspace="default",
            entity_client=entity_client,
            async_sdk=_sdk_with_files(),
            is_local=False,
        )


@pytest.mark.asyncio
async def test_to_spec_rejects_environment_spec_selecting_non_local_provider() -> None:
    entity_client = AsyncMock()
    entity_client.get.return_value = _agent()

    environment = AgentEnvironmentInline(
        environment_spec=EnvironmentSpecInline(provider="docker"),
    )

    with pytest.raises(ValueError, match="only support local Fabric environments"):
        await ExecuteAgentJob.to_spec(
            ExecuteAgentJobConfig(agent="calc", input="hello", environment=environment),
            workspace="default",
            entity_client=entity_client,
            async_sdk=_sdk_with_files(),
            is_local=False,
        )


@pytest.mark.asyncio
async def test_compile_injects_secret_env_and_compute_resources() -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
        compute=ComputeSpecInline(
            resources=ComputeResources(
                limits={"cpu": "2", "memory": "4Gi", "nvidia.com/gpu": "2"},
                requests={"cpu": "1", "memory": "2Gi"},
            )
        ),
        secrets={"OPENAI_API_KEY": "default/openai-key"},
    )

    with patch("nemo_agents_plugin.jobs.execute.AgentsConfig.get") as get_config:
        get_config.return_value.deployments.default_image = "registry.example/nmp-api:test"
        platform_spec = await ExecuteAgentJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )

    step = list(platform_spec["steps"])[0]
    # Secret ref -> secret-backed env var.
    assert step["environment"] == [{"name": "OPENAI_API_KEY", "from_secret": {"name": "default/openai-key"}}]
    # Compute -> executor resources: cpu/memory pass through, gpu -> num_gpus.
    executor = cast(dict[str, Any], step["executor"])
    resources = executor["resources"]
    assert resources["limits"] == {"cpu": "2", "memory": "4Gi"}
    assert resources["requests"] == {"cpu": "1", "memory": "2Gi"}
    assert resources["num_gpus"] == 2


@pytest.mark.asyncio
async def test_compile_without_compute_omits_executor_resources() -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )

    with patch("nemo_agents_plugin.jobs.execute.AgentsConfig.get") as get_config:
        get_config.return_value.deployments.default_image = "registry.example/nmp-api:test"
        platform_spec = await ExecuteAgentJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )

    step = list(platform_spec["steps"])[0]
    assert "resources" not in cast(dict[str, Any], step["executor"])
    assert step["environment"] == []


@pytest.mark.asyncio
async def test_compile_rejects_unsupported_compute_resource_key() -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
        compute=ComputeSpecInline(resources=ComputeResources(limits={"cpu": "1", "ephemeral-storage": "1Gi"})),
    )

    with (
        patch("nemo_agents_plugin.jobs.execute.AgentsConfig.get") as get_config,
        pytest.raises(PlatformJobCompilationError, match="Unsupported compute resource key"),
    ):
        get_config.return_value.deployments.default_image = "registry.example/nmp-api:test"
        await ExecuteAgentJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )


@pytest.mark.asyncio
async def test_compile_rejects_secret_env_colliding_with_reserved_name() -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
        secrets={"NMP_BASE_URL": "default/some-secret"},
    )

    with (
        patch("nemo_agents_plugin.jobs.execute.AgentsConfig.get") as get_config,
        pytest.raises(PlatformJobCompilationError, match="reserved job env var name"),
    ):
        get_config.return_value.deployments.default_image = "registry.example/nmp-api:test"
        await ExecuteAgentJob.compile(
            workspace="default",
            spec=spec,
            entity_client=MagicMock(),
            job_name=None,
            async_sdk=MagicMock(),
        )


def test_run_without_input_workdir_saves_empty_input_snapshot(ctx: JobContext) -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )

    async def _invoke(request: Any) -> FabricRuntimeResult:
        assert request.input == "hello"
        assert request.base_dir == ctx.storage.ephemeral / "fabric"
        assert request.timeout_seconds == DEFAULT_AGENT_EXECUTION_TIMEOUT_SECONDS
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

    with patch("nemo_agents_plugin.jobs.execute.invoke_agent_config_request_once", _invoke):
        result = ExecuteAgentJob().run(spec.model_dump(mode="json"), ctx=ctx)

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


def test_run_threads_custom_timeout_to_fabric(ctx: JobContext) -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello", timeout_seconds=12.5),
        agent=_resolved_agent(),
    )

    async def _invoke(request: Any) -> FabricRuntimeResult:
        assert request.timeout_seconds == 12.5
        return FabricRuntimeResult(status="succeeded")

    with patch("nemo_agents_plugin.jobs.execute.invoke_agent_config_request_once", _invoke):
        result = ExecuteAgentJob().run(spec.model_dump(mode="json"), ctx=ctx)

    assert result["status"] == "completed"


def test_run_rejects_non_fabric_step_config(ctx: JobContext) -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=ResolvedAgentConfig(
            name="calc",
            workspace="default",
            config={"workflow": {}},
            config_format="nat-workflow-v1",
        ),
    )

    with pytest.raises(ValueError, match="only support 'nemo-agents-spec-v1'"):
        ExecuteAgentJob().run(spec.model_dump(mode="json"), ctx=ctx)


def test_run_downloads_and_registers_input_workdir(ctx: JobContext) -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(
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

    with patch("nemo_agents_plugin.jobs.execute.invoke_agent_config_request_once", _invoke):
        result = ExecuteAgentJob().run(spec.model_dump(mode="json"), ctx=ctx, sdk=sdk)

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
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(
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

    with patch("nemo_agents_plugin.jobs.execute.invoke_agent_config_request_once", _invoke):
        result = ExecuteAgentJob().run(spec.model_dump(mode="json"), ctx=ctx, sdk=sdk)

    assert result["status"] == "completed"
    assert result["input_workdir"]["name"] == "input_workdir"
    saved_workdir = ctx.storage.persistent / "results" / "input_workdir"
    assert not (saved_workdir / "stale.txt").exists()
    assert (saved_workdir / "config.yaml").read_text() == "name: calc\n"


def test_run_clears_stale_artifacts_dir_before_invoking(ctx: JobContext) -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )
    stale_artifacts = ctx.storage.ephemeral / "fabric" / "artifacts"
    stale_artifacts.mkdir(parents=True)
    (stale_artifacts / "stale.txt").write_text("stale\n")

    async def _invoke(request: Any) -> FabricRuntimeResult:
        assert not (request.base_dir / "artifacts" / "stale.txt").exists()
        (request.base_dir / "artifacts" / "fresh.txt").write_text("fresh\n")
        return FabricRuntimeResult(status="succeeded")

    with patch("nemo_agents_plugin.jobs.execute.invoke_agent_config_request_once", _invoke):
        result = ExecuteAgentJob().run(spec.model_dump(mode="json"), ctx=ctx)

    assert result["status"] == "completed"
    saved_artifacts = ctx.storage.persistent / "results" / "output_artifacts"
    assert not (saved_artifacts / "stale.txt").exists()
    assert (saved_artifacts / "fresh.txt").read_text() == "fresh\n"


def test_run_failed_download_does_not_register_partial_result(ctx: JobContext) -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(
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
        ExecuteAgentJob().run(spec.model_dump(mode="json"), ctx=ctx, sdk=sdk)

    assert not (ctx.storage.persistent / "results" / "input_workdir").exists()


def test_run_failed_fabric_result_saves_results_and_marks_job_failed(ctx: JobContext) -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )

    async def _invoke(request: Any) -> FabricRuntimeResult:
        (request.base_dir / "workspace" / "partial.txt").write_text("partial\n")
        return FabricRuntimeResult(
            status="failed",
            error={"stage": "invoke", "message": "adapter failed"},
        )

    with patch("nemo_agents_plugin.jobs.execute.invoke_agent_config_request_once", _invoke):
        result = ExecuteAgentJob().run(spec.model_dump(mode="json"), ctx=ctx)

    assert result["status"] == "failed"
    assert result["fabric_status"] == "failed"
    assert (ctx.storage.persistent / "results" / OUTPUT_WORKDIR_RESULT_NAME / "partial.txt").read_text() == "partial\n"
    payload = json.loads((ctx.storage.persistent / "results" / FABRIC_RUN_RESULT_NAME).read_text())
    assert payload["status"] == "failed"
    assert payload["error"] == {"stage": "invoke", "message": "adapter failed"}
    assert not (ctx.storage.persistent / "results" / FABRIC_ERROR_RESULT_NAME).exists()


def test_run_fabric_exception_saves_best_effort_error_results(ctx: JobContext) -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
        agent=_resolved_agent(),
    )

    async def _invoke(request: Any) -> FabricRuntimeResult:
        (request.base_dir / "workspace" / "partial.txt").write_text("partial\n")
        raise RuntimeError("fabric exploded")

    with (
        patch("nemo_agents_plugin.jobs.execute.invoke_agent_config_request_once", _invoke),
        pytest.raises(RuntimeError, match="fabric exploded"),
    ):
        ExecuteAgentJob().run(spec.model_dump(mode="json"), ctx=ctx)

    assert (ctx.storage.persistent / "results" / INPUT_WORKDIR_RESULT_NAME).is_dir()
    assert (ctx.storage.persistent / "results" / OUTPUT_WORKDIR_RESULT_NAME / "partial.txt").read_text() == "partial\n"
    assert (ctx.storage.persistent / "results" / OUTPUT_ARTIFACTS_RESULT_NAME).is_dir()
    payload = json.loads((ctx.storage.persistent / "results" / FABRIC_ERROR_RESULT_NAME).read_text())
    assert payload["type"] == "RuntimeError"
    assert payload["message"] == "fabric exploded"
    assert payload["fabric_status"] == "error"


def test_run_fabric_exception_preserves_original_error_if_result_save_fails(ctx: JobContext) -> None:
    spec = ExecuteAgentStepConfig(
        request=ExecuteAgentJobConfig(agent="calc", input="hello"),
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
        patch("nemo_agents_plugin.jobs.execute.invoke_agent_config_request_once", _invoke),
        pytest.raises(RuntimeError, match="fabric exploded"),
    ):
        ExecuteAgentJob().run(spec.model_dump(mode="json"), ctx=ctx)

    assert (ctx.storage.persistent / "results" / FABRIC_ERROR_RESULT_NAME).exists()


def test_execute_job_create_route_stores_canonical_step_config() -> None:
    app = FastAPI()
    app.include_router(add_job_routes(ExecuteAgentJob), prefix="/apis/agents/v2/workspaces/{workspace}")

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
            name="execute-1",
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
            "/apis/agents/v2/workspaces/default/jobs/execute",
            json={
                "name": "execute-1",
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
        "connection": {},
        "env": {},
        "metadata": {},
        "settings": {},
    }
    assert (
        body.spec["agent"]["config"]["models"]["default"]["base_url"]
        == "http://localhost:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1"
    )
    assert body.spec["request"] == {
        "agent": "calc",
        "input": "hello",
        "environment": None,
        "workdir": {"base_workdir": "source#project", "artifact_mounts": []},
        "timeout_seconds": DEFAULT_AGENT_EXECUTION_TIMEOUT_SECONDS,
    }
    assert body.spec["workdir"] == {"base_workdir": "default/source#project/", "artifact_mounts": []}
    assert body.platform_spec.steps[0].name == "execute-agent"
    assert response.json()["spec"]["workdir"]["base_workdir"] == "default/source#project/"


def test_execute_job_create_route_maps_reserved_secret_env_to_422() -> None:
    """A reserved-name secret-env collision must surface as a 422, not a 500.

    The collision is detected in ``compile`` (``_secret_environment``). The jobs
    create route only translates ``PlatformJobCompilationError`` into a 422 - a
    bare ``ValueError`` escaping ``compile`` would fall through to the global
    handler as an opaque 500. This guards that the error reaches the client as a
    descriptive 422 at the HTTP boundary (the unit test on ``_secret_environment``
    only checks the raised exception, not the mapped status code).
    """
    app = FastAPI()
    app.include_router(add_job_routes(ExecuteAgentJob), prefix="/apis/agents/v2/workspaces/{workspace}")

    # Agent resolves, plus an environment whose EnvironmentSpec maps a secret env
    # var onto a reserved job env var name (NMP_BASE_URL).
    env = AgentEnvironment(name="prod", workspace="default", environment_spec="default/prod-spec")
    env_spec = AgentEnvironmentSpec(
        name="prod-spec", workspace="default", secrets={"NMP_BASE_URL": "default/some-secret"}
    )

    async def _get(entity_type: type, *, name: str, workspace: str) -> object:
        if entity_type is Agent:
            return _agent()
        if entity_type is AgentEnvironment:
            return env
        if entity_type is AgentEnvironmentSpec:
            return env_spec
        raise AssertionError(f"unexpected entity type {entity_type!r}")

    entity_client = AsyncMock()
    entity_client.get.side_effect = _get
    app.dependency_overrides[get_entity_client] = lambda: entity_client
    app.dependency_overrides[get_sdk_client] = lambda: _sdk_with_files()

    with patch("nemo_agents_plugin.jobs.execute.AgentsConfig.get") as get_config:
        get_config.return_value.deployments.default_image = "registry.example/nmp-api:test"
        response = TestClient(app, raise_server_exceptions=False).post(
            "/apis/agents/v2/workspaces/default/jobs/execute",
            json={"name": "execute-1", "spec": {"agent": "calc", "input": "hello", "environment": "default/prod"}},
        )

    assert response.status_code == 422, response.text
    assert "reserved job env var name" in response.json()["detail"]
