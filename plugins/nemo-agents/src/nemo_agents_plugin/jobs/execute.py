# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Execute-agent job."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, ClassVar, cast

from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.agent_config_formats import resolve_agent_config_for_deployment
from nemo_agents_plugin.config import AgentsConfig
from nemo_agents_plugin.entities import NEMO_AGENTS_SPEC_CONFIG_FORMAT, Agent
from nemo_agents_plugin.fabric.invocation import (
    AgentConfigInvocationRequest,
    FabricDirectories,
    invoke_agent_config_request_once,
)
from nemo_agents_plugin.fabric.runtime import FabricRuntimeTimeoutError
from nemo_agents_plugin.tasks.execute.workdir import (
    AgentWorkdir,
    materialize_agent_workdir,
    validate_agent_workdir,
)
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.job_results import ResultRef
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    PlatformJobSpec,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from nemo_platform_plugin.refs import ENTITY_REF_PATTERN, parse_entity_ref
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

FABRIC_AGENT_CONFIG_FORMAT = NEMO_AGENTS_SPEC_CONFIG_FORMAT
FABRIC_BASE_DIR_NAME = "fabric"
INPUT_WORKDIR_RESULT_NAME = "input_workdir"
OUTPUT_WORKDIR_RESULT_NAME = "output_workdir"
OUTPUT_ARTIFACTS_RESULT_NAME = "output_artifacts"
FABRIC_RUN_RESULT_NAME = "fabric_run_result"
FABRIC_ERROR_RESULT_NAME = "fabric_error"
FABRIC_RUN_RESULT_FILENAME = "fabric_run_result.json"
FABRIC_ERROR_FILENAME = "fabric_error.json"
SUCCESSFUL_FABRIC_STATUSES = {"succeeded"}
DEFAULT_AGENT_EXECUTION_TIMEOUT_SECONDS = 60 * 60
DEFAULT_AGENT_EXECUTION_IMAGE_NAME = "nmp-api"


class ExecuteAgentJobConfig(BaseModel):
    model_config = {"json_schema_mode_override": "validation"}

    agent: str = Field(pattern=ENTITY_REF_PATTERN, description="Agent entity name or workspace/name ref.")
    input: str = Field(description="Prompt to pass to the agent.")
    workdir: AgentWorkdir | None = Field(
        default=None,
        description="Optional working directory configuration for the execution.",
    )
    timeout_seconds: float = Field(
        default=DEFAULT_AGENT_EXECUTION_TIMEOUT_SECONDS,
        gt=0,
        description="Maximum time to wait for Fabric to return an execution result.",
    )


class ResolvedAgentConfig(BaseModel):
    name: str
    workspace: str
    config: dict[str, Any]
    config_format: str


class ExecuteAgentStepConfig(BaseModel):
    request: ExecuteAgentJobConfig
    agent: ResolvedAgentConfig
    workdir: AgentWorkdir | None = None


