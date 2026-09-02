# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job entrypoint for retrieval hard-negative mining."""

from __future__ import annotations

import os
from pathlib import Path

from nemo_platform import NeMoPlatform
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
from nmp.automodel.tasks.retrieval_mine.runner import RetrievalMineStepConfig, run_mine, work_dir


def _get_ctx(sdk: NeMoPlatform) -> JobContext:
    workspace = os.environ[NEMO_JOB_WORKSPACE_ENVVAR]
    job_name = os.environ[NEMO_JOB_ID_ENVVAR]
    persistent_env = os.environ.get(PERSISTENT_JOB_STORAGE_PATH_ENVVAR)
    storage = StoragePaths(
        ephemeral=Path(os.environ[EPHEMERAL_TASK_STORAGE_PATH_ENVVAR]),
        persistent=Path(persistent_env) if persistent_env else None,
    )
    results = PlatformJobResults(workspace=workspace, job_name=job_name, sdk=sdk)
    return JobContext(workspace=workspace, job_id=job_name, storage=storage, results=results)


def main() -> int:
    with open(os.environ[NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR], encoding="utf-8") as handle:
        spec = RetrievalMineStepConfig.model_validate_json(handle.read())
    sdk = get_platform_sdk(as_service="data-designer")
    ctx = _get_ctx(sdk)
    result = run_mine(
        spec.job_config,
        work_dir(ctx, "stage1_data_prep"),
        ctx,
        model_trust_remote_code=spec.model_trust_remote_code,
    )
    exit_code = result.get("exit_code") if isinstance(result, dict) else 1
    return exit_code if isinstance(exit_code, int) else 1


if __name__ == "__main__":
    raise SystemExit(main())
