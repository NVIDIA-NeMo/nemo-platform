# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared customization task utilities for container job backends.

Consolidates schemas and job context used by ``nmp-customizer``,
``nmp-automodel``, and ``nmp-unsloth``. Backend packages re-export
from here so each service keeps its own import paths.
"""

from nmp.customizer.shared.app.jobs.context import NMPJobContext

__all__ = ["NMPJobContext"]
