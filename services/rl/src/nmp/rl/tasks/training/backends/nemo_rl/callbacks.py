# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Training progress callbacks for NeMo-RL Jobs-service reporting.

Thin subclass of the shared
:class:`nmp.customization_common.training.callbacks.TrainingProgressCallback`,
matching the unsloth and automodel pattern. ``_default_backend`` stays ``None``
so no ``backend`` key is added and the existing status-detail shape is preserved.
"""

from nmp.customization_common.training.callbacks import (
    TrainingProgressCallback as _BaseTrainingProgressCallback,
)

__all__ = ["TrainingProgressCallback"]


class TrainingProgressCallback(_BaseTrainingProgressCallback):
    """Report NeMo-RL training progress to the Jobs service."""
