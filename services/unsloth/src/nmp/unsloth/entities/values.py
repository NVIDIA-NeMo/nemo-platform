# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Value types for the unsloth service."""

from enum import Enum

from nmp.customizer.shared.entities.values import FinetuningType, OutputNameType

__all__ = [
    "FinetuningType",
    "OutputNameType",
    "TrainingType",
]


class TrainingType(str, Enum):
    """Training algorithm type. Unsloth backend supports SFT only."""

    SFT = "sft"
