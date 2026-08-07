# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Canonical NeMo-RL job / training schemas — consumed by the compiler and drivers."""

from __future__ import annotations

from typing import Annotated, Literal, Self, Union

from nemo_platform_plugin.integrations import IntegrationsSpec
from nmp.customization_common.schema import NamespacedModel
from nmp.customization_common.schemas.values import OutputNameType
from nmp.customization_common.training.reporting import ProgressReportingConfig
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


class _TrainingBase(RlSchema):
    """Common training configuration shared by all RL methods."""

    model_config = ConfigDict(protected_namespaces=())

    optimizer_type: OptimizerType | None = Field(default=None)
    learning_rate: float = Field(default=1e-4, gt=0.0)
    min_learning_rate: float | None = Field(default=None, ge=0.0)
    weight_decay: float = Field(default=0.01, ge=0.0)
    adam_beta1: float = Field(default=0.9, ge=0.0, lt=1.0)
    adam_beta2: float = Field(default=0.999, ge=0.0, lt=1.0)
    adam_eps: float = Field(default=1e-5, gt=0.0)
    warmup_steps: int = Field(default=0, ge=0)
    epochs: int = Field(default=1, gt=0)
    max_steps: int | None = Field(default=None, gt=0)
    val_check_interval: float | None = Field(default=None)
    val_at_end: bool = Field(default=True)
    progress_reporting: ProgressReportingConfig = Field(default_factory=ProgressReportingConfig)
    keep_top_k: int = Field(default=1, gt=0)
    batch_size: int = Field(default=32, gt=0)
    micro_batch_size: int = Field(default=1, gt=0)
    activation_checkpointing: bool = Field(default=False)
    max_seq_length: int = Field(default=2048, gt=0)
    seed: int | None = Field(default=None)
    parallelism: ParallelismParams = Field(default_factory=ParallelismParams)
    execution_profile: str | None = Field(default=None, min_length=1)


class DPOTraining(_TrainingBase):
    """Direct Preference Optimization (full-weight only — PEFT unsupported)."""

    type: Literal["dpo"] = "dpo"
    ref_policy_kl_penalty: float = Field(default=0.05, ge=0.0)
    preference_average_log_probs: bool = Field(default=False)
    sft_average_log_probs: bool = Field(default=False)
    preference_loss_weight: float = Field(default=1.0, ge=0.0)
    sft_loss_weight: float = Field(default=0.0, ge=0.0)
    max_grad_norm: float = Field(default=1.0, ge=0.0)


class GRPOTraining(_TrainingBase):
    """Group Relative Policy Optimization with NeMo Gym environments."""

    type: Literal["grpo"] = "grpo"
    num_generations_per_prompt: int = Field(default=8, gt=0)
    num_prompts_per_step: int | None = Field(default=None, gt=0)
    num_val_generations_per_prompt: int = Field(default=4, gt=0)
    normalize_rewards: bool = True
    max_rollout_turns: int = Field(default=1, gt=0)
    ref_policy_kl_penalty: float = Field(default=0.0, ge=0.0)
    ratio_clip_min: float = Field(default=0.2, ge=0.0)
    ratio_clip_max: float = Field(default=0.28, ge=0.0)


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
        if self.training_type == TrainingType.GRPO and not self.environment:
            raise ValueError("GRPO jobs require an environment fileset reference.")

    @model_validator(mode="after")
    def _output_type_matches_training(self) -> Self:
        if self.training_type == TrainingType.DPO and self.output.type != OutputNameType.MODEL:
            raise ValueError("DPO produces a full-weight model; output.type must be 'model'.")
        if self.training_type == TrainingType.GRPO and self.output.type != OutputNameType.MODEL:
            raise ValueError("GRPO produces a full-weight model; output.type must be 'model'.")
        return self
