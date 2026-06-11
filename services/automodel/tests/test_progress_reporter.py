# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from nemo_platform import omit
from nmp.automodel.app.jobs.context import NMPJobContext
from nmp.automodel.tasks.progress_reporter import JobsServiceProgressReporter
from nmp.common.jobs.schemas import PlatformJobStatus


def test_progress_reporter_calls_sdk_create_or_update() -> None:
    sdk = MagicMock()
    ctx = NMPJobContext(
        workspace="ws-a",
        job_id="job-1",
        attempt_id="attempt-0",
        step="training",
        task="train-model",
        jobs_url="http://jobs.example.com",
        files_url=None,
        storage_path=Path("/tmp/job"),
        config_path=Path("/tmp/job/config.json"),
    )
    reporter = JobsServiceProgressReporter(sdk, ctx.workspace, ctx.job_id, ctx.step, ctx.normalized_task)
    reporter.update_progress(PlatformJobStatus.ACTIVE, status_details={"phase": "training"})

    sdk.jobs.tasks.create_or_update.assert_called_once_with(
        ctx.normalized_task,
        workspace=ctx.workspace,
        job=ctx.job_id,
        step=ctx.step,
        status=PlatformJobStatus.ACTIVE.value,
        status_details={"phase": "training"},
        error_details=omit,
        error_stack=omit,
    )
