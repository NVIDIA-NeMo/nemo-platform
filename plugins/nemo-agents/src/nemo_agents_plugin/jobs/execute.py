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
from nemo_agents_plugin.entities import (
    NEMO_AGENTS_SPEC_CONFIG_FORMAT,
    Agent,
    AgentEnvironmentInline,
    ComputeSpecInline,
)
from nemo_agents_plugin.environment_resolution import (
    EnvironmentResolutionError,
    merge_environment_spec_into_agent_config,
    resolve_environment,
)
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
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.entity_client import NemoEntityNotFoundError
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.job_results import ResultRef
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    EnvironmentVariable,
    EnvironmentVariableFromSecret,
    PlatformJobSpec,
    PlatformJobStep,
    ResourcesLimitsSpec,
    ResourcesSpec,
)
from nemo_platform_plugin.jobs.constants import (
    CONFIG_TASK_STORAGE_PATH_ENVVAR,
    EPHEMERAL_TASK_STORAGE_PATH_ENVVAR,
    NEMO_JOB_ATTEMPT_ID_ENVVAR,
    NEMO_JOB_FILESET_ENVVAR,
    NEMO_JOB_ID_ENVVAR,
    NEMO_JOB_SECRETS_ENVVAR,
    NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
    NEMO_JOB_STEP_ENVVAR,
    NEMO_JOB_TASK_ENVVAR,
    NEMO_JOB_WORKSPACE_ENVVAR,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
    TASK_CONFIG_ENVVAR,
)
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
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

# k8s resource key carrying the GPU count. The agents ``ComputeResources`` maps
# express GPUs the Kubernetes way (a ``nvidia.com/gpu`` entry in ``limits``);
# the jobs executor's ``ResourcesSpec`` instead carries a top-level integer
# ``num_gpus``. We translate that one key and pass ``cpu``/``memory`` through.
_GPU_RESOURCE_KEY = "nvidia.com/gpu"
# Resource keys we know how to translate onto the jobs ``ResourcesSpec``. Any
# other k8s resource key would be silently dropped (it has no home on the
# executor spec), so we reject it up front instead.
_SUPPORTED_RESOURCE_KEYS = frozenset({"cpu", "memory", _GPU_RESOURCE_KEY})

# Env var names a secret-backed env var must never shadow. Splitting a secret's
# resolved value over one of these would clobber platform-injected job state (the
# jobs substrate sets the ``NEMO_JOB_*``/``NMP_TASK_CONFIG`` family on every
# step) or the agent-container env the execute task relies on to reach the
# platform SDK (mirrors the deployment container's reserved set). Reject the
# collision at compile time so it can never reach the running step.
_RESERVED_ENV_VAR_NAMES = frozenset(
    {
        # Jobs substrate (nemo_platform_plugin.jobs.constants).
        EPHEMERAL_TASK_STORAGE_PATH_ENVVAR,
        PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
        CONFIG_TASK_STORAGE_PATH_ENVVAR,
        TASK_CONFIG_ENVVAR,
        NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
        NEMO_JOB_ID_ENVVAR,
        NEMO_JOB_ATTEMPT_ID_ENVVAR,
        NEMO_JOB_STEP_ENVVAR,
        NEMO_JOB_TASK_ENVVAR,
        NEMO_JOB_WORKSPACE_ENVVAR,
        NEMO_JOB_FILESET_ENVVAR,
        NEMO_JOB_SECRETS_ENVVAR,
        # Agent execution env (mirrors the deployment container's reserved set).
        "NMP_WORKSPACE",
        "NMP_AGENT_NAME",
        "NMP_BASE_URL",
        "PYTHONPATH",
        "AGENT_CONFIG_PATH",
        "NAT_CONFIG_PATH",
    }
)


