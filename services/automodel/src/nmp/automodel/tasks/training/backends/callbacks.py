# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Training progress callbacks for Automodel Jobs-service reporting.

Re-exports the shared
:class:`nmp.customization_common.training.callbacks.TrainingProgressCallback`.
Automodel does not stamp a ``backend`` field (``_default_backend`` is ``None``),
preserving its existing ``status_details`` shape.
"""

from nmp.customization_common.training.callbacks import TrainingProgressCallback

__all__ = ["TrainingProgressCallback"]
