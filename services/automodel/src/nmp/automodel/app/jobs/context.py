# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job context for automodel container task entrypoints.

Re-exports the shared :class:`nmp.customization_common.service.context.NMPJobContext`
so existing ``nmp.automodel.app.jobs.context`` import paths keep working.
"""

from nmp.customization_common.service.context import (
    DEFAULT_ATTEMPT_ID,
    DEFAULT_JOB_ID,
    DEFAULT_STEP,
    DEFAULT_TASK,
    NMPJobContext,
)

__all__ = [
    "DEFAULT_ATTEMPT_ID",
    "DEFAULT_JOB_ID",
    "DEFAULT_STEP",
    "DEFAULT_TASK",
    "NMPJobContext",
]
