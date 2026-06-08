# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Training step compiler."""

import logging

from nemo_platform.types.models.model_entity import ModelEntity
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    DistributedGPUExecutionProviderSpec,
    EnvironmentVariable,
    EnvironmentVariableFromSecret,
    GPUExecutionProviderSpec,
    PlatformJobStep,
    ResourcesSpec,
    StepLifecycle,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.common.model_utils import is_embedding_model
from nmp.customizer.api.v2.jobs.schemas import (
    AnyTraining,
    CustomizationJobOutput,
    DistillationTraining,
    DPOTraining,
    LoRAParams,
    MLflowParams,
    WandBParams,
)
from nmp.customizer.app.constants import (
    DEFAULT_DATASET_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_TEACHER_MODEL_PATH,
    V4_MODEL_FOR_CAUSAL_LM_MAPPING_NAMES,
)
from nmp.customizer.app.jobs.training.schemas import (
    DistillationConfig,
    DPOConfig,
    LoRAConfig,
    MLflowConfig,
    ModelConfig,
    TrainingBackend,
    TrainingStepConfig,
    WandBConfig,
)
from nmp.customizer.config import config
from nmp.customizer.entities.values import Precision, TrainingType

logger = logging.getLogger(__name__)


def _resolve_is_embedding_model(me: ModelEntity) -> bool:
    """Resolve embedding flag while preserving compatibility with legacy specs."""
    if me.spec is None:
        return is_embedding_model(me.name)

    # Do not rely on `me.spec is not None` alone:
    # older persisted ModelSpec payloads may not include `is_embedding_model`.
    # Pydantic fills missing fields with the default (False), which would
    # incorrectly classify legacy embedding models as LLMs.
    model_fields_set = getattr(me.spec, "model_fields_set", getattr(me.spec, "__fields_set__", set()))
    if "is_embedding_model" not in model_fields_set:
        return is_embedding_model(me.name)

    return me.spec.is_embedding_model or False


def _resolve_v4_compatible(me: ModelEntity) -> bool:
    """Check if the model requires transformers-v4-compatible checkpoint output."""
    if me.spec is None:
        return False
    checkpoint_model_name = getattr(me.spec, "checkpoint_model_name", None)
    is_v4_compatible = checkpoint_model_name in V4_MODEL_FOR_CAUSAL_LM_MAPPING_NAMES
    logger.info(f"Checkpoint model name {checkpoint_model_name} is v4 compatible: {is_v4_compatible}")
    return is_v4_compatible


def _resolve_custom_implementation_override(me: ModelEntity) -> bool:
    if me.spec is None:
        return False

    checkpoint_model_name = getattr(me.spec, "checkpoint_model_name", None)
    if checkpoint_model_name == "NemotronHForCausalLM" and getattr(me.spec, "moe_config", None) is None:
        # V2 Model is being used, v3 uses MoE - However V2 gets recognized as V3 and fails
        return True

    if (
        checkpoint_model_name == "MistralForCausalLM"
        and getattr(me.spec, "family", None) == "mistral"
        and getattr(me.spec, "is_chat", False)
    ):
        # Mistral 7b v0.3 Instruct has the custom tokenizer implementation fail with:
        """2026-03-02 18:35:51 | INFO | root | Using model config to instantiate tokenizer
        2026-03-02 18:35:53 | INFO | nemo_automodel._transformers.auto_tokenizer | Using custom tokenizer MistralCommonBackend for model type 'mistral'
        2026-03-02 18:35:53 | WARNING | nemo_automodel._transformers.tokenization.tokenization_mistral_common | Multiple tokenizer files found in directory: /var/run/scratch/job/model. Using tokenizer.model.v3.
        Instantiation failed for `ColumnMappedTextInstructionDataset`
        Accepted signature : (path_or_dataset_id: Union[str, List[str]], column_mapping: Dict[str, str], tokenizer, *, split: Optional[str] = 'train', name: Optional[str] = None, answer_only_loss_mask: bool = True, seq_length: Optional[int] = None, padding: Union[str, bool] = 'do_not_pad', truncation: Union[str, bool] = 'do_not_truncate', limit_dataset_samples: Optional[int] = None, use_hf_chat_template: bool = False) -> None
        Positional args    : ()
        Keyword args       : {   'answer_only_loss_mask': True,
            'column_mapping': {'answer': 'completion', 'question': 'prompt'},
            'padding': 'do_not_pad',
            'path_or_dataset_id': '/run/scratch/job/training/dataset/train.jsonl',
            'seq_length': 1024,
            'split': 'train',
            'tokenizer': '******',
            'truncation': 'longest_first'}
        Exception          : piece id is out of range.
        """
        return True

    return False


