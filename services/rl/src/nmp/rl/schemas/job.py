# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical NeMo-RL job / training schemas — consumed by the compiler and drivers."""

from __future__ import annotations

from typing import Annotated, Literal, Self, Union

from nemo_platform_plugin.integrations import IntegrationsSpec
from nmp.customization_common.schema import NamespacedModel
from nmp.customization_common.schemas.values import OutputNameType
from nmp.rl.app.jobs.training.schemas import OptimizerType
from nmp.rl.entities.values import TrainingType
from pydantic import ConfigDict, Discriminator, Field, model_validator


class RlSchema(NamespacedModel):
    """Backend base: every RL-owned model emits an ``Rl``-prefixed OpenAPI schema
    name (``DPOTraining`` -> ``RlDPOTraining``), so it can't collide with another
    backend's same-named model in the merged ``/apis/customization`` spec.
    """

    __schema_namespace__ = "Rl"


class ParallelismParams(RlSchema):
    """Distributed training parallelism configuration."""

    num_gpus_per_node: int = Field(default=1, gt=0, description="Number of GPUs per node.")
    num_nodes: int = Field(default=1, gt=0, description="Number of nodes (>1 → multi-node Ray cluster).")
    tensor_parallel_size: int = Field(default=1, gt=0, description="Tensor parallel size.")
    pipeline_parallel_size: int = Field(default=1, gt=0, description="Pipeline parallel size.")
    context_parallel_size: int = Field(default=1, gt=0, description="Context parallel size.")
    sequence_parallel: bool = Field(default=False, description="Enable sequence parallelism.")


class LoRAParams(RlSchema):
    """LoRA hyperparameters for GRPO (DTensor ``lora_cfg``). No merge-at-export."""

    rank: int = Field(default=16, gt=0, description="LoRA rank (r); maps to NeMo-RL lora_cfg.dim.")
    alpha: int = Field(default=32, gt=0, description="LoRA scaling factor (effective lr multiplier = alpha/rank).")
    dropout: float = Field(default=0.0, ge=0.0, le=1.0, description="LoRA dropout probability.")
    target_modules: list[str] | None = Field(
        default=None,
        description="Module names to adapt. Empty/None with match_all_linear applies to all linear layers.",
    )
    exclude_modules: list[str] | None = Field(
        default=None,
        description="Module name patterns to exclude from LoRA.",
    )
    use_triton: bool = Field(
        default=True,
        description="Use Triton LoRA kernels (DTensor v2). Set false when tensor_parallel_size > 1.",
    )


class _TrainingBase(RlSchema):
    """Common training configuration shared by all RL methods."""

    model_config = ConfigDict(protected_namespaces=())

    # --- Optimizer ---
    optimizer_type: OptimizerType | None = Field(
        default=None,
        description="Optimizer + LR-scheduler combination (AdamW/Adam × cosine-annealing/flat-LR). "
        "Defaults to AdamW with cosine annealing.",
    )
    learning_rate: float = Field(default=1e-4, gt=0.0, description="Peak learning rate.")
    min_learning_rate: float | None = Field(default=None, ge=0.0, description="Minimum LR for cosine decay.")
    weight_decay: float = Field(default=0.01, ge=0.0, description="Weight decay coefficient.")
    adam_beta1: float = Field(default=0.9, ge=0.0, lt=1.0, description="Adam beta1.")
    adam_beta2: float = Field(default=0.999, ge=0.0, lt=1.0, description="Adam beta2.")
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
        "set False only to skip the extra eval. GRPO ignores this when the dataset ships no "
        "validation.jsonl.",
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

    # No default: ``TrainingMethod`` is a discriminated union, so the tag has to be
    # present in the submitted JSON. Defaulting it here would make the generated
    # OpenAPI schema advertise the field as optional while the server rejects it.
    type: Literal["dpo"]
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


