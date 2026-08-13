# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Container entrypoint for the Data Designer build-dataset job."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from nemo_data_designer_plugin.jobs.build_dataset import BuildDatasetConfig, BuildDatasetJob
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import PlatformJobResults
from nemo_platform_plugin.jobs.constants import (
    EPHEMERAL_TASK_STORAGE_PATH_ENVVAR,
    NEMO_JOB_ID_ENVVAR,
    NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
    NEMO_JOB_WORKSPACE_ENVVAR,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from nemo_platform_plugin.sdk_provider import get_platform_sdk


def run() -> int:
    with open(os.environ[NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR]) as config_file:
        config = BuildDatasetConfig.model_validate_json(config_file.read())
    sdk = get_platform_sdk(as_service="data-designer")
    workspace = os.environ[NEMO_JOB_WORKSPACE_ENVVAR]
    job_id = os.environ[NEMO_JOB_ID_ENVVAR]
    persistent = os.environ.get(PERSISTENT_JOB_STORAGE_PATH_ENVVAR)
    ctx = JobContext(
        workspace=workspace,
        job_id=job_id,
        storage=StoragePaths(
            ephemeral=Path(os.environ[EPHEMERAL_TASK_STORAGE_PATH_ENVVAR]),
            persistent=Path(persistent) if persistent else None,
        ),
        results=PlatformJobResults(workspace=workspace, job_name=job_id, sdk=sdk),
    )
    result = BuildDatasetJob().run(config.model_dump(), ctx=ctx, sdk=sdk)
    exit_code = result.get("exit_code")
    return exit_code if isinstance(exit_code, int) else 1


if __name__ == "__main__":
    sys.exit(run())
