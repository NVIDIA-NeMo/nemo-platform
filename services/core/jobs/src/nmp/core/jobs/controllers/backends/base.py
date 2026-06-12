# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Generic, Optional, TypeVar

from nemo_platform import NeMoPlatform, NotFoundError
from nemo_platform.types import PlatformJobStatus
from nemo_platform.types.jobs import PlatformJobStep, PlatformJobStepWithContext
from nmp.common.auth.models import NMP_PRINCIPAL_ENVVAR
from nmp.common.config.base import (
    LOOPBACK_ADDRESSES,
    NMP_CONFIG_WARNINGS_DISABLED_ENV_VAR,
    PlatformConfig,
    determine_loopback_override,
)
from nmp.common.jobs.constants import (
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
from nmp.common.sdk_factory import get_entity_parts
from nmp.core.jobs.app.providers import ComputeResources
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

ExecutionProviderConfigT = TypeVar("ExecutionProviderConfigT")
ExecutionProfileConfigT = TypeVar("ExecutionProfileConfigT")

DEFAULT_PROFILE = "default"
DEFAULT_PROVIDER = "cpu"

# Env var names set by the platform during job creation; user-provided profile environment must not conflict.
RESERVED_JOB_ENVIRONMENT_VARIABLE_NAMES: frozenset[str] = frozenset(
    {
        # From nmp.common.jobs.constants
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
        # Auth
        NMP_PRINCIPAL_ENVVAR,
        # OTEL (telemetry)
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        "OTEL_LOGS_EXPORTER",
        "OTEL_SERVICE_NAME",
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS",
        # Platform shared envvars (to_shared_envvars with NMP_ prefix)
        NMP_CONFIG_WARNINGS_DISABLED_ENV_VAR,
        "NMP_BASE_URL",
        "NMP_JOBS_URL",
        "NMP_FILES_URL",
        "NMP_MODELS_URL",
        "NMP_SECRETS_URL",
    }
)


class JobUpdate(BaseModel):
    status: PlatformJobStatus
    status_details: dict | None = None
    error_details: dict | None = None


class JobExecutionProfileConfig(BaseModel):
    ttl_seconds_before_active: int = 30 * 60  # 30 minutes
    ttl_seconds_active: int = 24 * 60 * 60  # 24 hours
    ttl_seconds_after_finished: int = 60 * 60  # 1 hour
    cleanup_completed_jobs_immediately: bool = True
    launcher_tool_path: str = Field(default="/tools/jobs-launcher", description="Path to the jobs launcher tool")
    default_task_image: str | None = Field(
        default=None,
        min_length=1,
        description="Default container image for job task pods. Used when a job step omits container.image. "
        "When unset, falls back to the platform CPU tasks image (platform.image_registry/nmp-cpu-tasks:platform.image_tag).",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Optional env vars applied to all jobs (e.g. HOME=/tmp). Keys must not conflict with platform-reserved names. Job steps may override these variables.",
    )

    @model_validator(mode="after")
    def validate_env_no_reserved_names(self) -> JobExecutionProfileConfig:
        conflicting = [k for k in self.env if k in RESERVED_JOB_ENVIRONMENT_VARIABLE_NAMES]
        if conflicting:
            raise ValueError(
                f"Profile environment keys must not conflict with platform-reserved names: {sorted(conflicting)}"
            )
        return self


_DEFAULT_TASK_IMAGE_NAME = "nmp-cpu-tasks"


def resolve_task_image(container_image: str | None, default_task_image: str | None) -> str:
    """Resolve the container image for a job task.

    Priority:
    1. Explicit container.image from the job step
    2. default_task_image from the execution profile config
    3. Platform CPU tasks image derived from platform.image_registry / image_tag
    """
    from nemo_platform_plugin.jobs.image import get_qualified_image

    return container_image or default_task_image or get_qualified_image(_DEFAULT_TASK_IMAGE_NAME)


def resolve_gpu_job_shm_size(
    executor_resources: ComputeResources | None,
    profile_resources: ComputeResources | None,
    num_gpus: int,
) -> str:
    """Pick SHM size for GPU workloads: explicit shm_size on executor, then profile, then 1Gi x GPU count."""
    for res in (executor_resources, profile_resources):
        if res is not None and res.shm_size:
            return res.shm_size
    return f"{max(1, num_gpus)}Gi"


class JobBackend(Generic[ExecutionProviderConfigT, ExecutionProfileConfigT], ABC):
    BACKEND_NAME: str = "generic_backend"

    def __init__(
        self,
        nmp_sdk: NeMoPlatform,
        execution_profile_config: ExecutionProfileConfigT,
        profile_name: str,
    ):
        self._nmp_sdk = nmp_sdk
        self._execution_profile_config = execution_profile_config
        self._profile_name = profile_name
        self.init()

    def init(self): ...

    @abstractmethod
    def schedule(
        self,
        executor_config: ExecutionProviderConfigT,
        step: PlatformJobStepWithContext,
    ) -> JobUpdate: ...

    @abstractmethod
    def sync(self, step: PlatformJobStepWithContext) -> JobUpdate: ...

    @abstractmethod
    def cleanup_steps(self): ...

    @abstractmethod
    def shutdown(self): ...

    def __str__(self) -> str:
        return self.BACKEND_NAME

    def get_secrets_environment_variable_for_injection(self, step: PlatformJobStepWithContext) -> str:
        """Fetch the secret value for an inline secret environment variable.

        Args:
            step: The job step containing the environment variable reference.
        Returns:
            The environment variable to create to inform the job which secrets to fetch.
            It has the format "ENV_VAR1=workspace/secret_name1,ENV_VAR2=workspace/secret_name2".
        """
        env_var_str = ""
        for envvar in (step.step_spec.environment or []) if step.step_spec else []:
            if envvar.from_secret is not None:
                if env_var_str != "":
                    env_var_str += ","
                workspace, secret_name = get_entity_parts(envvar.from_secret.name, default_workspace=step.workspace)
                env_var_str += f"{envvar.name}={workspace}/{secret_name}"
        return env_var_str

    def get_step(self, job: str, step_name: str, workspace: str) -> PlatformJobStep:
        """Fetch the latest state of a job step from the NeMo Platform SDK."""
        return self._nmp_sdk.jobs.steps.retrieve(name=step_name, workspace=workspace, job=job)

    def get_step_safe(self, job: str, step_name: str, workspace: str) -> Optional[PlatformJobStep]:
        """Fetch the job step from the NeMo Platform SDK, or None if not found (e.g. 404, workspace deleted)."""
        try:
            return self.get_step(job=job, step_name=step_name, workspace=workspace)
        except NotFoundError:
            return None
        except Exception as e:
            raise e

    def check_step_is_terminal(self, job: str, step_name: str, workspace: str) -> bool:
        """Return True if the job step is terminal (cancelled/error/completed) or the step entity is not found (e.g. 404).

        Used by cleanup: when the entity is missing (e.g. workspace deleted) but the backend job is terminal and
        has our labels, we treat as terminal so we can clean up backend resources.
        """
        try:
            step = self.get_step(job=job, step_name=step_name, workspace=workspace)
            return step.status in ("cancelled", "error", "completed")
        except NotFoundError:
            # If the job step entity is not found, we treat it as terminal so cleanup can proceed.
            return True
        except Exception as e:
            raise RuntimeError(f"Could not fetch job step '{job}/{step_name}' to check if terminal") from e

    def check_job_is_terminal(self, job: str, workspace: str) -> bool:
        """Check if a job is in a terminal state."""
        try:
            job_response = self._nmp_sdk.jobs.retrieve(name=job, workspace=workspace)
            return job_response.status in ("cancelled", "error", "completed")
        except NotFoundError:
            # If the job entity is not found, we treat it as terminal so cleanup can proceed.
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to fetch job '{workspace}/{job}' to check if terminal") from e

    def check_step_ttl(self, step: PlatformJobStepWithContext, ttl_seconds: int) -> bool:
        # Ensure created_at is timezone-aware (assume UTC if naive)
        if step.created_at is None:
            return False

        created_at = step.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)

        return (created_at + datetime.timedelta(seconds=ttl_seconds)) < datetime.datetime.now(datetime.timezone.utc)

    @staticmethod
    def should_enforce_before_active_ttl(step: PlatformJobStepWithContext) -> bool:
        """Whether ttl_seconds_before_active applies. Skipped while resuming from pause."""
        if step.status is None:
            return True
        if isinstance(step.status, str):
            status_val = step.status
        elif isinstance(step.status, Enum):
            status_val = step.status.value
        else:
            status_val = str(step.status)
        return status_val != "resuming"

    def check_step_ttl_before_active(self, step: PlatformJobStepWithContext, ttl_seconds: int) -> bool:
        """Return True if the step exceeded ttl_seconds in a pre-active (pending) state.

        Uses max(created_at, updated_at) so pause/resume does not consume the scheduling
        budget; updated_at advances on lifecycle transitions (e.g. resume, PENDING).
        """
        if step.created_at is None:
            return False

        created_at = step.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)

        anchor = created_at
        if step.updated_at is not None:
            updated_at = step.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=datetime.timezone.utc)
            anchor = max(created_at, updated_at)

        return (anchor + datetime.timedelta(seconds=ttl_seconds)) < datetime.datetime.now(datetime.timezone.utc)

    def check_step_is_stale(self, step: PlatformJobStepWithContext) -> bool:
        """Check if all active tasks for a step have gone stale.

        Returns True if staleness_timeout_seconds is configured
        in the step lifecycle AND all active tasks have updated_at older than
        the staleness threshold.
        """
        staleness_timeout = step.step_spec.lifecycle.staleness_timeout_seconds if step.step_spec.lifecycle else None
        if not staleness_timeout or staleness_timeout <= 0:
            return False

        # Skip if step hasn't been alive long enough for staleness to be possible.
        if not self.check_step_ttl(step, staleness_timeout):
            return False

        try:
            tasks = self._nmp_sdk.jobs.tasks.list(
                name=step.name,
                job=step.job,
                workspace=step.workspace,
            )
        except Exception:
            logger.warning("Failed to fetch tasks for staleness check", extra={"step": step.name, "job": step.job})
            return False

        active_tasks = [t for t in tasks.data if t.status == "active"]
        if not active_tasks:
            return False

        now = datetime.datetime.now(datetime.timezone.utc)
        threshold = datetime.timedelta(seconds=staleness_timeout)

        for task in active_tasks:
            if task.updated_at is None:
                logger.error("Task missing updated_at timestamp", extra={"task": task.name, "step": step.name})
                return False
            updated_at = task.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=datetime.timezone.utc)
            if (now - updated_at) < threshold:
                return False

        logger.warning(
            "Stale job step detected, job step will be killed",
            extra={
                "step": step.name,
                "job": step.job,
                "staleness_timeout_seconds": staleness_timeout,
                "num_stale_tasks": len(active_tasks),
            },
        )
        return True


