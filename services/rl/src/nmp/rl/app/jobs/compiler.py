# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job compiler — transforms ``RlJobOutput`` into a 4-step ``PlatformJobSpec``.

Steps mirror unsloth/automodel:

1. file_io download    — pull model fileset + preference dataset to the PVC
2. training            — Ray DPO step (single-node GPU or multi-node distributed)
3. file_io upload      — push the trained checkpoint to a new fileset
4. model_entity        — create the output ``ModelEntity`` referencing it

The training step's executor is selected by ``parallelism.num_nodes``:
``num_nodes == 1`` means a single-node ``GPUExecutionProviderSpec``;
``num_nodes > 1`` means a multi-node ``DistributedGPUExecutionProviderSpec``.
Multi-node additionally requires a shared filesystem for Ray's
cross-node ENDED/barrier coordination, enforced here with a fail-fast.
"""

from __future__ import annotations

import logging

from nemo_platform import AsyncNeMoPlatform
from nemo_platform.types.models.model_entity import ModelEntity
from nemo_platform_plugin.integrations import IntegrationsSpec
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    DistributedGPUExecutionProviderSpec,
    EnvironmentVariable,
    GPUExecutionProviderSpec,
    PlatformJobSpec,
    PlatformJobStep,
    ResourcesLimitsSpec,
    ResourcesRequestsSpec,
    ResourcesSpec,
)
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from nmp.common.jobs.constants import DEFAULT_JOB_STORAGE_PATH, PERSISTENT_JOB_STORAGE_PATH_ENVVAR
from nmp.customization_common.integrations import (
    collect_integration_secret_envs,
    warn_incomplete_integrations,
)
from nmp.customization_common.schemas.file_io import (
    DownloadItem,
    FileIOTaskConfig,
    FileSetRef,
    UploadItem,
)
from nmp.customization_common.schemas.model_entity import ModelEntityTaskConfig
from nmp.customization_common.service.platform_client import fetch_model_entity
from nmp.rl.app.constants import (
    BASE_LOG_DIR_ENVVAR,
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_OUTPUT_MODEL_PATH,
)
from nmp.rl.app.jobs.training.schemas import (
    DPOConfig,
    MLflowConfig,
    ModelConfig,
    TrainingBackend,
    TrainingStepConfig,
    WandBConfig,
)
from nmp.rl.config import config
from nmp.rl.entities.values import FinetuningType, TrainingType
from nmp.rl.images import RL_PYTHON_ENTRYPOINT, get_tasks_image, get_training_image
from nmp.rl.schemas import DPOTraining, RlJobOutput

logger = logging.getLogger(__name__)


def _get_cpu_resources() -> ResourcesSpec:
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


def _base_environment() -> list[EnvironmentVariable]:
    return [EnvironmentVariable(name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR, value=DEFAULT_JOB_STORAGE_PATH)]


def _require_fileset(name: str | None, *, label: str) -> str:
    if not name or not str(name).strip():
        raise PlatformJobCompilationError(
            f"{label} has no fileset attached. Attach a platform FileSet (workspace/name) before training.",
        )
    return str(name)


def _build_download_config(job_spec: RlJobOutput, me: ModelEntity, *, workspace: str) -> FileIOTaskConfig:
    model_fileset = _require_fileset(me.fileset, label=f"Model '{me.workspace}/{me.name}'")
    # The model ref is already workspace-qualified (from me.fileset), but the
    # dataset ref comes straight from the submitted spec and may be a bare name
    # ("dpo-data"). The file_io download step's SDK list() requires an explicit
    # workspace, so qualify it with the job's workspace when unset.
    dataset_ref = FileSetRef.model_validate(job_spec.dataset)
    if dataset_ref.workspace is None:
        dataset_ref = FileSetRef(workspace=workspace, name=dataset_ref.name)
    return FileIOTaskConfig(
        download=[
            DownloadItem(src=FileSetRef.model_validate(model_fileset), dest=DEFAULT_MODEL_PATH),
            DownloadItem(src=dataset_ref, dest=DEFAULT_DATASET_PATH),
        ],
    )


def _build_upload_config(output_fileset_name: str) -> FileIOTaskConfig:
    return FileIOTaskConfig(
        upload=[UploadItem(src=DEFAULT_OUTPUT_MODEL_PATH, dest=FileSetRef(workspace=None, name=output_fileset_name))],
    )


def _build_model_entity_config(
    workspace: str, job_spec: RlJobOutput, *, trust_remote_code: bool
) -> ModelEntityTaskConfig:
    # DPO is full-weight: no PEFT/adapter config.
    return ModelEntityTaskConfig(
        name=job_spec.output.name,
        workspace=workspace,
        description=f"DPO-trained model from nmp-rl job ({job_spec.model})",
        fileset=FileSetRef(workspace=None, name=job_spec.output.fileset),
        model_entity=job_spec.model,
        base_model=job_spec.model,
        peft=None,
        trust_remote_code=trust_remote_code,
        deployment_config=None,
    )


def _build_integrations_config(integrations: IntegrationsSpec | None) -> TrainingStepConfig.IntegrationsConfig:
    """Map the public ``IntegrationsSpec`` onto the training step's ``IntegrationsConfig``.

    Without this the step config carries the empty default and the driver's
    ``build_wandb_config`` / ``build_mlflow_config`` (and the backend's MLFLOW_URI
    setup) all see ``None`` — silently disabling W&B/MLflow even when the job
    requested them. Field names line up except MLflow's run name (public ``name``
    maps to the step's ``run_name``). Secrets (``api_key_secret``) are NOT copied
    here; ``collect_integration_secret_envs`` injects them as env vars in
    :func:`_build_training_step`.
    """
    if integrations is None:
        return TrainingStepConfig.IntegrationsConfig()

    wandb_cfg = None
    if integrations.wandb is not None:
        w = integrations.wandb
        wandb_cfg = WandBConfig(
            project=w.project,
            name=w.name,
            entity=w.entity,
            tags=w.tags,
            notes=w.notes,
            base_url=w.base_url,
        )

    mlflow_cfg = None
    if integrations.mlflow is not None:
        m = integrations.mlflow
        mlflow_cfg = MLflowConfig(
            experiment_name=m.experiment_name,
            run_name=m.name,
            tags=m.tags,
            description=m.description,
            tracking_uri=m.tracking_uri,
        )

    return TrainingStepConfig.IntegrationsConfig(wandb=wandb_cfg, mlflow=mlflow_cfg)


def _build_training_step_config(job_spec: RlJobOutput, *, trust_remote_code: bool) -> TrainingStepConfig:
    """Map the canonical DPO spec onto the backend-agnostic step config."""
    t: DPOTraining = job_spec.training
    p = t.parallelism
    return TrainingStepConfig(
        backend=TrainingBackend.NEMO_RL,
        model=ModelConfig(
            path=DEFAULT_MODEL_PATH,
            name=job_spec.model,
            max_seq_length=t.max_seq_length,
            trust_remote_code=trust_remote_code,
        ),
        dataset=TrainingStepConfig.DatasetConfig(path=DEFAULT_DATASET_PATH),
        training=TrainingStepConfig.TrainingConfig(
            training_type=TrainingType.DPO,
            finetuning_type=FinetuningType.ALL_WEIGHTS,
            dpo=DPOConfig(
                ref_policy_kl_penalty=t.ref_policy_kl_penalty,
                preference_average_log_probs=t.preference_average_log_probs,
                sft_average_log_probs=t.sft_average_log_probs,
                preference_loss_weight=t.preference_loss_weight,
                sft_loss_weight=t.sft_loss_weight,
                max_grad_norm=t.max_grad_norm,
            ),
        ),
        schedule=TrainingStepConfig.ScheduleConfig(
            epochs=t.epochs,
            max_steps=t.max_steps,
            val_check_interval=t.val_check_interval,
            val_at_end=t.val_at_end,
            keep_top_k=t.keep_top_k,
        ),
        batch=TrainingStepConfig.BatchConfig(global_batch_size=t.batch_size, micro_batch_size=t.micro_batch_size),
        optimizer=TrainingStepConfig.OptimizerConfig(
            optimizer_type=t.optimizer_type,
            learning_rate=t.learning_rate,
            min_learning_rate=t.min_learning_rate,
            weight_decay=t.weight_decay,
            beta1=t.adam_beta1,
            beta2=t.adam_beta2,
            eps=t.adam_eps,
            warmup_steps=t.warmup_steps,
        ),
        parallelism=TrainingStepConfig.ParallelismConfig(
            num_nodes=p.num_nodes,
            num_gpus_per_node=p.num_gpus_per_node,
            tensor_parallel_size=p.tensor_parallel_size,
            pipeline_parallel_size=p.pipeline_parallel_size,
            context_parallel_size=p.context_parallel_size,
            sequence_parallel=p.sequence_parallel,
            activation_checkpointing=t.activation_checkpointing,
        ),
        # Carry W&B / MLflow config into the step so the driver actually enables
        # them; secrets are injected separately as env vars in _build_training_step.
        integrations=_build_integrations_config(job_spec.integrations),
        output_model=job_spec.output.name,
        seed=t.seed if t.seed is not None else 42,
    )


def _build_training_step(
    job_spec: RlJobOutput,
    base_env: list[EnvironmentVariable],
    *,
    trust_remote_code: bool,
    profile: str | None,
) -> PlatformJobStep:
    """Build the Ray DPO training step, selecting the executor by ``num_nodes``.

    Multi-node (``num_nodes > 1``) requires shared storage for Ray's cross-node
    ENDED/barrier coordination — fail fast when it is not configured.
    """
    p = job_spec.training.parallelism
    num_nodes = p.num_nodes
    num_gpus_per_node = p.num_gpus_per_node

    step_config = _build_training_step_config(job_spec, trust_remote_code=trust_remote_code)

    container = ContainerSpec(
        image=get_training_image(),
        entrypoint=RL_PYTHON_ENTRYPOINT,
        command=["-m", "nmp.rl.tasks.training"],
    )

    warn_incomplete_integrations(job_spec.integrations)
    environment = [*base_env, *collect_integration_secret_envs(job_spec.integrations)]

    executor: GPUExecutionProviderSpec | DistributedGPUExecutionProviderSpec
    if num_nodes > 1:
        shared_dir = config.multinode_shared_storage_path
        if not shared_dir:
            raise PlatformJobCompilationError(
                f"Multi-node NeMo-RL training (num_nodes={num_nodes}) requires a shared filesystem for Ray's "
                "cross-node coordination. Set NMP_RL_MULTINODE_SHARED_STORAGE_PATH to a path mounted on every "
                "node (e.g. an NFS mount) before submitting a multi-node job.",
            )
        # Ray's bootstrap writes the ENDED marker + barriers under BASE_LOG_DIR.
        environment = [*environment, EnvironmentVariable(name=BASE_LOG_DIR_ENVVAR, value=shared_dir)]
        executor = {
            "provider": "gpu_distributed",
            "container": container,
            "resources": ResourcesSpec(num_nodes=num_nodes, num_gpus=num_gpus_per_node),
        }
        resolved_profile = profile or config.default_distributed_execution_profile
    else:
        executor = {
            "provider": "gpu",
            "container": container,
            "resources": ResourcesSpec(num_gpus=num_gpus_per_node),
        }
        resolved_profile = profile or config.default_training_execution_profile

    if resolved_profile is not None:
        executor["profile"] = resolved_profile

    return PlatformJobStep(
        name="dpo-training",
        executor=executor,
        environment=environment,
        config=step_config.model_dump(mode="json"),
    )


async def platform_job_config_compiler(
    workspace: str,
    job_spec: RlJobOutput,
    sdk: AsyncNeMoPlatform,
    *,
    job_name: str | None = None,
    profile: str | None = None,
) -> PlatformJobSpec:
    """Compile a canonical NeMo-RL job spec into a 4-step ``PlatformJobSpec``."""
    del job_name  # reserved for future scheduling decisions

    # Log only non-sensitive, high-level context. The full spec embeds
    # `integrations` (W&B / MLflow tokens and tracking URIs), so it must not be
    # dumped at INFO.
    p = job_spec.training.parallelism
    logger.info(
        "Compiling NeMo-RL DPO job to PlatformJobSpec: model=%s, dataset=%s, output=%s, "
        "num_nodes=%d, num_gpus_per_node=%d",
        job_spec.model,
        job_spec.dataset,
        job_spec.output.name,
        p.num_nodes,
        p.num_gpus_per_node,
    )

    me = await fetch_model_entity(job_spec.model, workspace, sdk)
    trust_remote_code = me.trust_remote_code or False

    cpu_resources = _get_cpu_resources()
    base_env = _base_environment()

    def _cpu_task_step(
        name: str, command: str, task_config: FileIOTaskConfig | ModelEntityTaskConfig
    ) -> PlatformJobStep:
        return PlatformJobStep(
            name=name,
            executor=CPUExecutionProviderSpec(
                provider="cpu",
                container=ContainerSpec(
                    image=get_tasks_image(),
                    entrypoint=RL_PYTHON_ENTRYPOINT,
                    command=["-m", command],
                ),
                resources=cpu_resources,
            ),
            environment=base_env,
            config=task_config.model_dump(mode="json"),
        )

    steps: list[PlatformJobStep] = [
        _cpu_task_step(
            "model-and-dataset-download",
            "nmp.rl.tasks.file_io",
            _build_download_config(job_spec, me, workspace=workspace),
        ),
        _build_training_step(job_spec, base_env, trust_remote_code=trust_remote_code, profile=profile),
        _cpu_task_step("model-upload", "nmp.rl.tasks.file_io", _build_upload_config(job_spec.output.fileset)),
        _cpu_task_step(
            "model-entity-creation",
            "nmp.rl.tasks.model_entity",
            _build_model_entity_config(workspace, job_spec, trust_remote_code=trust_remote_code),
        ),
    ]

    return PlatformJobSpec(steps=steps)
