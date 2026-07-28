# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Task that exercises workload-auth by reading a workspace through the public SDK."""

from nemo_platform import NeMoPlatform
from nmp.common.jobs.config import get_task_config
from nmp.common.sdk_factory import get_task_sdk
from pydantic import BaseModel


class WorkloadWorkspaceGetConfig(BaseModel):
    """Configuration for the workload workspace read task."""

    workspace: str


def run(*, sdk: NeMoPlatform | None = None) -> int:
    """Read the configured workspace using the public SDK workload identity path."""
    try:
        config = get_task_config(WorkloadWorkspaceGetConfig)
        sdk = sdk or get_task_sdk(as_service="jobs")
        workspace = sdk.workspaces.retrieve(config.workspace)
        print(f"Successfully retrieved workspace: {workspace.name}")
        return 0
    except Exception as exc:
        print(f"Workload workspace retrieval failed: {exc}")
        return 1
