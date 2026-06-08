# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job endpoints for the Safe Synthesizer service.

This module provides job management endpoints for running safe synthesis tasks
through the platform job system.
"""

import logging
from typing import Any
from urllib.parse import urlparse

from nemo_platform import AsyncNeMoPlatform, NotFoundError, PermissionDeniedError
from nemo_platform.filesets import FilesetPathError, parse_fileset_ref
from nemo_platform_plugin.entities import EntityClient
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    EnvironmentVariable,
    EnvironmentVariableFromSecret,
    FileResultSerializer,
    GPUExecutionProviderSpec,
    PlatformJobResultRoute,
    PlatformJobSpec,
    PlatformJobStep,
    PydanticResultSerializer,
    ResourcesLimitsSpec,
    ResourcesRequestsSpec,
    ResourcesSpec,
    SubprocessExecutionProviderSpec,
    job_route_factory,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from nemo_safe_synthesizer.config.external_results import SafeSynthesizerSummary
from nemo_safe_synthesizer_plugin.config import config
from nemo_safe_synthesizer_plugin.job_config import (
    SafeSynthesizerJobConfig,
    parse_pretrained_model_job_ref,
)
from nemo_safe_synthesizer_plugin.runtime import runtime_task_command
from nmp.common.jobs.exceptions import PlatformJobCompilationError

logger = logging.getLogger(__name__)


def _runtime_job_config(job_config: SafeSynthesizerJobConfig) -> dict[str, Any]:
    config = job_config.model_dump()
    if job_config.pretrained_model_job:
        training = config.get("config", {}).get("training")
        if isinstance(training, dict):
            training.pop("pretrained_model", None)
    return config


def _create_job_step(job_config: SafeSynthesizerJobConfig, environment: list[EnvironmentVariable]) -> PlatformJobStep:
    if config.job_mode == "subprocess-local":
        try:
            command = runtime_task_command(config)
        except RuntimeError as e:
            raise PlatformJobCompilationError(str(e)) from e

        return PlatformJobStep(
            name="safe-synthesizer",
            executor=SubprocessExecutionProviderSpec(
                provider="subprocess",
                profile=config.job_executor_profile,
                command=command,
            ),
            config=_runtime_job_config(job_config),
            environment=environment,
        )

    if config.job_mode != "container":
        raise PlatformJobCompilationError(f"Unsupported Safe Synthesizer job_mode: {config.job_mode!r}")

    resources = ResourcesSpec(
        limits=ResourcesLimitsSpec(
            memory=config.default_job_resource_memory_limit,
            cpu=config.default_job_resource_cpu_limit,
        ),
        requests=ResourcesRequestsSpec(
            memory=config.default_job_resource_memory_request,
            cpu=config.default_job_resource_cpu_request,
        ),
    )
    return PlatformJobStep(
        name="safe-synthesizer",
        executor=GPUExecutionProviderSpec(
            provider="gpu",
            profile=config.job_executor_profile,
            container=ContainerSpec(
                image=get_qualified_image(config.container_image),
                entrypoint=config.entrypoint,
            ),
            resources=resources,
        ),
        config=_runtime_job_config(job_config),
        environment=environment,
    )


async def job_config_compiler(
    workspace: str,
    original_spec: SafeSynthesizerJobConfig,
    transformed_spec: SafeSynthesizerJobConfig,
    entity_client: EntityClient,
    job_name: str | None,
    sdk: AsyncNeMoPlatform,
) -> PlatformJobSpec:
    """Compile Safe Synthesizer job config into a platform job."""
    del original_spec, entity_client, job_name
    steps = []

    try:
        ds_workspace, fileset_name, _ = parse_fileset_ref(transformed_spec.data_source, workspace_fallback=workspace)
    except FilesetPathError as e:
        raise PlatformJobCompilationError(f"Invalid data_source format: {transformed_spec.data_source!r}") from e
    try:
        await sdk.files.filesets.retrieve(name=fileset_name, workspace=ds_workspace)
    except NotFoundError as e:
        raise PlatformJobCompilationError(
            f"Could not find fileset {fileset_name!r} in workspace {ds_workspace!r}"
        ) from e
    except PermissionDeniedError as e:
        raise PermissionError(f"Access denied to fileset {fileset_name!r} in workspace {ds_workspace!r}") from e

    environment = [
        EnvironmentVariable(name="DATA_SOURCE", value=transformed_spec.data_source),
    ]

    classify_model_provider = None
    if transformed_spec.config.replace_pii:
        classify_model_provider = transformed_spec.config.replace_pii.globals.classify.classify_model_provider
    if classify_model_provider:
        parts = classify_model_provider.split("/", 1)
        if len(parts) != 2:
            raise PlatformJobCompilationError(
                f"Invalid classify_model_provider format: '{classify_model_provider}'. "
                "Expected 'workspace/provider_name' format."
            )
        provider_workspace, provider_name = parts
        try:
            provider = await sdk.inference.providers.retrieve(provider_name, workspace=provider_workspace)
        except NotFoundError as e:
            raise PlatformJobCompilationError(
                f"Could not find model provider {provider_name!r} in workspace {provider_workspace!r}"
            ) from e
        except PermissionDeniedError as e:
            raise PlatformJobCompilationError(
                f"Failed to retrieve model provider {classify_model_provider!r}: Access denied to workspace {provider_workspace!r}"
            ) from e
        nim_endpoint_url = sdk.models.get_provider_route_openai_url(provider)
        parsed_url = urlparse(nim_endpoint_url)
        environment.append(EnvironmentVariable(name="CLASSIFY_LLM_ENDPOINT_PATH", value=parsed_url.path))
        logger.info("Configured NIM endpoint URL: %s (provider: %s)", nim_endpoint_url, classify_model_provider)

    if transformed_spec.hf_token_secret:
        environment.append(
            EnvironmentVariable(
                name="HF_TOKEN", from_secret=EnvironmentVariableFromSecret(name=transformed_spec.hf_token_secret)
            )
        )

    if transformed_spec.pretrained_model_job:
        model_workspace, model_job = parse_pretrained_model_job_ref(
            transformed_spec.pretrained_model_job, workspace_fallback=workspace
        )
        try:
            await sdk.jobs.results.retrieve(name="adapter", job=model_job, workspace=model_workspace)
        except NotFoundError as e:
            raise PlatformJobCompilationError(
                f"Could not find adapter result for NSS job {model_workspace}/{model_job!r}"
            ) from e
        except PermissionDeniedError as e:
            raise PlatformJobCompilationError(
                f"Failed to retrieve adapter result for NSS job {model_workspace}/{model_job!r}: "
                f"access denied to workspace {model_workspace!r}"
            ) from e

    if transformed_spec.config:
        steps.append(_create_job_step(job_config=transformed_spec, environment=environment))

    if not steps:
        raise PlatformJobCompilationError("No steps to run")
    return PlatformJobSpec(steps=steps)


router = job_route_factory(
    service_name="safe-synthesizer",
    job_type="SafeSynthesizer",
    job_input=SafeSynthesizerJobConfig,
    platform_job_config_compiler=job_config_compiler,
    job_result_routes=[
        PlatformJobResultRoute(
            name="summary",
            serializer=PydanticResultSerializer(model=SafeSynthesizerSummary),
        ),
        PlatformJobResultRoute(
            name="synthetic-data",
            serializer=FileResultSerializer(),
        ),
        PlatformJobResultRoute(
            name="evaluation-report",
            serializer=FileResultSerializer(),
        ),
        PlatformJobResultRoute(
            name="adapter",
            serializer=FileResultSerializer(),
        ),
    ],
)