class ExecuteAgentJobConfig(BaseModel):
    model_config = {"json_schema_mode_override": "validation"}

    agent: str = Field(pattern=ENTITY_REF_PATTERN, description="Agent entity name or workspace/name ref.")
    input: str = Field(description="Prompt to pass to the agent.")
    environment: str | AgentEnvironmentInline | None = Field(
        default=None,
        description=(
            'AgentEnvironment to run under: a "workspace/name" ref to a stored '
            "AgentEnvironment, an inline environment, or None. Its EnvironmentSpec "
            "is merged into the agent config and its ComputeSpec/secret refs are "
            "snapshotted onto the job step at creation time."
        ),
    )
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
    # Immutable snapshot of the resolved AgentEnvironment, mirroring
    # AgentDeployment. ``agent.config`` already holds the merged config;
    # ``compute`` and ``secrets`` are snapshotted for the executor. ``environment``
    # retains the raw request value for provenance. Once created, the job is not
    # kept in sync with the underlying environment entities.
    environment: str | AgentEnvironmentInline | None = None
    compute: ComputeSpecInline | None = None
    secrets: dict[str, str] = Field(default_factory=dict)


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

        # Resolve and merge the referenced AgentEnvironment. The EnvironmentSpec is
        # merged into the resolved config (EnvironmentSpec-wins precedence); the
        # ComputeSpec and secret-env references are snapshotted onto the step for
        # the executor. This mirrors ``create_deployment`` so environment errors
        # surface on the create request and the referenced entities are captured
        # as an immutable snapshot. ``EnvironmentResolutionError`` is surfaced as a
        # ``ValueError`` (matching the "Agent not found" pattern) so the jobs
        # create path reports it to the caller.
        try:
            resolved_env = await resolve_environment(
                request.environment, workspace=workspace, entity_client=typed_entity_client
            )
            merged = merge_environment_spec_into_agent_config(resolved_agent_config, resolved_env.environment_spec)
        except EnvironmentResolutionError as exc:
            raise ValueError(str(exc)) from exc

        # Validate the merged config: an EnvironmentSpec can override the harness
        # provider, so validation must run after the merge to reject e.g. a spec
        # that selects a non-local Fabric environment.
        _validate_agent_config(merged.config)

        workdir = None
        if request.workdir is not None:
            sdk = cast(AsyncNeMoPlatform, async_sdk)
            workdir = await validate_agent_workdir(request.workdir, sdk.files, default_workspace=workspace)

        return ExecuteAgentStepConfig(
            request=request,
            agent=ResolvedAgentConfig(
                name=agent.name,
                workspace=agent.workspace,
                config=merged.config,
                config_format=agent.config_format,
            ),
            workdir=workdir,
            environment=request.environment,
            compute=resolved_env.compute_spec,
            secrets=merged.secrets,
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

        executor = CPUExecutionProviderSpec(
            profile=profile or "default",
            provider="cpu",
            container=ContainerSpec(
                image=cls._execution_image(),
                entrypoint=["python", "-m"],
                command=["nemo_agents_plugin.tasks.execute"],
            ),
        )
        # Snapshotted compute -> executor resources, and secret-env refs ->
        # secret-backed step env vars. Both validate the snapshot and raise
        # ``ValueError`` on a bad shape (an unsupported resource key, or a secret
        # env name colliding with a reserved job env var). Surface those as a
        # ``PlatformJobCompilationError`` so the jobs create route maps them to a
        # descriptive 422 rather than an opaque 500 (the route's compile wrapper
        # only translates ``PlatformJobCompilationError``, not bare ``ValueError``).
        try:
            # Snapshotted compute -> executor resources. Injected only when the
            # environment supplied a compute spec, so the default CPU sizing is
            # left to the jobs backend otherwise.
            resources = _compute_to_resources(step_config.compute)
            # Snapshotted secret-env refs -> secret-backed step env vars. The jobs
            # substrate materializes each value into the process env under
            # ENV_NAME; Fabric and its MCP servers read it by name (env-var-name
            # indirection - see environment_resolution).
            environment = _secret_environment(step_config.secrets)
        except ValueError as exc:
            raise PlatformJobCompilationError(str(exc)) from exc

        if resources is not None:
            executor["resources"] = resources

        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="execute-agent",
                    executor=executor,
                    config=step_config.model_dump(mode="json"),
                    environment=environment,
                )
            ],
        )

    def run(self, config: dict, *, ctx: JobContext, sdk: NeMoPlatform | None = None) -> dict:
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


