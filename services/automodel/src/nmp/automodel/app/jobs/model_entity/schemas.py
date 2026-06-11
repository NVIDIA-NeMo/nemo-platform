# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Schemas for the automodel model_entity task configuration.

Re-exports the shared :mod:`nmp.customization_common.schemas.model_entity`.
"""

from nmp.customization_common.schemas.model_entity import (
    DeploymentParameters,
    ModelEntityCreationError,
    ModelEntityTaskConfig,
    PEFTConfig,
    ToolCallConfig,
)

__all__ = [
    "DeploymentParameters",
    "ModelEntityCreationError",
    "ModelEntityTaskConfig",
    "PEFTConfig",
    "ToolCallConfig",
]
