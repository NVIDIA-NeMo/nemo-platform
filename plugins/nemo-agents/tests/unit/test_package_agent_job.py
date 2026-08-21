# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from nemo_agents_plugin.entities import NAT_WORKFLOW_CONFIG_FORMAT, NEMO_AGENTS_SPEC_CONFIG_FORMAT, Agent
from nemo_agents_plugin.jobs.package_agent import (
    PackageAgentInput,
    PackageAgentJob,
    PackageAgentSpec,
)
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError
from nemo_platform_plugin.jobs.exceptions import (
    PlatformJobCompilationError,
    PlatformJobDependencyUnavailableError,
)
from nemo_platform_plugin.jobs.execution_profiles import (
    DockerJobExecutionProfile,
    DockerJobExecutionProfileConfig,
    SubprocessJobExecutionProfile,
)
from pydantic import ValidationError

FABRIC_CONFIG: dict[str, Any] = {"config_format": NEMO_AGENTS_SPEC_CONFIG_FORMAT, "harness": {"type": "deepagents"}}


class _StubEntityClient:
    def __init__(self, agent: Agent | None) -> None:
        self._agent = agent

    async def get(self, _cls: type, *, name: str, workspace: str) -> Agent:
        if self._agent is None:
            raise NemoEntityNotFoundError(f"no agent {name} in {workspace}")
        return self._agent


def _agent(config_format: str = NEMO_AGENTS_SPEC_CONFIG_FORMAT) -> Agent:
    return Agent(name="my-agent", workspace="default", config=FABRIC_CONFIG, config_format=config_format)


def _subprocess_profile(profile: str = "default") -> SubprocessJobExecutionProfile:
    return SubprocessJobExecutionProfile(profile=profile)


def _docker_profile(profile: str = "default") -> DockerJobExecutionProfile:
    return DockerJobExecutionProfile(profile=profile, config=DockerJobExecutionProfileConfig())


def _patch_profiles(profiles: list[Any] | Exception):
    """Patch the jobs-client lookup ``compile`` uses to discover execution profiles."""
    client = MagicMock()
    if isinstance(profiles, Exception):
        client.get_execution_profiles = MagicMock(side_effect=profiles)
    else:
        response = MagicMock()
        response.data = MagicMock(return_value=profiles)

        async def _get() -> Any:
            return response

        client.get_execution_profiles = _get
    return patch("nemo_agents_plugin.jobs.package_agent.client_from_platform", return_value=client)


class TestToSpec:
    async def test_resolves_agent_config_inline(self) -> None:
        spec = await PackageAgentJob.to_spec(
            PackageAgentInput(agent="my-agent"),
            workspace="default",
            entity_client=_StubEntityClient(_agent()),
            async_sdk=None,
            is_local=False,
        )

        assert isinstance(spec, PackageAgentSpec)
        assert spec.workspace == "default"
        assert spec.agent_config == FABRIC_CONFIG

    async def test_missing_agent_fails_at_submit(self) -> None:
        with pytest.raises(PlatformJobCompilationError, match="not found in workspace"):
            await PackageAgentJob.to_spec(
                PackageAgentInput(agent="ghost"),
                workspace="default",
                entity_client=_StubEntityClient(None),
                async_sdk=None,
                is_local=False,
            )

    async def test_nat_workflow_agent_is_rejected(self) -> None:
        with pytest.raises(PlatformJobCompilationError, match="packaging supports"):
            await PackageAgentJob.to_spec(
                PackageAgentInput(agent="my-agent"),
                workspace="default",
                entity_client=_StubEntityClient(_agent(NAT_WORKFLOW_CONFIG_FORMAT)),
                async_sdk=None,
                is_local=False,
            )

    async def test_knobs_survive_resolution(self) -> None:
        spec = await PackageAgentJob.to_spec(
            PackageAgentInput(agent="my-agent", tag="custom:1.0", allow_root=True, python_version="3.12"),
            workspace="default",
            entity_client=_StubEntityClient(_agent()),
            async_sdk=None,
            is_local=False,
        )

        assert isinstance(spec, PackageAgentSpec)
        assert (spec.tag, spec.allow_root, spec.python_version) == ("custom:1.0", True, "3.12")