class ExecuteAgentJob(NemoJob):
    name: ClassVar[str] = "execute"
    description: ClassVar[str] = "Execute an agent to completion as a scheduled platform job."
    container: ClassVar[str] = "cpu-tasks"
    input_spec_schema: ClassVar[type[BaseModel]] = ExecuteAgentJobConfig
    spec_schema: ClassVar[type[BaseModel]] = ExecuteAgentStepConfig

    @staticmethod
    def _execution_image() -> str:
        return AgentsConfig.get().deployments.default_image or get_qualified_image(DEFAULT_AGENT_EXECUTION_IMAGE_NAME)

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
        """Validates an ``ExecuteAgentJobConfig`` (external-facing) and resolves
        it to an ``ExecuteAgentStepConfig`` (internal). Validating entity references
        in this step ensures errors surface to the user on their create request; storing
        resolved values on the step config obviates the need for a second fetch from the Job,
        and ensures we have an immutable snapshot of referenced entities as they existed
        at job creation time (stored on the Job record). The exceptions are File references
        in the AgentWorkdir, which are validated here, but not materialized; the Job snapshots
        them as a named result before doing any work.
        """
        del is_local
        request = cast(ExecuteAgentJobConfig, input_spec)
        agent_ref = parse_entity_ref(request.agent, default_workspace=workspace)
        typed_entity_client = cast(Any, entity_client)
        try:
            agent = await typed_entity_client.get(Agent, name=agent_ref.name, workspace=agent_ref.workspace)
        except NemoEntityNotFoundError as exc:
            raise ValueError(f"Agent '{request.agent}' not found.") from exc

        _validate_agent_config_format(agent.config_format)
        resolved_agent_config = resolve_agent_config_for_deployment(
            agent.config_format,
            agent.config,
            workspace=agent.workspace,
            agent_name=agent.name,
        )
        _validate_agent_config(resolved_agent_config)

        workdir = None
        if request.workdir is not None:
            sdk = cast(AsyncNemoClient, async_sdk)
            workdir = await validate_agent_workdir(request.workdir, sdk.files, default_workspace=workspace)

        return ExecuteAgentStepConfig(
            request=request,
            agent=ResolvedAgentConfig(
                name=agent.name,
                workspace=agent.workspace,
                config=resolved_agent_config,
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
        step_config = ExecuteAgentStepConfig.model_validate(spec)
        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="execute-agent",
                    executor=CPUExecutionProviderSpec(
                        profile=profile or "default",
                        provider="cpu",
                        container=ContainerSpec(
                            image=cls._execution_image(),
                            entrypoint=["python", "-m"],
                            command=["nemo_agents_plugin.tasks.execute"],
                        ),
                    ),
                    config=step_config.model_dump(mode="json"),
                    environment=[],
                )
            ],
        )

    def run(self, config: dict, *, ctx: JobContext, sdk: NemoClient | None = None) -> dict:
        step_config = ExecuteAgentStepConfig.model_validate(config)
        _validate_agent_config_format(step_config.agent.config_format)
        agent_config = _validate_agent_config(step_config.agent.config)

        fabric_dirs = FabricDirectories.create(agent_config, ctx.storage.ephemeral)

        if step_config.workdir is not None and _has_workdir_inputs(step_config.workdir):
            if sdk is None:
                raise RuntimeError("sdk is required to stage workdir inputs.")
            materialize_agent_workdir(step_config.workdir, sdk.files, fabric_dirs.workspace)

        input_workdir_ref = ctx.results.save(INPUT_WORKDIR_RESULT_NAME, fabric_dirs.workspace)

        try:
            result = asyncio.run(
                invoke_agent_config_request_once(
                    AgentConfigInvocationRequest(
                        agent_config=agent_config,
                        input=step_config.request.input,
                        base_dir=fabric_dirs.base,
                        request_id=ctx.job_id,
                        caller_context={
                            "job_id": ctx.job_id,
                            "job_workspace": ctx.workspace,
                            "agent": f"{step_config.agent.workspace}/{step_config.agent.name}",
                        },
                        timeout_seconds=step_config.request.timeout_seconds,
                    )
                )
            )
        except Exception as error:
            self._save_fabric_error_results(
                ctx, workspace_dir=fabric_dirs.workspace, artifacts_dir=fabric_dirs.artifacts, error=error
            )
            raise

        fabric_run_result_ref = _save_json_result(
            ctx,
            FABRIC_RUN_RESULT_NAME,
            ctx.storage.ephemeral / FABRIC_RUN_RESULT_FILENAME,
            asdict(result),
        )
        output_workdir_ref = ctx.results.save(OUTPUT_WORKDIR_RESULT_NAME, fabric_dirs.workspace)
        output_artifacts_ref = ctx.results.save(OUTPUT_ARTIFACTS_RESULT_NAME, fabric_dirs.artifacts)
        status = "completed" if result.status in SUCCESSFUL_FABRIC_STATUSES else "failed"

        return {
            "status": status,
            "agent": f"{step_config.agent.workspace}/{step_config.agent.name}",
            "fabric_status": result.status,
            "runtime_id": result.runtime_id,
            "invocation_id": result.invocation_id,
            "request_id": result.request_id,
            "input_workdir": input_workdir_ref.model_dump(),
            "output_workdir": output_workdir_ref.model_dump(),
            "output_artifacts": output_artifacts_ref.model_dump(),
            "fabric_run_result": fabric_run_result_ref.model_dump(),
        }

    def _save_fabric_error_results(
        self,
        ctx: JobContext,
        *,
        workspace_dir: Path,
        artifacts_dir: Path,
        error: Exception,
    ) -> None:
        cause = error.__cause__
        payload = {
            "type": type(error).__name__,
            "message": str(error),
            "fabric_status": "timeout" if isinstance(error, (TimeoutError, FabricRuntimeTimeoutError)) else "error",
            "cause_type": type(cause).__name__ if cause is not None else None,
            "cause_message": str(cause) if cause is not None else None,
        }
        for name, path in (
            (OUTPUT_WORKDIR_RESULT_NAME, workspace_dir),
            (OUTPUT_ARTIFACTS_RESULT_NAME, artifacts_dir),
        ):
            try:
                if path.exists():
                    ctx.results.save(name, path)
            except Exception:
                logger.warning("Failed to save %s after Fabric invocation error.", name, exc_info=True)
        try:
            _save_json_result(ctx, FABRIC_ERROR_RESULT_NAME, ctx.storage.ephemeral / FABRIC_ERROR_FILENAME, payload)
        except Exception:
            logger.warning("Failed to save Fabric error result.", exc_info=True)


def _has_workdir_inputs(workdir: AgentWorkdir) -> bool:
    return workdir.base_workdir is not None or bool(workdir.artifact_mounts)


def _save_json_result(ctx: JobContext, name: str, path: Path, payload: dict[str, Any]) -> ResultRef:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return ctx.results.save(name, path)


def _validate_agent_config_format(config_format: str) -> None:
    if config_format != FABRIC_AGENT_CONFIG_FORMAT:
        raise ValueError(
            f"Config format {config_format!r} is not supported; "
            f"agents.execute jobs only support {FABRIC_AGENT_CONFIG_FORMAT!r}."
        )


def _validate_agent_config(config: dict) -> AgentConfig:
    agent_config = AgentConfig.model_validate(config)
    if agent_config.environment.provider != "local":
        raise ValueError("agents.execute jobs only support local Fabric environments.")

    return agent_config
