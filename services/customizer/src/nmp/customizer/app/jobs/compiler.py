# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job compiler - transforms CustomizationJobOutput into PlatformJobSpec."""

import logging

from nemo_platform import AsyncNeMoPlatform, NotFoundError
from nemo_platform.types.models.model_entity import ModelEntity
from nemo_platform_plugin.entities import EntityClient
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nmp.common.auth import AuthClient, auth_client_context
from nmp.common.entities.utils import parse_entity_ref
from nmp.common.jobs.exceptions import PlatformJobCompilationError
from nmp.common.jobs.image import get_qualified_image
from nmp.customizer.api.v2.jobs.schemas import (
    CustomizationJobInput,
    CustomizationJobOutput,
    DeploymentParams,
    DistillationTraining,
    LoRAParams,
    ValidationError,
)
from nmp.customizer.app.constants import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_OUTPUT_MODEL_PATH,
    DEFAULT_TEACHER_MODEL_PATH,
)
from nmp.customizer.app.jobs.file_io.schemas import (
    DownloadItem,
    FileIOTaskConfig,
    FileSetRef,
)
from nmp.customizer.app.jobs.model_entity.schemas import (
    DeploymentParameters as ModelEntityDeploymentParameters,
)
from nmp.customizer.app.jobs.model_entity.schemas import (
    ModelEntityTaskConfig,
)
from nmp.customizer.app.jobs.model_entity.schemas import (
    PEFTConfig as ModelEntityPEFTConfig,
)
from nmp.customizer.app.jobs.training.compiler import (
    _extract_model_name,
    _resolve_is_embedding_model,
    compile_training_step,
)
from nmp.customizer.config import config
from nmp.customizer.entities.values import FinetuningType
from nmp.customizer.platform_client import fetch_model_entity
from nmp.customizer.shared.app.jobs.compile_steps import (
    StoragePaths,
    TaskStepContainer,
    append_download_if_present,
    build_file_download_config,
    build_file_upload_config,
    build_output_fileset_metadata,
    compile_file_io_step,
    compile_model_entity_step,
    extract_model_fileset,
    get_base_environment,
    get_cpu_resources,
    resolve_deployment_config,
)

logger = logging.getLogger(__name__)

CPU_IMAGE_NAMESPACE = "nmp-cpu-tasks"
CPU_IMAGE = get_qualified_image(CPU_IMAGE_NAMESPACE)

GPU_IMAGE_NAMESPACE = "nmp-gpu-tasks"
GPU_IMAGE = get_qualified_image(GPU_IMAGE_NAMESPACE)

_STORAGE_PATHS = StoragePaths(
    model_path=DEFAULT_MODEL_PATH,
    dataset_path=DEFAULT_DATASET_PATH,
    output_model_path=DEFAULT_OUTPUT_MODEL_PATH,
    teacher_model_path=DEFAULT_TEACHER_MODEL_PATH,
)

_FILE_IO_CONTAINER = TaskStepContainer(
    image=CPU_IMAGE,
    command=["nemo-platform", "run", "task", "--task", "nmp.customizer.tasks.file_io"],
)

_MODEL_ENTITY_CONTAINER = TaskStepContainer(
    image=CPU_IMAGE,
    command=["nemo-platform", "run", "task", "--task", "nmp.customizer.tasks.model_entity"],
)


def _extract_model_uri(me: ModelEntity) -> str | None:
    return extract_model_fileset(me)


def _append_download_if_present(
    downloads: list[DownloadItem],
    fileset_name: str | None,
    dest: str,
    field_name: str,
) -> None:
    append_download_if_present(downloads, fileset_name, dest, field_name)


def _build_file_download_config(
    job_spec: CustomizationJobOutput,
    me: ModelEntity,
    teacher_me: ModelEntity | None = None,
) -> FileIOTaskConfig:
    teacher_fileset = extract_model_fileset(teacher_me) if teacher_me is not None else None

    return build_file_download_config(
        model_fileset=extract_model_fileset(me),
        dataset_path=job_spec.dataset,
        paths=_STORAGE_PATHS,
        teacher_fileset=teacher_fileset,
        require_model_fileset=False,
    )