def compile_training_step(
    job_spec: CustomizationJobOutput,
    base_env: list[EnvironmentVariable],
    me: ModelEntity,
    teacher_me: ModelEntity | None = None,
) -> PlatformJobStep:
    """Compile job input to a PlatformJobStep for training.

    Args:
        job_spec: The customization job output specification.
        base_env: Base environment variables for the job step.
        me: The model entity being trained.
        teacher_me: Optional teacher model entity for knowledge distillation jobs.

    """
    job_spec.validate_for_training()
    backend = _determine_backend(job_spec)
    trust_remote_code = me.trust_remote_code or False
    chat_template = me.spec.chat_template if me.spec else None
    is_embedding_model = _resolve_is_embedding_model(me)
    override_custom_impl = _resolve_custom_implementation_override(me)
    v4_compatible = _resolve_v4_compatible(me)
    training = job_spec.training
    p = training.parallelism
    num_gpus_per_node = p.num_gpus_per_node

    training_config = TrainingStepConfig(
        backend=backend,
        model=_translate_model_config(
            job_spec,
            DEFAULT_MODEL_PATH,
            trust_remote_code=trust_remote_code,
            is_embedding_model=is_embedding_model,
            chat_template=chat_template,
            override_custom_impl=override_custom_impl,
            v4_compatible=v4_compatible,
        ),
        dataset=TrainingStepConfig.DatasetConfig(
            path=DEFAULT_DATASET_PATH,
        ),
        training=_translate_training_config(training, me, teacher_me=teacher_me),
        schedule=TrainingStepConfig.ScheduleConfig(
            epochs=training.epochs,
            max_steps=training.max_steps,
            val_check_interval=training.val_check_interval,
        ),
        batch=TrainingStepConfig.BatchConfig(
            global_batch_size=training.batch_size,
            micro_batch_size=training.micro_batch_size,
            sequence_packing=training.sequence_packing,
        ),
        optimizer=TrainingStepConfig.OptimizerConfig(
            learning_rate=training.learning_rate,
            min_learning_rate=training.min_learning_rate,
            weight_decay=training.weight_decay,
            beta1=training.adam_beta1,
            beta2=training.adam_beta2,
            warmup_steps=training.warmup_steps,
        ),
        parallelism=TrainingStepConfig.ParallelismConfig(
            num_nodes=p.num_nodes,
            num_gpus_per_node=num_gpus_per_node,
            tensor_parallel_size=p.tensor_parallel_size,
            pipeline_parallel_size=p.pipeline_parallel_size,
            context_parallel_size=p.context_parallel_size,
            expert_parallel_size=p.expert_parallel_size,
            sequence_parallel=p.sequence_parallel,
        ),
        integrations=_translate_integrations(job_spec),
        output_model=job_spec.output.name,
    )

    container = ContainerSpec(
        image=_get_training_image(training_config.backend),
        command=["python", "-m", "nmp.customizer.tasks.training"],
    )

    profile = (
        training.execution_profile
        if training.execution_profile is not None
        else config.default_training_execution_profile
    )

    if p.num_nodes > 1:
        logger.debug(f"Using distributed GPU executor: num_nodes={p.num_nodes}, num_gpus_per_node={num_gpus_per_node}")
        executor = DistributedGPUExecutionProviderSpec(
            provider="gpu_distributed",
            profile=profile,
            container=container,
            resources=ResourcesSpec(
                num_gpus=num_gpus_per_node,
                num_nodes=p.num_nodes,
            ),
        )
    else:
        logger.debug(f"Using single-node GPU executor: num_gpus={num_gpus_per_node}")
        executor = GPUExecutionProviderSpec(
            provider="gpu",
            profile=profile,
            container=container,
            resources=ResourcesSpec(
                num_gpus=num_gpus_per_node,
            ),
        )

    secret_envs = _collect_integration_secret_envs(job_spec)

    return PlatformJobStep(
        name="customization-training-job",
        executor=executor,
        environment=[*base_env, *secret_envs, EnvironmentVariable(name="HF_DATASETS_OFFLINE", value="1")],
        config=training_config.model_dump(mode="json"),
        lifecycle=StepLifecycle(staleness_timeout_seconds=config.training_staleness_timeout_seconds),
    )


