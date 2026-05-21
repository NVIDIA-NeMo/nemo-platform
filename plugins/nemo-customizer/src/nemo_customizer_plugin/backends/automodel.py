# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Stub: local AutoModel backend.

Not implemented locally. The remote ``services/customizer/`` already wraps
AutoModel via a multi-step ``PlatformJobSpec``. Adding a local path
requires factoring its training driver out of the platform JobSpec
runner, which is out of scope for the PoC.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nemo_platform_plugin.job_context import JobContext

    from nemo_customizer_plugin.jobs.finetune import FinetuneSpec


def train_sft(spec: "FinetuneSpec", ctx: "JobContext") -> dict:
    raise NotImplementedError(
        "Local 'automodel' backend is not implemented. Use the remote service "
        "(services/customizer/) for AutoModel-backed customization."
    )
