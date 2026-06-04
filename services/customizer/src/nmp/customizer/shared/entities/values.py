# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared entity value types used across customization backends."""

from enum import Enum, StrEnum


class FinetuningType(str, Enum):
    """Finetuning strategy (full weights vs PEFT)."""

    ALL_WEIGHTS = "all_weights"
    LORA = "lora"
    LORA_MERGED = "lora_merged"


class OutputNameType(StrEnum):
    """Output artifact type."""

    ADAPTER = "adapter"
    MODEL = "model"