class GRPOTraining(_TrainingBase):
    """Group Relative Policy Optimization with NeMo Gym environments.

    ``finetuning_type`` is ``all_weights`` (default) or ``lora`` only.
    ``lora_merged`` is not supported for GRPO on the platform DTensor path.
    """

    # No default: ``TrainingMethod`` is a discriminated union, so the tag has to be
    # present in the submitted JSON (same as DPOTraining.type).
    type: Literal["grpo"]
    finetuning_type: Literal["all_weights", "lora"] = Field(
        default="all_weights",
        description="Full-weight GRPO or LoRA adapter training. lora_merged is not supported.",
    )
    lora: LoRAParams | None = Field(
        default=None,
        description="LoRA hyperparameters. Defaults applied when finetuning_type is lora.",
    )
    num_generations_per_prompt: int = Field(
        default=8, gt=0, description="Group size: rollouts sampled per prompt, used for relative advantages."
    )
    num_prompts_per_step: int | None = Field(
        default=None,
        gt=0,
        description="Prompts sampled per training step. Derived from batch_size / "
        "num_generations_per_prompt when omitted; the product of the two must be a "
        "multiple of batch_size.",
    )
    num_val_generations_per_prompt: int = Field(
        default=4, gt=0, description="Rollouts sampled per prompt during validation."
    )
    normalize_rewards: bool = Field(default=True, description="Normalize rewards within each prompt group.")
    max_rollout_turns: int = Field(
        default=1, gt=0, description="Maximum agent turns per rollout. Single-turn environments use 1."
    )
    ref_policy_kl_penalty: float = Field(
        default=0.0, ge=0.0, description="KL penalty coefficient against the reference policy."
    )
    ratio_clip_min: float = Field(default=0.2, ge=0.0, description="Lower PPO-style importance ratio clip bound.")
    ratio_clip_max: float = Field(default=0.28, ge=0.0, description="Upper PPO-style importance ratio clip bound.")
    max_grad_norm: float = Field(default=1.0, ge=0.0, description="Maximum gradient norm for clipping.")

    @model_validator(mode="after")
    def _lora_defaults(self) -> Self:
        if self.finetuning_type == "lora" and self.lora is None:
            self.lora = LoRAParams()
        if self.finetuning_type == "all_weights" and self.lora is not None:
            raise ValueError("lora must be omitted when finetuning_type is all_weights")
        return self


TrainingMethod = Annotated[Union[DPOTraining, GRPOTraining], Discriminator("type")]


class _OutputBase(RlSchema):
    name: str = Field(max_length=255, examples=["my-dpo-llama"])


class OutputRequest(_OutputBase):
    """Output artifact configuration provided by the user."""


class OutputResponse(_OutputBase):
    """Resolved output artifact details."""

    type: OutputNameType = Field(default=OutputNameType.MODEL)
    fileset: str = Field(max_length=255)


class RlJobOutput(RlSchema):
    """Canonical NeMo-RL job spec (output of the plugin transform)."""

    model_config = ConfigDict(protected_namespaces=())

    name: str | None = Field(default=None)
    model: str = Field(description="Model entity reference ('name' or 'workspace/name').")
    dataset: str = Field(description="Dataset fileset reference ('name' or 'workspace/name').")
    environment: str | None = Field(default=None)
    training: TrainingMethod = Field(description="Training method and hyperparameters.")
    integrations: IntegrationsSpec | None = Field(default=None)
    output: OutputResponse = Field(description="Output artifact created by this job.")

    @property
    def training_type(self) -> TrainingType:
        return TrainingType(self.training.type)

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
        if isinstance(training, GRPOTraining):
            if not self.environment:
                raise ValueError("GRPO jobs require an environment fileset reference.")
            # The rollout batch is num_prompts_per_step * num_generations_per_prompt, and
            # NeMo-RL shards it by the train batch. When num_prompts_per_step is derived,
            # the floor division can leave the two out of step (e.g. 32 // 5 = 6 -> 30 vs
            # 32), which only surfaces as an assert at the first optimizer step.
            gen = training.num_generations_per_prompt
            prompts = training.num_prompts_per_step or max(gb // max(gen, 1), 1)
            rollout = prompts * gen
            if rollout % gb != 0:
                raise ValueError(
                    f"num_prompts_per_step ({prompts}) * num_generations_per_prompt ({gen}) "
                    f"= {rollout} must be a multiple of batch_size ({gb}). Choose a "
                    f"num_generations_per_prompt that divides batch_size, or set "
                    f"num_prompts_per_step explicitly."
                )

    @model_validator(mode="after")
    def _output_type_matches_training(self) -> Self:
        if self.training_type == TrainingType.DPO and self.output.type != OutputNameType.MODEL:
            raise ValueError("DPO produces a full-weight model; output.type must be 'model'.")
        if self.training_type == TrainingType.GRPO:
            assert isinstance(self.training, GRPOTraining)
            if self.training.finetuning_type == "lora":
                if self.output.type != OutputNameType.ADAPTER:
                    raise ValueError("GRPO LoRA produces an adapter; output.type must be 'adapter'.")
            elif self.output.type != OutputNameType.MODEL:
                raise ValueError("GRPO all_weights produces a full-weight model; output.type must be 'model'.")
        return self