def _translate_model_config(
    job_spec: CustomizationJobOutput,
    path: str,
    *,
    trust_remote_code: bool = False,
    is_embedding_model: bool = False,
    chat_template: str | None = None,
    override_custom_impl: bool = False,
    v4_compatible: bool = False,
) -> ModelConfig:
    """Translate job spec to internal ModelConfig."""
    training = job_spec.training
    return ModelConfig(
        path=path,
        name=_extract_model_name(job_spec),
        max_seq_length=training.max_seq_length,
        precision=training.precision,
        trust_remote_code=trust_remote_code,
        is_embedding_model=is_embedding_model,
        chat_template=chat_template,
        override_custom_impl=override_custom_impl,
        v4_compatible=v4_compatible,
    )


def _translate_training_config(
    training: AnyTraining,
    me: ModelEntity,
    teacher_me: ModelEntity | None = None,
) -> TrainingStepConfig.TrainingConfig:
    """Translate API training method to internal TrainingConfig.

    Args:
        training: The API training configuration.
        me: The primary model entity.
        teacher_me: Teacher model entity, populated for distillation jobs.
    """
    training_type = TrainingType(training.type)
    lora = _translate_lora_config(training.peft, me) if isinstance(training.peft, LoRAParams) else None

    dpo = None
    if isinstance(training, DPOTraining):
        dpo = DPOConfig(
            ref_policy_kl_penalty=training.ref_policy_kl_penalty,
            preference_average_log_probs=training.preference_average_log_probs,
            sft_average_log_probs=training.sft_average_log_probs,
            preference_loss_weight=training.preference_loss_weight,
            sft_loss_weight=training.sft_loss_weight,
            max_grad_norm=training.max_grad_norm,
        )

    kd = None
    if isinstance(training, DistillationTraining):
        teacher_trust_remote_code = (teacher_me.trust_remote_code or False) if teacher_me else False
        kd = DistillationConfig(
            teacher_model=ModelConfig(
                path=DEFAULT_TEACHER_MODEL_PATH,
                name=training.teacher_model,
                precision=Precision(training.teacher_precision),
                trust_remote_code=teacher_trust_remote_code,
            ),
            ratio=training.distillation_ratio,
            temperature=training.distillation_temperature,
        )

    return TrainingStepConfig.TrainingConfig(
        training_type=training_type,
        finetuning_type=training.finetuning_type,
        lora=lora,
        dpo=dpo,
        kd=kd,
    )


def _translate_lora_config(api_lora: LoRAParams, me: ModelEntity) -> LoRAConfig:
    """Translate API LoRAConfig to internal LoRAConfig."""
    lora = LoRAConfig(
        rank=api_lora.rank,
        alpha=api_lora.alpha,
        dropout=api_lora.dropout,
        target_modules=api_lora.target_modules,
        use_triton=True,
    )

    if not lora.target_modules:
        if me.spec and me.spec.checkpoint_model_name == "NemotronHForCausalLM":
            # Need to remove out_proj from the list of target modules
            modules = set()
            if me.spec.linear_layers:
                for ll in me.spec.linear_layers:
                    m = ll.name.split(".")[-1]
                    if m.endswith("proj"):
                        modules.add(f"*.{m}")
                modules.discard("*.out_proj")

            # In cases when model_spec has linear_layers as null, we need to set the target_modules to default
            # If target_modules is empty we get this error during training:
            # Expected match_all_linear to be true or target_modules/exclude_modules to be non-empty
            lora.target_modules = list(modules) if modules else ["*proj"]
        else:
            lora.target_modules = ["*proj"]
    return lora


