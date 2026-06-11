# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Submitter-facing Unsloth schemas.

The **canonical** types (``UnslothJobOutput``, ``OutputResponse``, and
all shared sub-shapes) live in :mod:`nmp.unsloth.schemas`. They are
re-exported from this module for backward compatibility and to keep
caller imports concise (``from nemo_unsloth_plugin.schema import
UnslothJobInput, ModelLoadSpec`` still works).

Only two types are defined here:

- :class:`OutputRequest` — submitter-facing output preferences. The
  plugin's :func:`~nemo_unsloth_plugin.transform.transform_input_to_output`
  resolves it into the canonical :class:`~nmp.unsloth.schemas.OutputResponse`.
- :class:`UnslothJobInput` — the POST body / CLI JSON shape and the
  validators that mediate between input and canonical (mutexes,
  defaulting, etc.).
"""

from __future__ import annotations

from typing import Literal, Self

from nmp.unsloth.schemas import (
    BatchSpec,
    DatasetSpec,
    DeploymentParams,
    HardwareSpec,
    IntegrationsSpec,
    LoRAParams,
    ModelLoadSpec,
    OptimizerSpec,
    OutputResponse,
    ScheduleSpec,
    ToolCallParams,
    TrainingSpec,
    UnslothJobOutput,
    WandbIntegration,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "BatchSpec",
    "DatasetSpec",
    "DeploymentParams",
    "HardwareSpec",
    "IntegrationsSpec",
    "LoRAParams",
    "ModelLoadSpec",
    "OptimizerSpec",
    "OutputRequest",
    "OutputResponse",
    "ScheduleSpec",
    "ToolCallParams",
    "TrainingSpec",
    "UnslothJobInput",
    "UnslothJobOutput",
    "WandbIntegration",
]


class OutputRequest(BaseModel):
    """Submitter-facing output preferences. ``name`` is auto-derived if omitted."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    save_method: Literal["lora", "merged_16bit", "merged_4bit"] = "lora"


class UnslothJobInput(BaseModel):
    """POST body / CLI JSON for ``nemo customization unsloth run``."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    model: ModelLoadSpec
    dataset: DatasetSpec
    training: TrainingSpec = Field(default_factory=TrainingSpec)
    schedule: ScheduleSpec = Field(default_factory=ScheduleSpec)
    batch: BatchSpec = Field(default_factory=BatchSpec)
    optimizer: OptimizerSpec = Field(default_factory=OptimizerSpec)
    hardware: HardwareSpec = Field(default_factory=HardwareSpec)
    integrations: IntegrationsSpec | None = None
    output: OutputRequest | None = None
    deployment_config: str | DeploymentParams | None = Field(
        default=None,
        description=(
            "Deployment configuration for auto-deploying the model after training. "
            "Pass a string to reference an existing ModelDeploymentConfig by name "
            "('my-config' or 'workspace/my-config'). An object provides inline NIM "
            "deployment parameters. Omit to skip deployment."
        ),
    )

    @model_validator(mode="after")
    def _validate(self) -> Self:
        # exactly one of epochs / max_steps
        if self.schedule.epochs is None and self.schedule.max_steps is None:
            raise ValueError("schedule.epochs or schedule.max_steps must be set")
        if self.schedule.epochs is not None and self.schedule.max_steps is not None:
            raise ValueError("schedule.epochs and schedule.max_steps are mutually exclusive")
        # 4bit / 8bit mutex (bitsandbytes — they really are exclusive)
        if self.model.load_in_4bit and self.model.load_in_8bit:
            raise ValueError("model.load_in_4bit and model.load_in_8bit are mutually exclusive")
        # full FT cannot quantize
        if self.training.finetuning_type == "full":
            if self.model.load_in_4bit or self.model.load_in_8bit:
                raise ValueError(
                    "training.finetuning_type='full' is incompatible with 4-bit/8-bit loading; "
                    "set model.load_in_4bit=false and model.load_in_8bit=false"
                )
            if self.training.lora is not None:
                raise ValueError("training.lora must be unset when training.finetuning_type='full'")
        # auto-fill LoRA when implied but not provided
        if self.training.finetuning_type == "lora" and self.training.lora is None:
            self.training.lora = LoRAParams()
        # warmup_steps and warmup_ratio mutex (transformers also enforces this
        # at runtime; we surface it earlier with a clearer message)
        if self.schedule.warmup_steps and self.schedule.warmup_ratio is not None:
            raise ValueError("schedule.warmup_steps and schedule.warmup_ratio are mutually exclusive")
        # merged_* save methods only make sense with LoRA training
        if self.output is not None and self.output.save_method != "lora":
            if self.training.finetuning_type != "lora":
                raise ValueError(
                    f"output.save_method={self.output.save_method!r} is only valid for training.finetuning_type='lora'"
                )
        # LoRA adapters cannot be deployed against a base model with lora_enabled=false —
        # the deployed base would refuse to serve the adapter. Surface this at submit time
        # rather than failing after training completes.
        is_lora_adapter = self.training.finetuning_type == "lora" and (
            self.output is None or self.output.save_method == "lora"
        )
        if (
            is_lora_adapter
            and isinstance(self.deployment_config, DeploymentParams)
            and not self.deployment_config.lora_enabled
        ):
            raise ValueError(
                "deployment_config.lora_enabled must be true (or omitted) when training a LoRA adapter. "
                "Setting lora_enabled=false would deploy the base model without LoRA support, "
                "making the trained adapter unservable."
            )
        return self