def staleness_error_message(staleness_timeout: int) -> str:
    return f"Job terminated: no task updates received within {staleness_timeout}s staleness threshold"


def extract_provider_profile(step: PlatformJobStepWithContext) -> tuple[str, str]:
    profile = DEFAULT_PROFILE
    if isinstance(step.step_spec.executor, str):
        provider = step.step_spec.executor
    else:
        provider = step.step_spec.executor.provider or DEFAULT_PROVIDER
        profile = step.step_spec.executor.profile or profile

    return provider, profile


def get_logs_endpoint_from_fileset(
    platform_config: PlatformConfig, workspace: str, fileset_id: str, loopback_address: str | None = None
) -> str:
    """Get the OTLP logs endpoint URL for a fileset.

    Args:
        platform_config: Platform configuration containing files_url and loopback_address
        workspace: Workspace ID
        fileset_id: Fileset ID
        loopback_address: Optional override for loopback address replacement. If omitted, uses
            platform_config.loopback_address, then automatic loopback detection.

    Returns:
        Full OTLP logs endpoint URL with appropriate loopback address applied.
    """
    base_url = platform_config.get_service_url("files")

    # Use configured loopback_address, or fall back to automatic detection
    effective_override = loopback_address or platform_config.loopback_address or determine_loopback_override()

    if effective_override:
        for loopback in LOOPBACK_ADDRESSES:
            if loopback in base_url:
                base_url = base_url.replace(loopback, effective_override)
                break

    return f"{base_url}/apis/files/v2/workspaces/{workspace}/filesets/{fileset_id}/otlp/v1/logs"
