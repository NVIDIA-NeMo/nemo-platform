# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job compiler — transforms ``UnslothJobOutput`` into a 4-step ``PlatformJobSpec``.

Invoked from :meth:`UnslothJob.compile` via :mod:`nmp.unsloth.compile`.
The four steps mirror automodel:

1. file_io download   — pull model fileset + dataset fileset to the PVC
2. training            — GPU step running ``train_sft``
3. file_io upload      — push the saved checkpoint to a new fileset
4. model_entity        — create the output ``ModelEntity`` referencing it
"""

from __future__ import annotations

import logging

from nemo_platform import AsyncNeMoPlatform
from nemo_platform.types.models.model_entity import ModelEntity
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec, PlatformJobStep
from nmp.customizer.shared.app.jobs.compile_steps import (
    StoragePaths,
    TaskStepContainer,
    build_file_download_config,
    build_file_upload_config,
    compile_file_io_step,
    compile_model_entity_step,
    get_base_environment,
    get_cpu_resources,
    resolve_deployment_config,
)
from nmp.unsloth.app.constants import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_OUTPUT_MODEL_PATH,
)
from nmp.unsloth.app.jobs.file_io.schemas import FileSetRef
from nmp.unsloth.app.jobs.model_entity.schemas import (
    DeploymentParameters as ModelEntityDeploymentParameters,
)
from nmp.unsloth.app.jobs.model_entity.schemas import ModelEntityTaskConfig, PEFTConfig
from nmp.unsloth.app.jobs.training.compiler import compile_training_step
from nmp.unsloth.config import config
from nmp.unsloth.entities.values import FinetuningType
from nmp.unsloth.images import UNSLOTH_PYTHON_ENTRYPOINT, get_tasks_image
from nmp.unsloth.platform_client import fetch_model_entity
from nmp.unsloth.schemas import UnslothJobOutput

logger = logging.getLogger(__name__)

_STORAGE_PATHS = StoragePaths(
    model_path=DEFAULT_MODEL_PATH,
    dataset_path=DEFAULT_DATASET_PATH,
    output_model_path=DEFAULT_OUTPUT_MODEL_PATH,
)

_FILE_IO_CONTAINER = TaskStepContainer(
    image=get_tasks_image(),
    entrypoint=UNSLOTH_PYTHON_ENTRYPOINT,
    command=["-m", "nmp.unsloth.tasks.file_io"],
)

_MODEL_ENTITY_CONTAINER = TaskStepContainer(
    image=get_tasks_image(),
    entrypoint=UNSLOTH_PYTHON_ENTRYPOINT,
    command=["-m", "nmp.unsloth.tasks.model_entity"],
)


def _resolve_finetuning_type(spec: UnslothJobOutput) -> FinetuningType:
    """Map the plugin's flat ``finetuning_type`` + ``save_method`` onto the enum."""
    if spec.training.finetuning_type == "lora":
        if spec.output.save_method in {"merged_16bit", "merged_4bit"}:
            return FinetuningType.LORA_MERGED
        return FinetuningType.LORA
    return FinetuningType.ALL_WEIGHTS


def _build_peft_config(spec: UnslothJobOutput) -> PEFTConfig | None:
    if spec.training.finetuning_type != "lora":
        return None
    assert spec.training.lora is not None  # validated by UnslothJobInput
    return PEFTConfig(
        type=_resolve_finetuning_type(spec),
        rank=spec.training.lora.rank,
        alpha=spec.training.lora.alpha,
    )


def _build_file_download_config(
    job_spec: UnslothJobOutput,
    me: ModelEntity,
):
    """Compile the download step: model fileset + dataset fileset."""
    return build_file_download_config(
        model_fileset=me.fileset,
        dataset_path=job_spec.dataset.path,
        paths=_STORAGE_PATHS,
        require_model_fileset=True,
        model_entity_label=f"Model '{me.workspace}/{me.name}'",
    )


def _build_file_upload_config(output_fileset_name: str):
    """Compile the upload step."""
    return build_file_upload_config(
        output_fileset_name=output_fileset_name,
        output_model_path=DEFAULT_OUTPUT_MODEL_PATH,
    )


def _build_model_entity_config(
    workspace: str,
    job_spec: UnslothJobOutput,
    trust_remote_code: bool,
) -> ModelEntityTaskConfig:
    deployment_config = resolve_deployment_config(
        job_spec.deployment_config,
        ModelEntityDeploymentParameters,
    )

    return ModelEntityTaskConfig(
        name=job_spec.output.name,
        workspace=workspace,
        description=job_spec.output.description or "Customized model from unsloth job",
        fileset=FileSetRef(workspace=None, name=job_spec.output.fileset),
        model_entity=job_spec.model.name,
        base_model=job_spec.model.name,
        peft=_build_peft_config(job_spec),
        trust_remote_code=trust_remote_code,
        deployment_config=deployment_config,
    )


async def platform_job_config_compiler(
    workspace: str,
    job_spec: UnslothJobOutput,
    sdk: AsyncNeMoPlatform,
    job_name: str | None = None,
    profile: str | None = None,
) -> PlatformJobSpec:
    """Compile a canonical unsloth job spec into a 4-step ``PlatformJobSpec``."""
    del job_name  # reserved for future scheduling decisions (e.g. naming jobs)

    logger.info(f"Compiling Unsloth job to PlatformJobSpec: {job_spec.model_dump_json(indent=2)}")

    me = await fetch_model_entity(job_spec.model.name, workspace, sdk)

    cpu_resources = get_cpu_resources(config)
    base_env = get_base_environment()

    download_config = _build_file_download_config(job_spec, me)
    upload_config = _build_file_upload_config(job_spec.output.fileset)
    model_entity_config = _build_model_entity_config(
        workspace,
        job_spec,
        trust_remote_code=me.trust_remote_code or False,
    )

    steps: list[PlatformJobStep] = [
        compile_file_io_step(
            "model-and-dataset-download",
            _FILE_IO_CONTAINER,
            cpu_resources,
            base_env,
            download_config,
        ),
        compile_training_step(job_spec, base_env, profile=profile),
        compile_file_io_step(
            "model-upload",
            _FILE_IO_CONTAINER,
            cpu_resources,
            base_env,
            upload_config,
        ),
        compile_model_entity_step(
            _MODEL_ENTITY_CONTAINER,
            cpu_resources,
            base_env,
            model_entity_config,
        ),
    ]

    return PlatformJobSpec(steps=steps)
