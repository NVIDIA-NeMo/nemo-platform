# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Stub: local Megatron-Bridge backend.

Not implemented locally. The remote ``services/customizer/`` wraps
Megatron-Bridge through its distributed-GPU executor; that path expects
a multi-node ``PlatformJobSpec`` not a plain subprocess.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nemo_platform_plugin.job_context import JobContext

    from nemo_customizer_plugin.jobs.finetune import FinetuneSpec


def train_sft(spec: "FinetuneSpec", ctx: "JobContext") -> dict:
    raise NotImplementedError(
        "Local 'megatron-bridge' backend is not implemented. Use the remote service "
        "(services/customizer/) for Megatron-Bridge-backed customization."
    )