def _build_output_fileset_metadata(me: ModelEntity) -> dict | None:
    return build_output_fileset_metadata(me)


def _build_file_upload_config(
    output_fileset_name: str,
    fileset_metadata: dict | None = None,
) -> FileIOTaskConfig:
    return build_file_upload_config(
        output_fileset_name=output_fileset_name,
        output_model_path=DEFAULT_OUTPUT_MODEL_PATH,
        fileset_metadata=fileset_metadata,
    )


def _build_model_entity_config(
    workspace: str, job_spec: CustomizationJobOutput, trust_remote_code: bool = False
) -> ModelEntityTaskConfig:
    base_model = _extract_model_name(job_spec)

    assert job_spec.output is not None, "output must be set by input-to-output transformer"
    training = job_spec.training

    peft_config: ModelEntityPEFTConfig | None = None
    if isinstance(training.peft, LoRAParams):
        peft_config = ModelEntityPEFTConfig(
            type=training.finetuning_type,
            alpha=training.peft.alpha,
            rank=training.peft.rank,
        )

    deployment_config = resolve_deployment_config(
        job_spec.deployment_config,
        ModelEntityDeploymentParameters,
    )

    return ModelEntityTaskConfig(
        name=job_spec.output.name,
        workspace=workspace,
        description="Customized model from job",
        fileset=FileSetRef(
            workspace=None,
            name=job_spec.output.fileset,
        ),
        base_model=base_model,
        model_entity=job_spec.model,
        peft=peft_config,
        trust_remote_code=trust_remote_code,
        deployment_config=deployment_config,
    )


async def _resolve_deployment_config_ref(
    config_ref: str,
    workspace: str,
    sdk: AsyncNeMoPlatform,
):
    """Resolve a ``name`` or ``workspace/name`` string to a ModelDeploymentConfig."""
    ref = parse_entity_ref(config_ref, default_workspace=workspace)
    try:
        return await sdk.inference.deployment_configs.retrieve(name=ref.name, workspace=ref.workspace)
    except NotFoundError as e:
        raise PlatformJobCompilationError(
            f"deployment_config references '{config_ref}' which does not exist in workspace '{ref.workspace}'."
        ) from e
    except Exception as e:
        raise PlatformJobCompilationError(f"Failed to resolve deployment_config '{config_ref}': {e}") from e


async def _validate_deployment_config(
    workspace: str,
    transformed_spec: CustomizationJobOutput,
    sdk: AsyncNeMoPlatform,
    auth_client: AuthClient,
) -> None:
    """Validate deployment_config consistency before training starts."""
    dc = transformed_spec.deployment_config

    if isinstance(dc, DeploymentParams):
        tcc = dc.tool_call_config
        if tcc and tcc.tool_call_plugin:
            if not await auth_client.has_permissions(workspace, ["models.tool-call-plugin.set"]):
                raise PlatformJobCompilationError(
                    "Insufficient permissions to set tool_call_plugin. "
                    "Requires the models.tool-call-plugin.set permission."
                )
        return

    if not isinstance(dc, str):
        return

    ft_type = transformed_spec.training.finetuning_type
    is_lora = ft_type == FinetuningType.LORA
    produces_new_model = ft_type in (FinetuningType.ALL_WEIGHTS, FinetuningType.LORA_MERGED)
    resolved_config = await _resolve_deployment_config_ref(dc, workspace, sdk)

    if is_lora and resolved_config.nim_deployment and resolved_config.nim_deployment.lora_enabled is False:
        raise PlatformJobCompilationError(
            f"deployment_config references '{dc}' which has lora_enabled=false, "
            "but this is a LoRA training job. The deployment would not load LoRA adapters. "
            "Use a deployment config with lora_enabled=true, or provide inline deployment parameters."
        )

    if produces_new_model:
        output_name = transformed_spec.output.name
        try:
            existing_me = await sdk.models.retrieve(name=output_name, workspace=workspace)
        except NotFoundError:
            raise PlatformJobCompilationError(
                f"deployment_config cannot be a string reference ('{dc}') for {ft_type.value} training "
                "that creates a new model entity. The referenced config was created for a different model. "
                "Use inline deployment parameters (e.g., DeploymentParams(gpu=1, lora_enabled=True)) instead."
            )

        nim = resolved_config.nim_deployment
        config_targets_model = (resolved_config.model_entity_id == f"{existing_me.workspace}/{existing_me.name}") or (
            nim and nim.model_name == existing_me.name and nim.model_namespace == existing_me.workspace
        )
        if not config_targets_model:
            raise PlatformJobCompilationError(
                f"deployment_config references '{dc}' which targets a different model entity "
                f"than the output model '{existing_me.workspace}/{existing_me.name}'. "
                "The deployment config must target the same model entity being retrained, "
                "or use inline deployment parameters instead."
            )


