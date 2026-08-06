# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""On-the-fly aggregate artifact download handler for audit jobs."""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from pathlib import Path

from fastapi import BackgroundTasks, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.dependencies import get_sdk_client
from nemo_platform_plugin.jobs.client import AsyncJobsClient
from nemo_platform_plugin.jobs.result_manager import download_from_result_info

from nemo_auditor.jobs.audit import GARAK_RESULT_NAMES


async def aggregate_artifacts_download(
    workspace: str,
    job: str,
    background_tasks: BackgroundTasks,
    sdk: AsyncNeMoPlatform = Depends(get_sdk_client),
) -> Response:
    """Download all available Garak report results and return them as a single tar.gz."""
    jobs_client = client_from_platform(sdk, AsyncJobsClient)
    all_results = (await jobs_client.list_job_results(name=job, workspace=workspace)).data()
    relevant = [r for r in all_results.data if r.name in GARAK_RESULT_NAMES]

    if not relevant:
        raise HTTPException(status_code=404, detail="No artifact results found for this audit job")

    tmp_dirs = []
    for result in relevant:
        filename, tmp_dir_path = await download_from_result_info(
            result_name=result.name,
            job_name=job,
            workspace=workspace,
            artifact_url=result.artifact_url,
            files_sdk=sdk,
        )
        tmp_dirs.append((filename, tmp_dir_path))
        background_tasks.add_task(tmp_dir_path.cleanup_tmp_dir)

    agg_tmp = Path(tempfile.mkdtemp())
    tar_path = agg_tmp / "artifacts.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for filename, tmp_dir_path in tmp_dirs:
            tar.add(tmp_dir_path.path, arcname=filename)
    background_tasks.add_task(lambda: shutil.rmtree(agg_tmp, ignore_errors=True))

    return FileResponse(path=tar_path, media_type="application/gzip", filename="artifacts.tar.gz")
