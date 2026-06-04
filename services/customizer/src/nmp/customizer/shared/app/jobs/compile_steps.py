# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for compiling customization job file I/O and model-entity steps."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from nemo_platform.types.models.model_entity import ModelEntity
from nemo_platform_plugin.jobs.api_factory import (
    CPUExecutionProviderSpec,
    ContainerSpec,
    EnvironmentVariable,
    PlatformJobStep,
    ResourcesLimitsSpec,
    ResourcesRequestsSpec,
    ResourcesSpec,
)
from nmp.common.jobs.exceptions import PlatformJobCompilationError
from nmp.common.jobs.constants import DEFAULT_JOB_STORAGE_PATH, PERSISTENT_JOB_STORAGE_PATH_ENVVAR
from nmp.customizer.shared.app.jobs.file_io.schemas import (
    DownloadItem,
    FileIOTaskConfig,
    FileSetRef,
    UploadItem,
)
from nmp.customizer.shared.app.jobs.model_entity.schemas import ModelEntityTaskConfig

logger = logging.getLogger(__name__)


class JobResourceConfig(Protocol):
    """CPU/memory defaults used when compiling download/upload steps."""

    default_job_resource_cpu_limit: str
    default_job_resource_memory_limit: str
    default_job_resource_cpu_request: str
    default_job_resource_memory_request: str


@dataclass(frozen=True)
class StoragePaths:
    """PVC paths used across compile download/upload steps."""

    model_path: str
    dataset_path: str
    output_model_path: str
    teacher_model_path: str | None = None


@dataclass(frozen=True)
class TaskStepContainer:
    """Container invocation for a CPU task step."""

    image: str
    command: list[str]
    entrypoint: str | None = None


def get_cpu_resources(config: JobResourceConfig) -> ResourcesSpec:
    """Default CPU resources for download/upload/model-entity steps."""
    return ResourcesSpec(
        limits=ResourcesLimitsSpec(
            cpu=config.default_job_resource_cpu_limit,
            memory=config.default_job_resource_memory_limit,
        ),
        requests=ResourcesRequestsSpec(
            cpu=config.default_job_resource_cpu_request,
            memory=config.default_job_resource_memory_request,
        ),
    )


def get_base_environment() -> list[EnvironmentVariable]:
    """Base environment variables shared by all container task steps."""
    return [
        EnvironmentVariable(
            name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
            value=DEFAULT_JOB_STORAGE_PATH,
        ),
    ]


def extract_model_fileset(model_entity: ModelEntity) -> str | None:
    """Return the model entity fileset reference, if attached."""
    return model_entity.fileset if model_entity.fileset else None


def require_fileset_for_download(fileset_name: str | None, entity_label: str) -> str:
    """Require a platform fileset reference before compiling a download step."""
    if not fileset_name or not str(fileset_name).strip():
        raise PlatformJobCompilationError(
            f"{entity_label} has no fileset. "
            "Attach a platform FileSet (workspace/name) with model weights before running training.",
        )
    return str(fileset_name)


def append_download_if_present(
    downloads: list[DownloadItem],
    fileset_name: str | None,
    dest: str,
    field_name: str,
) -> None:
    """Append a download item when a fileset reference is present."""
    if not fileset_name:
        return
    fileset = FileSetRef.model_validate(fileset_name)
    downloads.append(DownloadItem(src=fileset, dest=dest))
    logger.info("Detected %s FileSet reference: %s", field_name, fileset)


