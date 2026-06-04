# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared customization-backend utilities for GPU training contributors.

Used by ``nemo-unsloth-plugin`` and ``nemo-automodel-plugin`` (and future
backends) so contributor routes, SDK, and CLI stay consistent under the
``nemo-customizer-plugin`` hub.
"""

from nemo_customizer.shared.contributor import ContributorBackendConfig, make_customization_contributor

__all__ = [
    "ContributorBackendConfig",
    "make_customization_contributor",
]
