# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Value types for the unsloth service.

A reduced subset of automodel's ``entities/values.py`` — the unsloth
backend supports SFT only, with two finetuning shapes (LoRA / full).
The plugin's input schema enforces this; this module exists so compile
and model-entity code can speak the same enum values as automodel.
"""

from enum import Enum, StrEnum


class TrainingType(str, Enum):
    """Training algorithm type. Unsloth backend supports SFT only."""

    SFT = "sft"


class FinetuningType(str, Enum):
    """Finetuning strategy.

    The plugin's ``UnslothJobInput.training.finetuning_type`` accepts
    ``"lora"`` and ``"full"``; ``"full"`` maps onto :attr:`ALL_WEIGHTS`,
    matching automodel's compiler vocabulary. ``"lora_merged"`` is
    derived from ``output.save_method`` at compile time when the user
    asks for a merged checkpoint.
    """

    ALL_WEIGHTS = "all_weights"
    LORA = "lora"
    LORA_MERGED = "lora_merged"


class OutputNameType(StrEnum):
    """Output artifact type — adapter (LoRA only) or model (merged / full)."""

    ADAPTER = "adapter"
    MODEL = "model"