class TestCompile:
    async def _compile(self, **kwargs: Any) -> Any:
        return await PackageAgentJob.compile(
            workspace="default",
            spec=PackageAgentSpec(agent="my-agent", workspace="default", agent_config=FABRIC_CONFIG),
            entity_client=None,
            job_name=None,
            async_sdk=MagicMock(),
            **kwargs,
        )

    async def test_emits_host_subprocess_step(self) -> None:
        with _patch_profiles([_subprocess_profile()]):
            platform_spec = await self._compile()

        step = next(iter(platform_spec["steps"]))
        assert step["executor"]["provider"] == "subprocess"
        assert step["executor"]["command"] == ["python", "-m", "nemo_agents_plugin.tasks.package"]

    async def test_url_workspace_overwrites_spec_workspace(self) -> None:
        with _patch_profiles([_subprocess_profile()]):
            platform_spec = await PackageAgentJob.compile(
                workspace="default",
                spec=PackageAgentSpec(agent="my-agent", workspace="attacker", agent_config=FABRIC_CONFIG),
                entity_client=None,
                job_name=None,
                async_sdk=MagicMock(),
            )

        step = next(iter(platform_spec["steps"]))
        assert step["config"]["workspace"] == "default"

    async def test_non_subprocess_backend_is_rejected(self) -> None:
        with _patch_profiles([_docker_profile()]):
            with pytest.raises(PlatformJobCompilationError, match="does not resolve to a subprocess backend"):
                await self._compile()

    async def test_rejection_names_the_local_fallback(self) -> None:
        with _patch_profiles([]):
            with pytest.raises(PlatformJobCompilationError, match="nemo agents package"):
                await self._compile()

    async def test_named_profile_must_match(self) -> None:
        with _patch_profiles([_subprocess_profile("other")]):
            with pytest.raises(PlatformJobCompilationError):
                await self._compile(profile="default")

    async def test_unreachable_jobs_service_is_retryable(self) -> None:
        with _patch_profiles(RuntimeError("connection refused")):
            with pytest.raises(PlatformJobDependencyUnavailableError, match="Retry the submission"):
                await self._compile()

    async def test_missing_sdk_is_retryable(self) -> None:
        with pytest.raises(PlatformJobDependencyUnavailableError):
            await PackageAgentJob.compile(
                workspace="default",
                spec=PackageAgentSpec(agent="my-agent", workspace="default", agent_config=FABRIC_CONFIG),
                entity_client=None,
                job_name=None,
                async_sdk=None,
            )


class TestRun:
    def test_builds_from_staged_spec_fileset(self, tmp_path: Path) -> None:
        captured: dict[str, Any] = {}

        async def _stage(*, workspace: str, agent_name: str, agent_config: dict, base_dir: Path, sdk: Any) -> None:
            captured["workspace"] = workspace
            captured["agent_name"] = agent_name
            (base_dir / "skills").mkdir()
            (base_dir / "skills" / "SKILL.md").write_text("# staged\n")

        def _build(agent_config_path: Path, **kwargs: Any) -> str:
            captured["config_path"] = agent_config_path
            captured["rendered"] = yaml.safe_load(agent_config_path.read_text())
            captured["staged_skill"] = (agent_config_path.parent / "skills" / "SKILL.md").exists()
            captured["kwargs"] = kwargs
            return "my-agent-abc123:26.08.21"

        with (
            patch("nemo_agents_plugin.runner.fabric_artifact_staging.stage_fabric_spec_dir", _stage),
            patch("nemo_agents_plugin.container.builder.build_fabric_agent_image", _build),
        ):
            result = PackageAgentJob().run(
                PackageAgentSpec(
                    agent="my-agent", workspace="default", agent_config=FABRIC_CONFIG, tag="my-agent-abc123:26.08.21"
                ).model_dump(mode="json"),
            )

        assert result == {"image": "my-agent-abc123:26.08.21", "agent": "my-agent"}
        assert captured["workspace"] == "default"
        assert captured["rendered"] == FABRIC_CONFIG
        assert captured["staged_skill"], "agent.yaml must be written after staging clears the tree"

    def test_build_context_is_removed(self, tmp_path: Path) -> None:
        seen: dict[str, Path] = {}

        async def _stage(**kwargs: Any) -> None:
            return None

        def _build(agent_config_path: Path, **kwargs: Any) -> str:
            seen["dir"] = agent_config_path.parent
            return "x:latest"

        with (
            patch("nemo_agents_plugin.runner.fabric_artifact_staging.stage_fabric_spec_dir", _stage),
            patch("nemo_agents_plugin.container.builder.build_fabric_agent_image", _build),
        ):
            PackageAgentJob().run(
                PackageAgentSpec(agent="my-agent", workspace="default", agent_config=FABRIC_CONFIG).model_dump(
                    mode="json"
                ),
            )

        assert not seen["dir"].exists()

    def test_build_failure_propagates(self) -> None:
        from nemo_agents_plugin.container.errors import ImageBuildError

        async def _stage(**kwargs: Any) -> None:
            return None

        def _build(agent_config_path: Path, **kwargs: Any) -> str:
            raise ImageBuildError("Docker build failed: no such host")

        with (
            patch("nemo_agents_plugin.runner.fabric_artifact_staging.stage_fabric_spec_dir", _stage),
            patch("nemo_agents_plugin.container.builder.build_fabric_agent_image", _build),
        ):
            with pytest.raises(ImageBuildError, match="no such host"):
                PackageAgentJob().run(
                    PackageAgentSpec(agent="my-agent", workspace="default", agent_config=FABRIC_CONFIG).model_dump(
                        mode="json"
                    ),
                )