def build_file_download_config(
    model_fileset: str | None,
    dataset_path: str,
    paths: StoragePaths,
    teacher_fileset: str | None = None,
    require_model_fileset: bool = False,
    model_entity_label: str = "Model",
    require_teacher_fileset: bool = False,
    teacher_entity_label: str = "Teacher model",
) -> FileIOTaskConfig:
    """Build a file_io download config for model, dataset, and optional teacher filesets."""
    downloads: list[DownloadItem] = []

    resolved_model_fileset = model_fileset
    if require_model_fileset:
        resolved_model_fileset = require_fileset_for_download(model_fileset, model_entity_label)

    append_download_if_present(
        downloads,
        fileset_name=resolved_model_fileset,
        dest=paths.model_path,
        field_name="model",
    )
    append_download_if_present(
        downloads,
        fileset_name=dataset_path,
        dest=paths.dataset_path,
        field_name="dataset",
    )

    if teacher_fileset is not None and paths.teacher_model_path is not None:
        resolved_teacher_fileset = teacher_fileset
        if require_teacher_fileset:
            resolved_teacher_fileset = require_fileset_for_download(teacher_fileset, teacher_entity_label)
        append_download_if_present(
            downloads,
            fileset_name=resolved_teacher_fileset,
            dest=paths.teacher_model_path,
            field_name="teacher_model",
        )

    return FileIOTaskConfig(download=downloads)


def build_output_fileset_metadata(model_entity: ModelEntity) -> dict | None:
    """Build tool_calling metadata to propagate from the source model entity."""
    if model_entity.spec is None:
        return None

    tool_calling: dict[str, Any] = {}

    if model_entity.spec.chat_template:
        tool_calling["chat_template"] = model_entity.spec.chat_template

    if model_entity.spec.tool_call_config:
        tcc = model_entity.spec.tool_call_config
        if tcc.tool_call_parser:
            tool_calling["tool_call_parser"] = tcc.tool_call_parser
        if tcc.tool_call_plugin:
            tool_calling["tool_call_plugin"] = tcc.tool_call_plugin
        if tcc.auto_tool_choice is not None:
            tool_calling["auto_tool_choice"] = tcc.auto_tool_choice

    return {"tool_calling": tool_calling} if tool_calling else None


def build_file_upload_config(
    output_fileset_name: str,
    output_model_path: str,
    fileset_metadata: dict | None = None,
) -> FileIOTaskConfig:
    """Build a file_io upload config for the training output directory."""
    return FileIOTaskConfig(
        upload=[
            UploadItem(
                src=output_model_path,
                dest=FileSetRef(workspace=None, name=output_fileset_name),
                metadata=fileset_metadata,
            ),
        ],
    )


def resolve_deployment_config(
    deployment_config: Any,
    deployment_parameters_type: type,
) -> str | Any | None:
    """Forward string refs or inline deployment parameters for model_entity tasks."""
    if isinstance(deployment_config, str):
        return deployment_config
    if deployment_config is not None:
        return deployment_parameters_type.model_validate(deployment_config.model_dump())
    return None


def _build_container_spec(container: TaskStepContainer) -> ContainerSpec:
    """Build a container spec, omitting entrypoint when not configured."""
    kwargs: dict[str, Any] = {
        "image": container.image,
        "command": container.command,
    }
    if container.entrypoint is not None:
        kwargs["entrypoint"] = container.entrypoint
    return ContainerSpec(**kwargs)


def compile_file_io_step(
    step_name: str,
    container: TaskStepContainer,
    cpu_resources: ResourcesSpec,
    base_env: list[EnvironmentVariable],
    task_config: FileIOTaskConfig,
) -> PlatformJobStep:
    """Compile a CPU file_io task step."""
    return PlatformJobStep(
        name=step_name,
        executor=CPUExecutionProviderSpec(
            provider="cpu",
            container=_build_container_spec(container),
            resources=cpu_resources,
        ),
        environment=base_env,
        config=task_config.model_dump(mode="json"),
    )


def compile_model_entity_step(
    container: TaskStepContainer,
    cpu_resources: ResourcesSpec,
    base_env: list[EnvironmentVariable],
    task_config: ModelEntityTaskConfig,
) -> PlatformJobStep:
    """Compile the model-entity creation CPU task step."""
    return PlatformJobStep(
        name="model-entity-creation",
        executor=CPUExecutionProviderSpec(
            provider="cpu",
            container=_build_container_spec(container),
            resources=cpu_resources,
        ),
        environment=base_env,
        config=task_config.model_dump(mode="json"),
    )
