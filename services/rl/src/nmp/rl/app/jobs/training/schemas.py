# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backend-agnostic training-step config consumed by the container runner.

The compiler serializes a :class:`TrainingStepConfig` into the training
``PlatformJobStep``; the runner deserializes it and ``dpo_config.compile_dpo_config``
turns it into the NeMo-RL YAML.
"""

from __future__ import annotations

from enum import Enum

from nmp.rl.app.constants import DEFAULT_OUTPUT_MODEL_PATH, DEFAULT_SEED, DEFAULT_TRAINING_OUTPUT_PATH
from nmp.rl.entities.values import CheckpointFormat, FinetuningType, Precision, TrainingType
from pydantic import BaseModel, Field


class TrainingBackend(str, Enum):
    """Training backend identifier."""

    NEMO_RL = "nemo_rl"


class OptimizerType(str, Enum):
    """Optimizer and scheduler combination types."""

    ADAMW_WITH_COSINE_ANNEALING = "adamw_with_cosine_annealing"
    ADAM_WITH_COSINE_ANNEALING = "adam_with_cosine_annealing"
    ADAMW_WITH_FLAT_LR = "adamw_with_flat_lr"
    ADAM_WITH_FLAT_LR = "adam_with_flat_lr"


class ModelConfig(BaseModel):
    """Internal model configuration with a resolved local path."""

    path: str = Field(description="Local path to the downloaded model directory.")
    name: str | None = Field(default=None, description="Model entity identifier.")
    max_seq_length: int = Field(default=2048)
    precision: Precision | None = Field(default=None, description="Weight dtype; auto-detected when None.")
    chat_template: str | None = Field(default=None, description="Jinja2 chat template override.")
    trust_remote_code: bool = Field(default=False)


class DPOConfig(BaseModel):
    """DPO hyperparameters controlling the loss and optimization behavior."""

    ref_policy_kl_penalty: float = Field(default=0.05, ge=0.0, description="KL penalty (beta in the DPO paper).")
    preference_average_log_probs: bool = Field(default=False)
    sft_average_log_probs: bool = Field(default=False)
    preference_loss_weight: float = Field(default=1.0, ge=0.0)
    sft_loss_weight: float = Field(default=0.0, ge=0.0)
    max_grad_norm: float = Field(default=1.0, ge=0.0)


class WandBConfig(BaseModel):
    project: str | None = None
    name: str | None = None
    entity: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    base_url: str | None = None


class MLflowConfig(BaseModel):
    experiment_name: str | None = None
    run_name: str | None = None
    tags: dict[str, str] | None = None
    description: str | None = None
    tracking_uri: str | None = None


class TrainingStepConfig(BaseModel):
    """Normalized, backend-agnostic training configuration.

    The training container deserializes this and the NeMo-RL backend transforms
    it into library-specific YAML at runtime.
    """

    class DatasetConfig(BaseModel):
        path: str
        prompt_template: str | None = None
        add_bos: bool | None = None
        add_eos: bool | None = None

    class TrainingConfig(BaseModel):
        training_type: TrainingType
        finetuning_type: FinetuningType | None = None
        dpo: DPOConfig | None = None

    class ScheduleConfig(BaseModel):
        epochs: int = 1
        max_steps: int | None = None
        val_check_interval: float | None = None
        val_at_end: bool = True
        keep_top_k: int = 1

    class BatchConfig(BaseModel):
        global_batch_size: int = Field(default=32, gt=0)
        micro_batch_size: int = Field(default=1, gt=0)
        sequence_packing: bool = False
        sequence_packing_max_samples: int = 1000

    class OptimizerConfig(BaseModel):
        optimizer_type: OptimizerType | None = Field(default=None)
        learning_rate: float = 1e-4
        min_learning_rate: float | None = None
        eps: float = 1e-5
        weight_decay: float = 0.01
        beta1: float = 0.9
        beta2: float = 0.999
        warmup_steps: int = 0

    class ParallelismConfig(BaseModel):
        num_nodes: int = 1
        num_gpus_per_node: int = 1
        tensor_parallel_size: int = 1
        pipeline_parallel_size: int = 1
        context_parallel_size: int = 1
        sequence_parallel: bool = False
        activation_checkpointing: bool = False

    class IntegrationsConfig(BaseModel):
        wandb: WandBConfig | None = None
        mlflow: MLflowConfig | None = None

    # === Main config fields ===
    backend: TrainingBackend = TrainingBackend.NEMO_RL
    model: ModelConfig
    dataset: DatasetConfig
    training: TrainingConfig
    schedule: ScheduleConfig
    batch: BatchConfig
    optimizer: OptimizerConfig
    parallelism: ParallelismConfig
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)

    # === Output paths ===
    output_model: str
    workspace_path: str = Field(default=DEFAULT_TRAINING_OUTPUT_PATH)
    output_path: str = Field(default=DEFAULT_OUTPUT_MODEL_PATH)

    # === Misc ===
    seed: int = Field(default=DEFAULT_SEED)
    training_timeout: int | None = None


class GPUInfo(BaseModel):
    architecture: str
    device_name: str
    memory_gb: float
    cuda_version: str


class CheckpointInfo(BaseModel):
    path: str
    format: CheckpointFormat
    precision: Precision | None = None


class TrainingMetrics(BaseModel):
    final_loss: float | None = None
    final_val_loss: float | None = None
    best_val_loss: float | None = None
    total_steps: int = 0
    total_epochs: int = 0


class TrainingResult(BaseModel):
    """Result written by the training task to ``{workspace_path}/training_result.json``."""

    success: bool
    error_message: str | None = None
    checkpoint: CheckpointInfo | None = None
    gpu_info: GPUInfo | None = None
    metrics: TrainingMetrics = Field(default_factory=TrainingMetrics)
    training_duration_seconds: float | None = None