class TestTaskEntrypointWiring:
    """The build context comes from an async fileset download, so the entrypoint
    must hand ``run`` an async SDK — without it the image silently loses skills."""

    def test_entrypoint_passes_async_sdk(self) -> None:
        import nemo_agents_plugin.tasks.package.__main__ as entrypoint

        with (
            patch.object(entrypoint, "get_task_sdk", return_value="sync"),
            patch.object(entrypoint, "get_async_task_sdk", return_value="async") as async_sdk,
            patch.object(entrypoint, "run_task", return_value=0) as run_task,
        ):
            assert entrypoint.main() == 0

        async_sdk.assert_called_once_with("agents")
        assert run_task.call_args.kwargs["async_sdk"] == "async"

    def test_missing_client_warns_about_dropped_artifacts(self, caplog) -> None:
        async def _noop(**kwargs: Any) -> None:
            return None

        with (
            patch("nemo_agents_plugin.runner.fabric_artifact_staging.stage_fabric_spec_dir", _noop),
            patch("nemo_agents_plugin.container.builder.build_fabric_agent_image", lambda p, **k: "x:latest"),
            caplog.at_level("WARNING"),
        ):
            PackageAgentJob().run(
                PackageAgentSpec(agent="my-agent", workspace="default", agent_config=FABRIC_CONFIG).model_dump(
                    mode="json"
                ),
                async_sdk=None,
            )

        assert "my-agent-spec" in caplog.text


class TestDockerfileInjection:
    """`base_image_*` / `*_version` are interpolated into the Dockerfile unescaped,
    and the submitter is a remote caller — a newline would append build instructions."""

    @pytest.mark.parametrize(
        "field",
        ["base_image_url", "base_image_tag", "python_version", "uv_version"],
    )
    def test_newline_payload_is_rejected(self, field: str) -> None:
        with pytest.raises(ValidationError):
            payload: dict[str, Any] = {field: "noble\nRUN echo pwned"}
            PackageAgentInput(agent="my-agent", **payload)

    @pytest.mark.parametrize(
        "field",
        ["base_image_url", "base_image_tag", "python_version", "uv_version"],
    )
    def test_whitespace_payload_is_rejected(self, field: str) -> None:
        with pytest.raises(ValidationError):
            payload: dict[str, Any] = {field: "noble RUN echo pwned"}
            PackageAgentInput(agent="my-agent", **payload)

    def test_realistic_values_are_accepted(self) -> None:
        spec = PackageAgentInput(
            agent="my-agent",
            base_image_url="nvcr.io/nvidia/base/ubuntu",
            base_image_tag="noble-20260217",
            python_version="3.13",
            uv_version="0.9.14",
        )
        assert spec.base_image_url == "nvcr.io/nvidia/base/ubuntu"

    def test_registry_with_port_is_accepted(self) -> None:
        assert PackageAgentInput(agent="a", base_image_url="localhost:5000/base/ubuntu").base_image_url


class TestCliSurface:
    def test_job_name_does_not_shadow_the_local_package_command(self) -> None:
        """`nemo agents package` is an existing command; the generated job sub-group
        mounts by `name` onto the same Typer app and would win."""
        assert PackageAgentJob.name != "package"

    def test_rest_collection_path_is_pinned(self) -> None:
        assert PackageAgentJob.job_collection_path == "/jobs/package"
