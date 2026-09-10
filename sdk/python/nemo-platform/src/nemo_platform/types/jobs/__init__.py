# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compatibility aliases for source-owned Jobs types.

The generated Jobs resource was removed from the public Stainless SDK, but a few
callers still import Jobs models from ``nemo_platform.types.jobs`` for type
annotations. Keep those imports routed to the source-owned Jobs models.
"""

from __future__ import annotations

from nemo_platform_plugin.jobs.types import (
    PlatformJobResponse as PlatformJobResponse,
    PlatformJobStepResponse as PlatformJobStepResponse,
    PlatformJobTaskResponse as PlatformJobTaskResponse,
    PlatformJobStepWithContext as PlatformJobStepWithContext,
)

PlatformJobStep = PlatformJobStepResponse
PlatformJobTask = PlatformJobTaskResponse