def _translate_wandb_config(api_wandb: WandBParams | None) -> WandBConfig | None:
    """Translate API WandBParams to internal WandBConfig."""
    if api_wandb is None:
        return None

    return WandBConfig(
        project=api_wandb.project,
        name=api_wandb.name,
        entity=api_wandb.entity,
        tags=api_wandb.tags,
        notes=api_wandb.notes,
        base_url=api_wandb.base_url,
    )


def _translate_mlflow_config(api_mlflow: MLflowParams | None) -> MLflowConfig | None:
    """Translate API MLflowParams to internal MLflowConfig."""
    if api_mlflow is None:
        return None

    return MLflowConfig(
        experiment_name=api_mlflow.experiment_name,
        run_name=api_mlflow.run_name,
        tags=api_mlflow.tags,
        description=api_mlflow.description,
        tracking_uri=api_mlflow.tracking_uri,
    )


def _translate_integrations(job_spec: CustomizationJobOutput) -> TrainingStepConfig.IntegrationsConfig:
    """Translate API IntegrationsConfig to internal IntegrationsConfig."""
    if not job_spec.integrations:
        return TrainingStepConfig.IntegrationsConfig()

    return TrainingStepConfig.IntegrationsConfig(
        wandb=_translate_wandb_config(job_spec.integrations.wandb),
        mlflow=_translate_mlflow_config(job_spec.integrations.mlflow),
    )


def _collect_integration_secret_envs(job_input: CustomizationJobOutput) -> list[EnvironmentVariable]:
    """Collect secret environment variables from integration configs.

    Secrets are propagated via PlatformJobStep.environment (not config) so that
    the Jobs service can resolve secret references at runtime.
    """
    secret_envs: list[EnvironmentVariable] = []
    if not job_input.integrations:
        return secret_envs

    if job_input.integrations.wandb and job_input.integrations.wandb.api_key_secret:
        secret_envs.append(
            EnvironmentVariable(
                name="WANDB_API_KEY",
                from_secret=EnvironmentVariableFromSecret(
                    name=job_input.integrations.wandb.api_key_secret.root,
                ),
            )
        )

    return secret_envs


def _extract_model_name(job_spec: CustomizationJobOutput) -> str | None:
    """Extract the canonical model name from the model field for template lookup.

    The model name follows the pattern "workspace/name" (e.g., "meta/llama-3.1-8b-instruct")
    which matches the keys in DEFAULT_CHAT_TEMPLATES.
    """
    model = job_spec.model

    if "/" in model:
        logger.debug(f"Extracted model name from URN: {model}")
        return model

    return None


def _determine_backend(job_spec: CustomizationJobOutput) -> TrainingBackend:
    """Determine which backend to use based on the training type.

    Decision logic:
    1. DPO → nemo_rl (RL training requires nemo-rl library)
    2. Everything else (SFT, Distillation) → automodel
    """
    if TrainingType(job_spec.training.type) == TrainingType.DPO:
        return TrainingBackend.NEMO_RL

    return TrainingBackend.AUTOMODEL


def _get_training_image(backend: TrainingBackend) -> str:
    """Get the training image for a backend."""
    if backend == TrainingBackend.AUTOMODEL:
        return config.training_automodel_image or get_qualified_image("customizer-automodel")
    elif backend == TrainingBackend.NEMO_RL:
        return config.training_rl_image or get_qualified_image("customizer-rl")
    else:
        raise ValueError(f"No training image configured for backend: {backend}")
