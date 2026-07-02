# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Automodel job input/output schemas (simplified JSON v1)."""

from __future__ import annotations

from typing import Literal, Self

from nemo_platform_plugin.integrations import IntegrationsSpec
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "AutomodelJobInput",
    "AutomodelJobOutput",
    "BatchSpec",
    "DatasetSpec",
    "LoRAParams",
    "OptimizerSpec",
    "OutputRequest",
    "OutputResponse",
    "ParallelismSpec",
    "ScheduleSpec",
    "TrainingSpec",
    "ValidationError",
]


class ValidationError(ValueError):
    """Raised when automodel job input validation fails."""


class LoRAParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(default=16, gt=0)
    alpha: int = Field(default=32, gt=0)
    dropout: float = Field(default=0.0, ge=0.0, le=1.0, description="LoRA dropout probability for regularization.")
    merge: bool = False
    target_modules: list[str] | None = None
    exclude_modules: list[str] | None = Field(
        default=None, description="Module name patterns to exclude from LoRA (e.g. ['*.out_proj'])."
    )
    use_triton: bool = Field(default=True, description="Use the optimized Triton LoRA kernel.")


class DatasetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    training: str = Field(description="Training fileset as 'name' or 'workspace/name'.")
    validation: str | None = None
    prompt_template: str | None = None


class TrainingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    training_type: Literal["sft", "distillation"] = "sft"
    finetuning_type: Literal["lora", "all_weights", "lora_merged"] = "lora"
    lora: LoRAParams | None = None
    max_seq_length: int = Field(default=2048, gt=0)
    precision: Literal["bf16", "fp16", "fp32", "fp8"] | None = Field(
        default=None,
        description="Model precision for training. Auto-detected from the checkpoint when unset.",
    )
    attn_implementation: Literal["sdpa", "flash_attention_2", "eager"] = Field(
        default="sdpa",
        description="Attention backend: 'sdpa' (PyTorch native), 'flash_attention_2', or 'eager'.",
    )
    execution_profile: str | None = Field(default=None, min_length=1)
    teacher_model: str | None = None
    distillation_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    distillation_temperature: float = Field(default=1.0, gt=0.0)
    teacher_precision: Literal["bf16", "fp16", "fp32"] = "bf16"
    offload_teacher: bool = False

    @model_validator(mode="after")
    def _training_type_fields(self) -> Self:
        if self.training_type == "distillation" and not self.teacher_model:
            raise ValueError("teacher_model is required when training_type is distillation")
        if self.finetuning_type.startswith("lora") and self.lora is None:
            self.lora = LoRAParams()
        return self


class ScheduleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    epochs: int = Field(default=1, gt=0)
    max_steps: int | None = Field(default=None, gt=0)
    val_check_interval: float | None = None
    seed: int | None = None


class BatchSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_batch_size: int = Field(default=8, gt=0)
    micro_batch_size: int = Field(default=1, gt=0)
    sequence_packing: bool = False
    sequence_packing_max_samples: int = Field(
        default=1000, gt=0, description="Samples analyzed to estimate the optimal pack size when packing is enabled."
    )


class OptimizerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learning_rate: float = Field(default=5e-6, gt=0.0)
    min_learning_rate: float | None = Field(
        default=None, ge=0.0, description="Minimum learning rate for the cosine decay schedule."
    )
    weight_decay: float = Field(default=0.01, ge=0.0)
    adam_beta1: float = Field(default=0.9, ge=0.0, lt=1.0, description="Adam optimizer beta1.")
    adam_beta2: float = Field(default=0.999, ge=0.0, lt=1.0, description="Adam optimizer beta2.")
    warmup_steps: int = Field(default=0, ge=0)
    adam_eps: float = Field(default=1e-8, gt=0.0, description="Adam/AdamW epsilon for numerical stability.")
    optimizer: Literal["Adam", "AdamW"] = Field(default="Adam", description="Optimizer algorithm.")
    lr_decay_style: Literal["cosine", "linear", "constant"] = Field(
        default="cosine", description="Learning-rate decay schedule."
    )


class ParallelismSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    num_nodes: int = Field(default=1, gt=0)
    num_gpus_per_node: int = Field(default=1, gt=0)
    tensor_parallel_size: int = Field(default=1, gt=0)
    pipeline_parallel_size: int = Field(default=1, gt=0)
    context_parallel_size: int = Field(default=1, gt=0)
    expert_parallel_size: int | None = Field(default=None, gt=0)
    sequence_parallel: bool = Field(default=False, description="Enable sequence parallelism.")


class OutputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None


class OutputResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["model", "adapter"]
    fileset: str
    description: str | None = None


class AutomodelJobInput(BaseModel):
    """POST body / CLI JSON."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    model: str
    dataset: DatasetSpec
    training: TrainingSpec
    schedule: ScheduleSpec = Field(default_factory=ScheduleSpec)
    batch: BatchSpec = Field(default_factory=BatchSpec)
    optimizer: OptimizerSpec = Field(default_factory=OptimizerSpec)
    parallelism: ParallelismSpec = Field(default_factory=ParallelismSpec)
    output: OutputRequest | None = None
    integrations: IntegrationsSpec | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_fields(cls, data: object) -> object:
        if isinstance(data, dict) and "output_model" in data:
            raise ValueError("spec.output_model was removed. Use spec.output instead.")
        return data


class AutomodelJobOutput(BaseModel):
    """Stored canonical spec after ``to_spec()``."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    model: str
    dataset: DatasetSpec
    training: TrainingSpec
    schedule: ScheduleSpec
    batch: BatchSpec
    optimizer: OptimizerSpec
    parallelism: ParallelismSpec
    output: OutputResponse
    integrations: IntegrationsSpec | None = None

    def validate_for_training(self) -> None:
        """MoE / parallelism constraints (ported from legacy CustomizationJobOutput)."""
        p = self.parallelism
        num_nodes = p.num_nodes
        num_gpus_per_node = p.num_gpus_per_node
        tp = p.tensor_parallel_size
        pp = p.pipeline_parallel_size
        cp = p.context_parallel_size
        ep = p.expert_parallel_size

        total_gpus = num_gpus_per_node * num_nodes
        model_parallel_size = tp * pp * cp
        if total_gpus % model_parallel_size != 0:
            raise ValidationError(
                f"Total GPUs ({total_gpus}) must be divisible by "
                f"tensor_parallel_size ({tp}) * pipeline_parallel_size ({pp}) * "
                f"context_parallel_size ({cp}) = {model_parallel_size}"
            )

        derived_dp = total_gpus // model_parallel_size
        gb = self.batch.global_batch_size
        mb = self.batch.micro_batch_size
        divisor = mb * derived_dp
        if gb % divisor != 0:
            raise ValidationError(
                f"global_batch_size ({gb}) must be divisible by "
                f"micro_batch_size ({mb}) * data_parallel_size ({derived_dp}) = {divisor}"
            )

        if ep is not None:
            dp_cp = derived_dp * cp
            if dp_cp % ep != 0:
                raise ValidationError(
                    f"(data_parallel_size * context_parallel_size) ({dp_cp}) "
                    f"must be divisible by expert_parallel_size ({ep})"
                )
            if ep > 1 and tp > 1 and total_gpus > 1:
                raise ValidationError(
                    f"Tensor parallelism (tensor_parallel_size={tp}) is not supported for MoE models "
                    f"when expert_parallel_size > 1 ({ep}); tensor_parallel_size must be 1."
                )
