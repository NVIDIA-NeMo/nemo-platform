# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""TrainingStepConfig -> NeMo RL YAML configuration generation.

This module handles configuration generation for DPO training type,
converting the internal TrainingStepConfig format to NeMo RL's YAML format.

Example of similar config but for AutoModel training
- services/automodel/src/nmp/automodel/tasks/training/backends/config.py
"""

import logging
from pathlib import Path
from typing import Any

from nmp.customizer.app.jobs.context import NMPJobContext
from nmp.customizer.tasks.training.chat_templates import resolve_chat_template
from nmp.customizer.tasks.training.datasets.preparation import (
    PreparedDataset,
    compute_val_check_interval,
    prepare_dataset,
)
from nmp.customizer.tasks.training.datasets.validation import DatasetValidator, detect_dpo_schema_name
from nmp.customizer.tasks.training.integrations import (
    build_mlflow_config,
    build_wandb_config,
)
from nmp.customizer.tasks.training.schemas import (
    DPOConfig,
    OptimizerType,
    TrainingStepConfig,
)

logger = logging.getLogger(__name__)


def compile_dpo_config(
    customizer_config: TrainingStepConfig,
    job_ctx: NMPJobContext,
) -> dict[str, Any]:
    """
    Compile TrainingStepConfig to NeMo RL DPO configuration dict.

    This transforms the standardized TrainingStepConfig into the format
    expected by NeMo RL's DPO training. The output dict will be serialized
    to YAML by the training runner.

    Args:
        customizer_config: The training step configuration
        job_ctx: Job context

    Returns:
        Configuration dict for NeMo RL DPO training

    Reference: https://github.com/NVIDIA-NeMo/RL/blob/main/examples/configs/dpo.yaml
    """
    cfg: dict[str, Any] = {}
    workspace_dir = Path(customizer_config.workspace_path)

    # === Dataset Preparation ===
    prepared = prepare_dataset(
        dataset_path=Path(customizer_config.dataset.path),
        output_dir=workspace_dir / "dataset",
    )
    logger.info(
        f"Prepared dataset: train={prepared.train_samples} samples, validation={prepared.validation_samples} samples"
    )
    validator = DatasetValidator(training_type=customizer_config.training.training_type)
    validator.validate_dataset(str(prepared.train_file))
    validator.validate_dataset(str(prepared.validation_file))
    logger.info("Validated datasets successfully")

    # === Training Schedule Calculations ===
    batch_size = customizer_config.batch.global_batch_size
    micro_batch_size = customizer_config.batch.micro_batch_size
    epochs = customizer_config.schedule.epochs

    # Compute steps per epoch (round up to ensure all samples are used)
    steps_per_epoch = max((prepared.train_samples + batch_size - 1) // batch_size, 1)
    total_steps = steps_per_epoch * epochs

    # Determine effective max_steps
    user_max_steps = customizer_config.schedule.max_steps
    if user_max_steps and user_max_steps > 0:
        max_steps = min(user_max_steps, total_steps)
    else:
        max_steps = total_steps

    # Compute validation interval
    val_check_interval = compute_val_check_interval(
        steps_per_epoch=steps_per_epoch,
        max_steps=max_steps,
        val_check_interval=customizer_config.schedule.val_check_interval,
    )

    logger.info(
        f"Training schedule: {prepared.train_samples} samples, batch_size={batch_size}, "
        f"steps_per_epoch={steps_per_epoch}, epochs={epochs}, max_steps={max_steps}, "
        f"val_period={val_check_interval}"
    )

    # === Get DPO Hyperparameters ===
    dpo_hp = customizer_config.training.dpo or DPOConfig()

    # Workaround to ensure validation metrics are available when checkpoints are saved:
    # NeMo RL saves a checkpoint on the last step regardless of save_period
    # (is_last_step flag). If that step isn't also a validation step, the
    # checkpoint lacks validation metrics and get_best_checkpoint_path() in
    # NeMo RL raises KeyError. We set val_period = val_check_interval (no
    # offset) so that validation and checkpoint saves land on the same steps.
    #
    # This works when max_steps is a multiple of val_period:
    #   val_check_interval=None -> val_period=steps_per_epoch=max_steps -> always aligned
    #   val_check_interval=0.5, 1500 samples, batch_size=16 -> steps=94, val_period=47 -> 94%47=0 -> aligned
    #
    # It can still misalign when max_steps is NOT a multiple of val_period:
    #   val_check_interval=0.5, 1505 samples, batch_size=16 -> steps=95, val_period=47 -> 95%47=1 -> misaligned
    #   val_check_interval=10, any dataset -> steps=94, val_period=10 -> 94%10=4 -> misaligned
    #
    # The fallback in find_best_checkpoint() in backend.py catches the KeyError
    # and returns the latest checkpoint, so training still succeeds.
    val_period = val_check_interval

    # === DPO Section ===
    cfg["dpo"] = {
        "max_num_epochs": epochs,
        "max_num_steps": max_steps,
        "steps_per_epoch": steps_per_epoch,
        "val_period": val_period,
        "val_batches": 0,  # Run the entire validation dataset
        "val_global_batch_size": batch_size,
        "val_micro_batch_size": micro_batch_size,
        "val_at_start": True,
        "seed": customizer_config.seed,
        # DPO-specific hyperparameters
        "reference_policy_kl_penalty": dpo_hp.ref_policy_kl_penalty,
        "preference_average_log_probs": dpo_hp.preference_average_log_probs,
        "sft_average_log_probs": dpo_hp.sft_average_log_probs,
        "preference_loss_weight": dpo_hp.preference_loss_weight,
        "sft_loss_weight": dpo_hp.sft_loss_weight,
    }

    # === Checkpointing Section ===
    # save_period must match val_period to ensure validation metrics are available
    # when checkpoints are saved (both use the same formula: (step + 1) % period == 0)
    # Note: NeMo RL still saves on last step regardless, which may not have val metrics.
    cfg["checkpointing"] = {
        "enabled": True,
        "checkpoint_dir": str(workspace_dir / "checkpoints"),
        "metric_name": "val:validation-default_loss",
        "higher_is_better": False,
        "keep_top_k": 1,
        "save_period": val_period,
        "checkpoint_must_save_by": None,
    }

    # === Policy Section ===
    model_path = customizer_config.model.path
    precision = _adapt_precision(customizer_config.model.precision)
    parallelism = customizer_config.parallelism

    # Resolve chat template with priority:
    # 1. Fileset metadata chat_template (from model entity spec)
    # 2. Custom template from DEFAULT_CHAT_TEMPLATES (if model.name matches)
    # 3. Model's built-in tokenizer template (fallback)
    chat_template = resolve_chat_template(
        model_path=model_path,
        model_name=customizer_config.model.name,
        user_template=customizer_config.model.chat_template,
    )

    cfg["policy"] = {
        "model_name": model_path,
        "tokenizer": {
            "name": model_path,
            "chat_template": chat_template,
        },
        "train_global_batch_size": batch_size,
        "train_micro_batch_size": micro_batch_size,
        "max_total_sequence_length": customizer_config.model.max_seq_length,
        "precision": precision,
        "fsdp_offload_enabled": False,
        "activation_checkpointing_enabled": False,
        # DTensor configuration
        # v2: Added propagation of sequence_parallel and context_parallel_size
        "dtensor_cfg": {
            "enabled": True,
            "cpu_offload": False,
            "sequence_parallel": parallelism.sequence_parallel,
            "activation_checkpointing": False,
            "tensor_parallel_size": parallelism.tensor_parallel_size,
            "context_parallel_size": parallelism.context_parallel_size,
            "custom_parallel_plan": None,
        },
        "dynamic_batching": {"enabled": False},
        "sequence_packing": _build_sequence_packing_config(customizer_config),
        "make_sequence_length_divisible_by": parallelism.tensor_parallel_size,
        "max_grad_norm": dpo_hp.max_grad_norm,
        # Optimizer and scheduler
        "optimizer": _build_optimizer_config(customizer_config),
        "scheduler": _build_scheduler_config(customizer_config, total_steps),
    }

    # === Data Section ===
    cfg["data"] = _build_data_config(customizer_config, prepared)

    # === Logger Section ===
    cfg["logger"] = _build_logger_config(customizer_config, job_ctx, workspace_dir)

    # === Cluster Section ===
    cfg["cluster"] = {
        "gpus_per_node": parallelism.num_gpus_per_node,
        "num_nodes": parallelism.num_nodes,
    }

    return cfg


def _build_data_config(customizer_config: TrainingStepConfig, prepared: PreparedDataset) -> dict[str, Any]:
    add_bos = customizer_config.dataset.add_bos if customizer_config.dataset.add_bos is not None else False
    add_eos = customizer_config.dataset.add_eos if customizer_config.dataset.add_eos is not None else True
    dpo_dataset_type = detect_dpo_schema_name(prepared.train_file)
    data_config = {
        "dataset_name": dpo_dataset_type,
        # "prompt_key": "prompt",
        # "chosen_key": "chosen_response",
        # "rejected_key": "rejected_response",
        "train_data_path": str(prepared.train_file),
        "val_data_path": str(prepared.validation_file),
        "max_input_seq_length": customizer_config.model.max_seq_length,
        "add_bos": add_bos,
        "add_eos": add_eos,
        "shuffle": False,
        "seed": customizer_config.seed,
        # Number of data loader workers.
        # Set to 8 or 10 for large batches to improve loading speed.
        # This saturates CPU threads without consuming too much memory
        # However, setting it too high might cause memory issues for long seqlens.
        "num_workers": 1,  # TODO: Make this configurable
    }

    return data_config


def _adapt_precision(precision: str | None) -> str:
    """

    Returns in the format that is expected by NeMo FW:
    ('transformer-engine', 'transformer-engine-float16', '16-true', '16-mixed',
    'bf16-true', 'bf16-mixed', '32-true', '64-true', 64, 32, 16, '64', '32', '16', 'bf16')
    """
    precision_map = {
        "bf16": "bfloat16",
        "bf16-mixed": "bfloat16",
        "fp16": "float16",
        "fp32": "float32",
        None: "bfloat16",  # Default
    }
    result = precision_map.get(precision)
    if result is None:
        logger.warning(f"Unknown precision '{precision}', defaulting to bfloat16")
        return "bfloat16"
    return result


def _build_sequence_packing_config(customizer_config: TrainingStepConfig) -> dict[str, Any]:
    """Build sequence packing configuration."""
    logger.warning("Sequence packing is currently not supported with DPO.")
    return {"enabled": False}

    ## TODO: uncomment below code when sequence packing is supported by nemo-rl
    ## Sequence packing is currently not supported with DPO. See https://github.com/NVIDIA-NeMo/RL/issues/719
    # if not customizer_config.batch.sequence_packing:
    #     return {"enabled": False}

    # return {
    #     "enabled": True,
    #     "train_mb_tokens": 2048,
    #     "logprob_mb_tokens": 2048,
    #     "algorithm": "modified_first_fit_decreasing",
    #     "sequence_length_round": 64,  # Hardware alignment
    # }


def _build_optimizer_config(customizer_config: TrainingStepConfig) -> dict[str, Any]:
    """Build optimizer configuration for NeMo RL.

    Supports:
    - AdamW (with weight decay)
    - Adam (without weight decay correction)

    The optimizer type is determined by the optimizer_type field in OptimizerConfig.
    """
    opt = customizer_config.optimizer
    optimizer_type = opt.optimizer_type or OptimizerType.ADAMW_WITH_COSINE_ANNEALING

    # Determine optimizer name based on type
    if optimizer_type in (OptimizerType.ADAM_WITH_COSINE_ANNEALING, OptimizerType.ADAM_WITH_FLAT_LR):
        optimizer_name = "torch.optim.Adam"
    else:
        # Default: AdamW for ADAMW_WITH_COSINE_ANNEALING and ADAMW_WITH_FLAT_LR
        optimizer_name = "torch.optim.AdamW"

    return {
        "name": optimizer_name,
        "kwargs": {
            "lr": opt.learning_rate,
            "weight_decay": opt.weight_decay,
            "betas": [opt.beta1, opt.beta2],
            "eps": 1e-5,  # NeMo RL default
            "foreach": False,
            "fused": False,
        },
    }


def _build_scheduler_config(
    customizer_config: TrainingStepConfig,
    total_steps: int,
) -> list[dict[str, Any]] | dict[str, Any]:
    """
    Build learning rate scheduler configuration.

    Supports two scheduler types based on optimizer_type:
    - Cosine Annealing: LinearLR warmup followed by CosineAnnealingLR decay
    - Flat LR: ConstantLR (constant learning rate throughout training)
    """
    opt = customizer_config.optimizer
    optimizer_type = opt.optimizer_type or OptimizerType.ADAMW_WITH_COSINE_ANNEALING
    warmup_steps = opt.warmup_steps
    lr = opt.learning_rate
    min_lr = opt.min_learning_rate or 0.0

    # Check if using flat LR scheduler
    if optimizer_type in (OptimizerType.ADAM_WITH_FLAT_LR, OptimizerType.ADAMW_WITH_FLAT_LR):
        # Flat LR: Use ConstantLR scheduler
        return {
            "name": "torch.optim.lr_scheduler.ConstantLR",
            "kwargs": {
                "factor": 1.0,
                "total_iters": total_steps,
            },
        }

    if optimizer_type in (OptimizerType.ADAM_WITH_COSINE_ANNEALING, OptimizerType.ADAMW_WITH_COSINE_ANNEALING):
        # Default: Cosine Annealing with warmup
        # Compute start_factor for warmup (avoid division by zero)
        start_factor = max(min_lr / lr, 1e-5) if lr > 0 else 1e-5
        # Clamp warmup_steps to >= 1 for cosine schedulers; LinearLR(total_iters=0)
        # and milestones=[0] produce invalid scheduler behavior
        effective_warmup_steps = max(warmup_steps or 0, 1)

        return [
            {
                "name": "torch.optim.lr_scheduler.LinearLR",
                "kwargs": {
                    "start_factor": start_factor,
                    "end_factor": 1.0,
                    "total_iters": effective_warmup_steps,
                },
            },
            {
                "name": "torch.optim.lr_scheduler.CosineAnnealingLR",
                "kwargs": {
                    "T_max": max(total_steps - effective_warmup_steps, 1),
                    "eta_min": min_lr,
                },
            },
            {
                "milestones": [effective_warmup_steps],
            },
        ]

    return {}


def _build_logger_config(
    customizer_config: TrainingStepConfig,
    job_ctx: NMPJobContext,
    workspace_dir: Path,
) -> dict[str, Any]:
    """Build logger configuration for NeMo RL.

    WandB logging is handled by nemo-rl's Logger class when wandb_enabled is True.
    The wandb config is passed directly to wandb.init().
    """
    wandb_config = build_wandb_config(
        customizer_config=customizer_config,
        job_ctx=job_ctx,
        framework="nemo_rl",
    )
    wandb_enabled = wandb_config is not None
    # NeMo-RL's WandbLogger always passes `dir=` when initializing wandb.
    # Avoid duplicate keyword errors by removing it from shared config here.
    if wandb_config is not None:
        wandb_config.pop("dir", None)
    mlflow_config = build_mlflow_config(
        customizer_config=customizer_config,
        job_ctx=job_ctx,
        framework="nemo_rl",
    )
    mlflow_enabled = mlflow_config is not None

    config: dict[str, Any] = {
        "log_dir": str(workspace_dir / "logs"),
        "num_val_samples_to_print": 0,
        "tensorboard_enabled": False,
        "monitor_gpus": False,
        "wandb_enabled": wandb_enabled,
        "mlflow_enabled": mlflow_enabled,
        "swanlab_enabled": False,
        "gpu_monitoring": {
            "collection_interval": 10,
            "flush_interval": 10,
        },
    }

    if wandb_enabled and wandb_config:
        config["wandb"] = wandb_config

    if mlflow_enabled and mlflow_config:
        config["mlflow"] = mlflow_config

    return config
