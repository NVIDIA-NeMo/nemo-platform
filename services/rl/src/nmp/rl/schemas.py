# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical NeMo-RL schemas — consumed by the compiler and the DPO driver.

Why these live in the service, not the plugin (same rationale as
:mod:`nmp.unsloth.schemas`): both compile-time
(:func:`nmp.rl.compile.platform_job_config_compiler`) and runtime (the DPO
driver) consume the canonical shape; the plugin's ``transform.py`` only
produces it from the thin ``RlJobInput``.

Only DPO is wired today; the discriminated training union leaves a seam for
GRPO/PPO (see ``TrainingMethod``).
"""

from __future__ import annotations

from typing import Literal, Self

from nemo_platform_plugin.integrations import IntegrationsSpec
from nmp.customization_common.schemas.values import OutputNameType
from nmp.rl.app.jobs.training.schemas import OptimizerType
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ParallelismParams(BaseModel):
    """Distributed training parallelism configuration.

    Single-node multi-GPU uses ``num_nodes=1`` with ``num_gpus_per_node>1``;
    multi-node sets ``num_nodes>1`` and the compiler emits a distributed-GPU
    executor (see :mod:`nmp.rl.app.jobs.compiler`).
    """

    model_config = ConfigDict(extra="forbid")

    num_gpus_per_node: int = Field(default=1, gt=0, description="Number of GPUs per node.")
    num_nodes: int = Field(default=1, gt=0, description="Number of nodes (>1 → multi-node Ray cluster).")
    tensor_parallel_size: int = Field(default=1, gt=0, description="Tensor parallel size.")
    pipeline_parallel_size: int = Field(default=1, gt=0, description="Pipeline parallel size.")
    context_parallel_size: int = Field(default=1, gt=0, description="Context parallel size.")
    sequence_parallel: bool = Field(default=False, description="Enable sequence parallelism.")


class _TrainingBase(BaseModel):
    """Common training configuration shared by all RL methods.

    Flat hyperparameters match the ML-practitioner mental model (HuggingFace
    ``TrainingArguments`` / TRL configs). Only parallelism is grouped.
    """

    model_config = ConfigDict(protected_namespaces=(), extra="forbid")

    # --- Optimizer ---
    optimizer_type: OptimizerType | None = Field(
        default=None,
        description="Optimizer + LR-scheduler combination (AdamW/Adam × cosine-annealing/flat-LR). "
        "Defaults to AdamW with cosine annealing.",
    )
    learning_rate: float = Field(default=1e-4, description="Peak learning rate.")
    min_learning_rate: float | None = Field(default=None, description="Minimum LR for cosine decay.")
    weight_decay: float = Field(default=0.01, description="Weight decay coefficient.")
    adam_beta1: float = Field(default=0.9, description="Adam beta1.")
    adam_beta2: float = Field(default=0.999, description="Adam beta2.")
    adam_eps: float = Field(default=1e-5, gt=0.0, description="Adam epsilon (numerical stability term).")
    warmup_steps: int = Field(default=0, ge=0, description="Linear warmup steps.")

    # --- Schedule ---
    epochs: int = Field(default=1, gt=0, description="Number of passes through the dataset.")
    max_steps: int | None = Field(default=None, gt=0, description="Max training steps (overrides epochs if set).")
    val_check_interval: float | None = Field(
        default=None,
        description="Validation interval. Float <= 1.0 is fraction of epoch; > 1.0 is step count.",
    )
    val_at_end: bool = Field(
        default=True,
        description="Run a final validation pass after the last training step. Keep enabled so the "
        "final checkpoint carries validation metrics and best-checkpoint selection works; "
        "set False only to skip the extra eval.",
    )

    # --- Checkpointing ---
    keep_top_k: int = Field(
        default=1, gt=0, description="Number of best checkpoints to retain (ranked by validation loss)."
    )

    # --- Batch ---
    batch_size: int = Field(default=32, gt=0, description="Global batch size across all GPUs.")
    micro_batch_size: int = Field(default=1, gt=0, description="Per-GPU micro batch size.")
    activation_checkpointing: bool = Field(
        default=False,
        description="Recompute activations during the backward pass to reduce memory at the cost of compute. "
        "Enable to fit larger models or longer sequences.",
    )

    # --- Model ---
    max_seq_length: int = Field(default=2048, gt=0, description="Maximum token sequence length for training.")
    seed: int | None = Field(default=None, description="Random seed for reproducibility.")

    # --- Infrastructure ---
    parallelism: ParallelismParams = Field(default_factory=ParallelismParams)
    execution_profile: str | None = Field(
        default=None,
        min_length=1,
        description="Execution profile for the GPU training step (operator-configured). "
        "Falls back to the service default when omitted.",
    )


class DPOTraining(_TrainingBase):
    """Direct Preference Optimization (full-weight only — PEFT unsupported)."""

    type: Literal["dpo"] = "dpo"
    ref_policy_kl_penalty: float = Field(
        default=0.05, ge=0.0, description="KL penalty coefficient (beta in the DPO paper)."
    )
    preference_average_log_probs: bool = Field(
        default=False, description="Average log probabilities for preference loss calculation."
    )
    sft_average_log_probs: bool = Field(
        default=False, description="Average log probabilities for SFT regularization loss."
    )
    preference_loss_weight: float = Field(default=1.0, ge=0.0, description="Weight for the preference (DPO) loss term.")
    sft_loss_weight: float = Field(
        default=0.0, ge=0.0, description="Weight for SFT regularization loss (0 = disabled)."
    )
    max_grad_norm: float = Field(default=1.0, ge=0.0, description="Maximum gradient norm for clipping.")


# GRPO/PPO headroom. DPO carries a ``type: Literal["dpo"]`` discriminator field
# already, so when a second method lands this becomes:
#   TrainingMethod = Annotated[Union[DPOTraining, GRPOTraining], Discriminator("type")]
# A single-member Union collapses to the member, and Discriminator requires a
# real Union — so today TrainingMethod is just DPOTraining.
TrainingMethod = DPOTraining


class _OutputBase(BaseModel):
    name: str = Field(
        max_length=255,
        description="Name of the output artifact. Used to identify it during deployment and inference.",
        examples=["my-dpo-llama"],
    )


class OutputRequest(_OutputBase):
    """Output artifact configuration provided by the user."""


class OutputResponse(_OutputBase):
    """Resolved output artifact details."""

    type: OutputNameType = Field(
        default=OutputNameType.MODEL,
        description="Output artifact type. DPO is full-weight, so always `model`.",
    )
    fileset: str = Field(
        max_length=255,
        description="FileSet name where output artifacts are stored.",
    )


class RlJobOutput(BaseModel):
    """Canonical NeMo-RL job spec (output of the plugin transform).

    The ``dataset`` fileset must contain ``training.jsonl`` and ``validation.jsonl``
    (any of the four supported preference formats); the dataset-preparation step
    splits/normalizes them at runtime.
    """

    model_config = ConfigDict(protected_namespaces=())

    name: str | None = Field(default=None, description="Optional job name; auto-generated when omitted.")
    model: str = Field(description="Model entity reference ('name' or 'workspace/name').")
    dataset: str = Field(description="Preference dataset fileset reference ('name' or 'workspace/name').")
    training: TrainingMethod = Field(description="Training method and hyperparameters (DPO).")
    integrations: IntegrationsSpec | None = Field(default=None, description="W&B / MLflow integrations.")
    output: OutputResponse = Field(description="Output artifact created by this job.")

    def validate_for_training(self) -> None:
        """Validate parallelism/batch consistency before compiling."""
        training = self.training
        p = training.parallelism
        total_gpus = p.num_gpus_per_node * p.num_nodes
        model_parallel_size = p.tensor_parallel_size * p.pipeline_parallel_size * p.context_parallel_size
        if total_gpus % model_parallel_size != 0:
            raise ValueError(
                f"Total GPUs ({total_gpus}) must be divisible by tensor_parallel_size "
                f"({p.tensor_parallel_size}) * pipeline_parallel_size ({p.pipeline_parallel_size}) * "
                f"context_parallel_size ({p.context_parallel_size}) = {model_parallel_size}"
            )
        derived_dp = total_gpus // model_parallel_size
        gb, mb = training.batch_size, training.micro_batch_size
        divisor = mb * derived_dp
        if gb % divisor != 0:
            raise ValueError(
                f"batch_size ({gb}) must be divisible by micro_batch_size ({mb}) * "
                f"data_parallel_size ({derived_dp}) = {divisor}."
            )

    @model_validator(mode="after")
    def _dpo_is_full_weight(self) -> Self:
        # DPO is full-weight only; surface it early.
        if self.output.type != OutputNameType.MODEL:
            raise ValueError("DPO produces a full-weight model; output.type must be 'model'.")
        return self
