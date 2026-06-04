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
from nemo_safe_synthesizer.config.external_results import SafeSynthesizerSummary
from nemo_safe_synthesizer.config.job import SafeSynthesizerJobConfig as SafeSynthesizerJobConfigInternal
from nemo_safe_synthesizer.config.job import SafeSynthesizerParameters as SafeSynthesizerParametersInternal
from nemo_safe_synthesizer.config.replace_pii import PiiReplacerConfig
from nemo_safe_synthesizer_plugin.config import config
from nemo_safe_synthesizer_plugin.runtime import runtime_task_command
from nmp.common.jobs.exceptions import PlatformJobCompilationError
from nmp.common.jobs.image import get_qualified_image
from pydantic import Field, model_validator
from pydantic.json_schema import SkipJsonSchema

logger = logging.getLogger(__name__)


class SafeSynthesizerParameters(SafeSynthesizerParametersInternal):
    """NMP-facing Safe Synthesizer parameters with SDK convenience flags."""

    enable_synthesis: bool = Field(
        default=True,
        exclude=True,
        description="Whether to run LLM training and generation phases. "
        "When false the task only performs PII replacement and returns the processed data.",
    )
    enable_replace_pii: bool = Field(
        default=True,
        exclude=True,
        description="Whether to run the default PII replacement pipeline before synthesis.",
    )


class SafeSynthesizerJobConfig(SafeSynthesizerJobConfigInternal):
    """NMP-facing Safe Synthesizer job config with SDK convenience flags."""

    __doc__ = SafeSynthesizerJobConfigInternal.__doc__

    config: SafeSynthesizerParameters = Field(
        description="The Safe Synthesizer parameters configuration.",
    )
    pretrained_model_job: str | None = Field(
        default=None,
        description="Optional previous NSS job whose stored adapter artifact is reused for generation-only "
        "synthesis. Accepts either '<job>' in the current workspace or '<workspace>/<job>'. "
        "The plugin resolves the prior job's 'adapter' result from Files.",
    )

    enable_synthesis: SkipJsonSchema[bool] = Field(
        default=True,
        description="Whether to run LLM training and generation phases. "
        "When False the task only performs PII replacement and returns the processed data.",
    )

    @model_validator(mode="before")
    @classmethod
    def _apply_enable_flags(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        cfg = data.get("config")
        if not isinstance(cfg, dict):
            return data
        enable_synthesis = cfg.pop("enable_synthesis", True)
        enable_replace_pii = cfg.pop("enable_replace_pii", True)
        data.setdefault("enable_synthesis", enable_synthesis)
        if not enable_replace_pii:
            cfg["replace_pii"] = None
        return data

    @model_validator(mode="before")
    @classmethod
    def _apply_pii_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        config_data = data.get("config")
        if not isinstance(config_data, dict):
            return data
        replace_pii = config_data.get("replace_pii")
        if not isinstance(replace_pii, dict) or "steps" in replace_pii:
            return data

        def deep_update(base: dict, override: dict) -> dict:
            for k, v in override.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    deep_update(base[k], v)
                else:
                    base[k] = v
            return base

        default = PiiReplacerConfig.get_default_config().model_dump()
        deep_update(default, replace_pii)
        config_data["replace_pii"] = default
        return data

    @model_validator(mode="before")
    @classmethod
    def _validate_pretrained_model_source(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if not data.get("pretrained_model_job"):
            return data
        config_data = data.get("config")
        training_data = config_data.get("training") if isinstance(config_data, dict) else None
        if isinstance(training_data, dict) and "pretrained_model" in training_data:
            raise ValueError("Use either 'pretrained_model_job' or 'config.training.pretrained_model', not both.")
        return data


def parse_pretrained_model_job_ref(job_ref: str, workspace_fallback: str) -> tuple[str, str]:
    """Parse a previous NSS job reference.

    Accepts either "<job>" in the current workspace or "<workspace>/<job>".
    """
    parts = job_ref.split("/", 1)
    if len(parts) == 1:
        workspace = workspace_fallback
        job_name = parts[0]
    else:
        workspace, job_name = parts

    if not workspace or not job_name:
        raise PlatformJobCompilationError(
            f"Invalid pretrained_model_job format: {job_ref!r}. Expected '<job>' or '<workspace>/<job>'."
        )
    return workspace, job_name


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
            config=job_config.model_dump(),
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
        config=job_config.model_dump(),
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