def _secret_environment(secrets: dict[str, str]) -> list[EnvironmentVariable]:
    """Compile snapshotted secret-env refs into secret-backed step env vars.

    Each ``ENV_NAME -> "workspace/secret"`` entry becomes an
    ``EnvironmentVariable`` whose value is populated from the referenced Secret.
    A secret env name must never shadow a platform-injected env var (the jobs
    substrate or agent-execution env - see ``_RESERVED_ENV_VAR_NAMES``): the
    resolved value would clobber platform state, so reject the collision here.
    """
    if not secrets:
        return []

    reserved = sorted(name for name in secrets if name in _RESERVED_ENV_VAR_NAMES)
    if reserved:
        raise ValueError(
            f"Secret env var(s) {', '.join(reserved)} collide with reserved job env var name(s). "
            f"Reserved names: {', '.join(sorted(_RESERVED_ENV_VAR_NAMES))}."
        )

    return [
        EnvironmentVariable(name=env_name, from_secret=EnvironmentVariableFromSecret(name=ref))
        for env_name, ref in secrets.items()
    ]


def _compute_to_resources(compute: ComputeSpecInline | None) -> ResourcesSpec | None:
    """Map a snapshotted agents ComputeSpec onto the jobs executor ResourcesSpec.

    Agents ``ComputeResources`` express requests/limits the Kubernetes way -
    ``cpu``/``memory`` scalars plus a ``nvidia.com/gpu`` GPU count. The jobs
    executor's ``ResourcesSpec`` instead carries ``cpu``/``memory`` under
    ``limits``/``requests`` and a top-level integer ``num_gpus``. We translate
    ``cpu``/``memory`` through and lift ``nvidia.com/gpu`` into ``num_gpus``,
    preferring the limits count and falling back to requests. Any other k8s
    resource key has no home on ``ResourcesSpec`` and would be silently dropped,
    so it is rejected instead.
    """
    if compute is None:
        return None

    resources = compute.resources
    _reject_unsupported_resource_keys(resources.limits, "limits")
    _reject_unsupported_resource_keys(resources.requests, "requests")

    spec: ResourcesSpec = {}
    limits = _cpu_memory_spec(resources.limits)
    if limits:
        spec["limits"] = limits
    requests = _cpu_memory_spec(resources.requests)
    if requests:
        spec["requests"] = requests

    num_gpus = _gpu_count(resources.limits, resources.requests)
    if num_gpus is not None:
        spec["num_gpus"] = num_gpus

    return spec or None


def _reject_unsupported_resource_keys(resource_map: dict[str, str], where: str) -> None:
    unsupported = sorted(key for key in resource_map if key not in _SUPPORTED_RESOURCE_KEYS)
    if unsupported:
        raise ValueError(
            f"Unsupported compute resource key(s) in {where}: {', '.join(unsupported)}. "
            f"agents.execute jobs support only {', '.join(sorted(_SUPPORTED_RESOURCE_KEYS))}."
        )


def _cpu_memory_spec(resource_map: dict[str, str]) -> ResourcesLimitsSpec:
    # ``ResourcesLimitsSpec`` and ``ResourcesRequestsSpec`` are the same TypedDict
    # (``ComputeResourceSpecParam``); one builder covers both sides.
    spec: ResourcesLimitsSpec = {}
    if "cpu" in resource_map:
        spec["cpu"] = resource_map["cpu"]
    if "memory" in resource_map:
        spec["memory"] = resource_map["memory"]
    return spec


def _gpu_count(limits: dict[str, str], requests: dict[str, str]) -> int | None:
    raw = limits.get(_GPU_RESOURCE_KEY, requests.get(_GPU_RESOURCE_KEY))
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {_GPU_RESOURCE_KEY!r} value {raw!r}; expected an integer GPU count.") from exc


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
