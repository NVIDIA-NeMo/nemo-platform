# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import tarfile

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin import client_from_platform
from nemo_platform_plugin.files.client import AsyncFilesClient, FilesClient
from nemo_platform_plugin.jobs.client import AsyncJobsClient, JobsClient
from nemo_platform_plugin.jobs.file_manager import AsyncFilesetFileManager as AsyncFilesetFileManager
from nemo_platform_plugin.jobs.file_manager import FilesetFileManager as FilesetFileManager
from nemo_platform_plugin.jobs.file_manager import TmpDirPath as TmpDirPath
from nemo_platform_plugin.jobs.result_manager import AsyncResultManager as AsyncResultManager
from nemo_platform_plugin.jobs.result_manager import ResultManager as ResultManager


def result_manager_factory(
    job_name: str,
    *,
    attempt_id: str | None = None,
    sdk: NeMoPlatform,
) -> ResultManager:
    """Create a sync ResultManager for uploading job results.

    The nemo_platform_plugin version requires typed client params; this wrapper
    keeps the nmp_common entry point SDK-first and derives clients from it.
    """
    workspace = sdk.workspace
    if not workspace:
        raise ValueError("Result manager requires a workspace-scoped NeMoPlatform SDK")

    return ResultManager(
        job_name=job_name,
        workspace=workspace,
        attempt_id=attempt_id,
        files_client=client_from_platform(sdk, FilesClient),
        jobs_client=client_from_platform(sdk, JobsClient),
    )


def async_result_manager_factory(
    job_name: str,
    *,
    attempt_id: str | None = None,
    sdk: AsyncNeMoPlatform,
) -> AsyncResultManager:
    """Create an async ResultManager for uploading job results."""
    workspace = sdk.workspace
    if not workspace:
        raise ValueError("Async result manager requires a workspace-scoped AsyncNeMoPlatform SDK")

    return AsyncResultManager(
        job_name=job_name,
        workspace=workspace,
        attempt_id=attempt_id,
        files_client=client_from_platform(sdk, AsyncFilesClient),
        jobs_client=client_from_platform(sdk, AsyncJobsClient),
    )


async def download_from_result_info(
    result_name: str,
    job_name: str,
    *,
    artifact_url: str,
    sdk: AsyncNeMoPlatform,
) -> tuple[str, TmpDirPath]:
    """Backward-compatible wrapper that uses the local async result manager factory.

    This ensures that patching ``nmp.common.jobs.result_manager.async_result_manager_factory``
    in tests also affects download_from_result_info, preserving the old monkeypatch
    behavior.
    """
    mgr = async_result_manager_factory(
        job_name=job_name,
        sdk=sdk,
    )

    tmp_dir_path = await mgr.download_artifact(artifact_url=artifact_url)
    filename = result_name

    if tmp_dir_path.path.is_dir():
        filename = f"{filename}.tar.gz"
        tar_path = tmp_dir_path.tmp_dir / filename
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(tmp_dir_path.path, arcname=os.path.basename(tmp_dir_path.path))

        tmp_dir_path.path = tar_path

    return filename, tmp_dir_path