async def platform_job_config_compiler(
    workspace: str,
    original_spec: CustomizationJobInput,
    transformed_spec: CustomizationJobOutput,
    entity_client: EntityClient,
    job_name: str | None,
    sdk: AsyncNeMoPlatform,
) -> PlatformJobSpec:
    """Compile customization job specs into a PlatformJobSpec."""
    logger.info(f"Compiling CustomizationJob to PlatformJobSpec: {transformed_spec.model_dump_json(indent=2)}")

    try:
        transformed_spec.validate_for_training()
    except ValidationError as e:
        raise PlatformJobCompilationError(str(e)) from e

    cpu_resources = get_cpu_resources(config)
    base_env = get_base_environment()

    me = await fetch_model_entity(transformed_spec.model, workspace, sdk)

    teacher_me: ModelEntity | None = None
    if isinstance(transformed_spec.training, DistillationTraining):
        try:
            teacher_me = await fetch_model_entity(transformed_spec.training.teacher_model, workspace, sdk)
        except ValueError as e:
            raise PlatformJobCompilationError(
                f"Teacher model '{transformed_spec.training.teacher_model}' not found. "
                "Verify the teacher model entity exists."
            ) from e
        except PermissionError as e:
            raise PlatformJobCompilationError(
                f"Access denied to teacher model '{transformed_spec.training.teacher_model}'."
            ) from e

    auth_client = auth_client_context.get()
    if auth_client is None:
        raise PlatformJobCompilationError("No auth context available; cannot validate deployment config permissions.")
    await _validate_deployment_config(workspace, transformed_spec, sdk, auth_client)

    file_io_download_config = _build_file_download_config(transformed_spec, me, teacher_me)
    is_embedding_model_flag = _resolve_is_embedding_model(me)

    if is_embedding_model_flag and transformed_spec.training.finetuning_type == FinetuningType.LORA:
        raise PlatformJobCompilationError(
            "NeMo Platform does not support unmerged LoRA for embedding models because the embedding NIM requires ONNX format, "
            "which cannot represent standalone adapters. "
            "Use peft with merge=True (lora_merged) or omit peft for all_weights training."
        )

    fileset_metadata = _build_output_fileset_metadata(me)
    file_io_upload_config = _build_file_upload_config(transformed_spec.output.fileset, fileset_metadata)

    trust_remote_code = me.trust_remote_code or False
    model_entity_config = _build_model_entity_config(workspace, transformed_spec, trust_remote_code)

    steps = [
        compile_file_io_step(
            "model-and-dataset-download",
            _FILE_IO_CONTAINER,
            cpu_resources,
            base_env,
            file_io_download_config,
        ),
        compile_training_step(
            transformed_spec,
            base_env,
            me,
            teacher_me=teacher_me,
        ),
        compile_file_io_step(
            "model-upload",
            _FILE_IO_CONTAINER,
            cpu_resources,
            base_env,
            file_io_upload_config,
        ),
        compile_model_entity_step(
            _MODEL_ENTITY_CONTAINER,
            cpu_resources,
            base_env,
            model_entity_config,
        ),
    ]

    return PlatformJobSpec(steps=steps)
