# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Where this backend points, and how it authenticates."""

from __future__ import annotations

import os
from dataclasses import dataclass

#: Default fileset holding every published package archive in a workspace. One fileset rather
#: than one per task: `BaseStorage.download_file` receives only a path string, so the fewer
#: places a blob can live, the fewer ways metadata and blobs can end up on different hosts.
DEFAULT_FILESET = "harbor-packages"
DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_WORKSPACE = "default"


@dataclass(frozen=True)
class NemoConfig:
    """Resolved connection settings for the NeMo registry backend.

    Read from the environment at construction rather than import time, so a process can point
    at a different platform between backend instances (which is also what makes the tests able
    to run without patching module globals).
    """

    base_url: str
    workspace: str
    fileset: str
    token: str | None
    timeout_sec: float

    @classmethod
    def from_env(cls) -> "NemoConfig":
        return cls(
            base_url=os.environ.get("NMP_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            workspace=os.environ.get("HARBOR_NEMO_WORKSPACE")
            or os.environ.get("NMP_WORKSPACE", DEFAULT_WORKSPACE),
            fileset=os.environ.get("HARBOR_NEMO_FILESET", DEFAULT_FILESET),
            # NMP_TOKEN first: a token is what the platform actually accepts, and an API key
            # env var is the more common thing to have set for an unrelated service.
            token=os.environ.get("NMP_TOKEN") or os.environ.get("NMP_API_KEY"),
            timeout_sec=float(os.environ.get("HARBOR_NEMO_TIMEOUT_SEC", "120")),
        )

    @property
    def files_url(self) -> str:
        return f"{self.base_url}/apis/files/v2/workspaces/{self.workspace}/filesets"

    @property
    def tasks_url(self) -> str:
        return f"{self.base_url}/apis/evaluator/v2/workspaces/{self.workspace}/tasks"

    @property
    def tasksets_url(self) -> str:
        return f"{self.base_url}/apis/evaluator/v2/workspaces/{self.workspace}/tasksets"
