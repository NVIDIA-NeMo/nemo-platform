# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Task that exercises workload-auth by reading a workspace through the public SDK."""

import os

from nemo_platform import NeMoPlatform
from nmp.common.jobs.config import get_task_config
from pydantic import BaseModel

_WORKLOAD_TOKEN_ENV_VARS = ("NEMO_WORKLOAD_TOKEN", "NEMO_WORKLOAD_TOKEN_FILE")


class WorkloadWorkspaceGetConfig(BaseModel):
    """Configuration for the workload workspace read task."""

    workspace: str


def _load_workload_token() -> str:
    if token := os.environ.get("NEMO_WORKLOAD_TOKEN"):
        return token
    if token_file := os.environ.get("NEMO_WORKLOAD_TOKEN_FILE"):
        with open(token_file, encoding="utf-8") as token_handle:
            token = token_handle.read().strip()
        if token:
            return token
    token_vars = " or ".join(_WORKLOAD_TOKEN_ENV_VARS)
    raise RuntimeError(f"workload token not configured; set {token_vars}")


def run(*, sdk: NeMoPlatform | None = None) -> int:
    """Read the configured workspace using the public bearer-token SDK path."""
    try:
        config = get_task_config(WorkloadWorkspaceGetConfig)
        if sdk is None:
            token = _load_workload_token()
            sdk = NeMoPlatform(default_headers={"Authorization": f"Bearer {token}"})
        workspace = sdk.workspaces.retrieve(config.workspace)
        print(f"Successfully retrieved workspace: {workspace.name}")
        return 0
    except Exception as exc:
        print(f"Workload workspace retrieval failed: {exc}")
        return 1
