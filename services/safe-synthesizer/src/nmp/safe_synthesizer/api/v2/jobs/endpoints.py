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
    job_route_factory,
)
from nemo_safe_synthesizer.config.external_results import SafeSynthesizerSummary
from nemo_safe_synthesizer.config.job import SafeSynthesizerJobConfig as SafeSynthesizerJobConfigInternal
from nemo_safe_synthesizer.config.replace_pii import PiiReplacerConfig
from nmp.common.jobs.exceptions import PlatformJobCompilationError
from nmp.common.jobs.image import get_qualified_image
from nmp.safe_synthesizer.config import config
from pydantic import Field, model_validator

logger = logging.getLogger(__name__)


class SafeSynthesizerJobConfig(SafeSynthesizerJobConfigInternal):
    # Applies default PII replacement config when ``steps`` is omitted.
    # The upstream ``PiiReplacerConfig`` requires ``steps`` (min_length=1).
    # SDK callers that use ``with_replace_pii()`` without explicit steps would
    # otherwise get a 422.  This validator injects the server-side defaults
    # before Pydantic validates the nested model.
    __doc__ = SafeSynthesizerJobConfigInternal.__doc__

    enable_synthesis: bool = Field(
        default=True,
        description="Whether to run LLM training and generation phases. "
        "When False the task only performs PII replacement and returns the processed data.",
    )

    @model_validator(mode="before")
    @classmethod
    def _apply_enable_flags(cls, data: Any) -> Any:
        """Honor enable_synthesis and enable_replace_pii flags from the SDK builder.

        These flags are not part of the NSS package's SafeSynthesizerParameters and
        would be silently dropped during nested config validation.  We lift them to
        the top level of the job config so the task container can read them from the
        stored JSON, and apply ``replace_pii=None`` explicitly when PII replacement
        is disabled (popping the key would let the default_factory re-enable it).
        """
        if not isinstance(data, dict):
            return data
        cfg = data.get("config")
        if not isinstance(cfg, dict):
            return data
        enable_synthesis = cfg.pop("enable_synthesis", True)
        enable_replace_pii = cfg.pop("enable_replace_pii", True)
        # Lift enable_synthesis to the top level so model_dump() includes it and
        # the task container can read it before calling SafeSynthesizerJobConfig.model_validate().
        data.setdefault("enable_synthesis", enable_synthesis)
        if not enable_replace_pii:
            # Explicitly set to None rather than popping — popping would cause
            # SafeSynthesizerParameters.replace_pii's default_factory to re-enable PII.
            cfg["replace_pii"] = None
        return data

    @model_validator(mode="before")
    @classmethod
    def _apply_pii_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        config = data.get("config")
        if not isinstance(config, dict):
            return data
        replace_pii = config.get("replace_pii")
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
        config["replace_pii"] = default
        return data


def _create_job_step(job_config: SafeSynthesizerJobConfig, environment: list[EnvironmentVariable]) -> PlatformJobStep:
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

    s = PlatformJobStep(
        name="safe-synthesizer",
        executor=GPUExecutionProviderSpec(
            provider="gpu",
            profile=config.job_executor_profile,
            container=ContainerSpec(
                image=get_qualified_image("nmp-gpu-tasks"),
                entrypoint=config.entrypoint,
            ),
            resources=resources,
        ),
        config=job_config.model_dump(),
        environment=environment,
    )
    return s


async def job_config_compiler(
    workspace: str,
    original_spec: SafeSynthesizerJobConfig,
    transformed_spec: SafeSynthesizerJobConfig,
    entity_client: EntityClient,
    job_name: str | None,
    sdk: AsyncNeMoPlatform,
) -> PlatformJobSpec:
    """Compile safe-synthesizer job config into a PlatformJobSpec.

    Args:
        workspace: The workspace for this job.
        original_spec: The user-provided input specification.
        transformed_spec: The spec after applying the input-to-output transformer.
            Since no transformer is configured for safe-synthesizer, original_spec
            and transformed_spec are identical.
        entity_client: Entity client for lookups.
        job_name: The resolved job name (user-provided or auto-generated).
        sdk: SDK instance for building inference gateway URLs.
    """
    steps = []

    # Validate user has access to the data source fileset before building the job spec.
    # Without this check, a user could reference a fileset in another workspace and
    # the error would only surface at task runtime.
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
    except PermissionDeniedError:
        raise PermissionError(f"Access denied to fileset {fileset_name!r} in workspace {ds_workspace!r}") from None

    environment = [
        EnvironmentVariable(name="DATA_SOURCE", value=transformed_spec.data_source),
    ]

    # Configure column classification via Inference Gateway
    # The provider reference is stored in the PII replacer config under globals.classify
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
        logger.info(f"Configured NIM endpoint URL: {nim_endpoint_url} (provider: {classify_model_provider})")

    # Configure HuggingFace token via platform secrets
    # The secret must exist in the same workspace as the job
    if transformed_spec.hf_token_secret:
        environment.append(
            EnvironmentVariable(
                name="HF_TOKEN", from_secret=EnvironmentVariableFromSecret(name=transformed_spec.hf_token_secret)
            )
        )

    nss_step = _create_job_step(job_config=transformed_spec, environment=environment)

    if transformed_spec.config:
        steps.append(nss_step)

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
