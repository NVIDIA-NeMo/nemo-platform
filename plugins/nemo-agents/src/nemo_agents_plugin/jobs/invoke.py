# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Agent invocation job skeleton."""

from __future__ import annotations

import shutil
from typing import Any, ClassVar, cast

from nemo_agents_plugin.entities import Agent
from nemo_agents_plugin.tasks.invoke.workdir import (
    AgentWorkdir,
    materialize_agent_workdir,
    validate_agent_workdir,
)
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from nemo_platform_plugin.refs import ENTITY_REF_PATTERN, parse_entity_ref
from pydantic import BaseModel, Field

INPUT_WORKDIR_RESULT_NAME = "input_workdir"


class AgentInvocationJobConfig(BaseModel):
    model_config = {"json_schema_mode_override": "validation"}

    agent: str = Field(pattern=ENTITY_REF_PATTERN, description="Agent entity name or workspace/name ref.")
    input: str = Field(description="Prompt to pass to the agent.")
    workdir: AgentWorkdir | None = Field(
        default=None,
        description="Optional working directory configuration for the invocation.",
    )


class ResolvedAgentConfig(BaseModel):
    name: str
    workspace: str
    config: dict[str, Any]
    config_format: str


class AgentInvocationStepConfig(BaseModel):
    request: AgentInvocationJobConfig
    agent: ResolvedAgentConfig
    workdir: AgentWorkdir | None = None


class AgentInvocationJob(NemoJob):
    name: ClassVar[str] = "invoke"
    description: ClassVar[str] = "Invoke an agent as a scheduled platform job."
    container: ClassVar[str] = "cpu-tasks"
    input_spec_schema: ClassVar[type[BaseModel]] = AgentInvocationJobConfig
    spec_schema: ClassVar[type[BaseModel]] = AgentInvocationStepConfig

    @classmethod
    async def to_spec(  # type: ignore[override]
        cls,
        input_spec: BaseModel,
        *,
        workspace: str,
        entity_client: object,
        async_sdk: object,
        is_local: bool,
    ) -> BaseModel:
        """Validates an ``AgentInvocationJobConfig`` (external-facing) and resolves
        it to an ``AgentInvocationStepConfig`` (internal). Validating entity references
        in this step ensures errors surface to the user on their create request; storing
        resolved values on the step config obviates the need for a second fetch from the Job,
        and ensures we have an immutable snapshot of referenced entities as they existed
        at job creation time (stored on the Job record). The exceptions are File references
        in the AgentWorkdir, which are validated here, but not materialized; the Job snapshots
        them as a named result before doing any work.
        """
        del is_local
        request = cast(AgentInvocationJobConfig, input_spec)
        agent_ref = parse_entity_ref(request.agent, default_workspace=workspace)
        typed_entity_client = cast(Any, entity_client)
        try:
            agent = await typed_entity_client.get(Agent, name=agent_ref.name, workspace=agent_ref.workspace)
        except NemoEntityNotFoundError as exc:
            raise ValueError(f"Agent '{request.agent}' not found.") from exc

        workdir = None
        if request.workdir is not None:
            sdk = cast(AsyncNeMoPlatform, async_sdk)
            workdir = await validate_agent_workdir(request.workdir, sdk.files, default_workspace=workspace)

        return AgentInvocationStepConfig(
            request=request,
            agent=ResolvedAgentConfig(
                name=agent.name,
                workspace=agent.workspace,
                config=agent.config,
                config_format=agent.config_format,
            ),
            workdir=workdir,
        )

    @classmethod
    async def compile(  # type: ignore[override]
        cls,
        *,
        workspace: str,
        spec: BaseModel,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        del workspace, entity_client, job_name, async_sdk, options
        step_config = AgentInvocationStepConfig.model_validate(spec)
        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="invoke-agent",
                    executor=CPUExecutionProviderSpec(
                        profile=profile or "default",
                        provider="cpu",
                        container=ContainerSpec(
                            image=get_qualified_image("nmp-cpu-tasks"),
                            entrypoint=["python", "-m"],
                            command=["nemo_agents_plugin.tasks.invoke"],
                        ),
                    ),
                    config=step_config.model_dump(mode="json"),
                    environment=[],
                )
            ],
        )

    def run(self, config: dict, *, ctx: JobContext, sdk: NeMoPlatform | None = None) -> dict:
        step_config = AgentInvocationStepConfig.model_validate(config)
        result_ref = None
        if step_config.workdir is not None and (
            step_config.workdir.base_workdir is not None or step_config.workdir.artifact_mounts
        ):
            if sdk is None:
                raise RuntimeError("sdk is required to stage workdir inputs.")
            local_workdir = ctx.storage.ephemeral / INPUT_WORKDIR_RESULT_NAME
            if local_workdir.exists() or local_workdir.is_symlink():
                if local_workdir.is_dir() and not local_workdir.is_symlink():
                    shutil.rmtree(local_workdir)
                else:
                    local_workdir.unlink()
            materialize_agent_workdir(step_config.workdir, sdk.files, local_workdir)
            result_ref = ctx.results.save(INPUT_WORKDIR_RESULT_NAME, local_workdir)

        return {
            "status": "completed",
            "agent": f"{step_config.agent.workspace}/{step_config.agent.name}",
            "input_workdir": result_ref.model_dump() if result_ref else None,
        }
