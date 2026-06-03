# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import tarfile
from typing import Literal, overload

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.jobs.constants import NEMO_JOB_WORKSPACE_ENVVAR
from nemo_platform_plugin.jobs.file_manager import AsyncFilesetFileManager as AsyncFilesetFileManager
from nemo_platform_plugin.jobs.file_manager import FilesetFileManager as FilesetFileManager
from nemo_platform_plugin.jobs.file_manager import TmpDirPath as TmpDirPath
from nemo_platform_plugin.jobs.result_manager import AsyncResultManager as AsyncResultManager
from nemo_platform_plugin.jobs.result_manager import ResultManager as ResultManager
from nmp.common.sdk_factory import get_async_platform_sdk, get_platform_sdk


@overload
def result_manager_factory(
    job_name: str,
    *,
    attempt_id: str | None = None,
    workspace: str | None = None,
    files_sdk: AsyncNeMoPlatform | None = None,
    jobs_sdk: AsyncNeMoPlatform | None = None,
    is_async: Literal[True] = True,
) -> AsyncResultManager: ...


@overload
def result_manager_factory(
    job_name: str,
    *,
    attempt_id: str | None = None,
    workspace: str | None = None,
    files_sdk: NeMoPlatform | None = None,
    jobs_sdk: NeMoPlatform | None = None,
    is_async: Literal[False],
) -> ResultManager: ...


def result_manager_factory(
    job_name: str,
    *,
    attempt_id: str | None = None,
    workspace: str | None = None,
    files_sdk: NeMoPlatform | AsyncNeMoPlatform | None = None,
    jobs_sdk: NeMoPlatform | AsyncNeMoPlatform | None = None,
    is_async: bool = True,
) -> ResultManager | AsyncResultManager:
    """Create a ResultManager for uploading job results.

    Backward-compatible wrapper that auto-creates SDK instances from platform
    config when not provided. The nemo_platform_plugin version requires SDK params;
    this wrapper provides the old convenience defaults.
    """
    if workspace is None:
        workspace_env = os.getenv(NEMO_JOB_WORKSPACE_ENVVAR)
        if not workspace_env:
            raise ValueError(f"{NEMO_JOB_WORKSPACE_ENVVAR} environment variable is not set")
        workspace = workspace_env

    if files_sdk is None:
        files_sdk = get_async_platform_sdk() if is_async else get_platform_sdk()

    if jobs_sdk is None:
        jobs_sdk = get_async_platform_sdk() if is_async else get_platform_sdk()

    file_manager_cls = AsyncFilesetFileManager if is_async else FilesetFileManager
    result_manager_cls = AsyncResultManager if is_async else ResultManager
    return result_manager_cls(
        job_name=job_name,
        workspace=workspace,
        attempt_id=attempt_id,
        file_manager_cls=file_manager_cls,
        files_sdk=files_sdk,
        jobs_sdk=jobs_sdk,
    )


async def download_from_result_info(
    result_name: str,
    job_name: str,
    *,
    artifact_url: str,
    workspace: str | None = None,
    files_sdk: AsyncNeMoPlatform | None = None,
) -> tuple[str, TmpDirPath]:
    """Backward-compatible wrapper that uses the local result_manager_factory.

    This ensures that patching ``nmp.common.jobs.result_manager.result_manager_factory``
    in tests also affects download_from_result_info, preserving the old monkeypatch
    behavior.
    """
    if files_sdk is None:
        files_sdk = get_async_platform_sdk()

    mgr = result_manager_factory(
        job_name=job_name,
        workspace=workspace,
        files_sdk=files_sdk,
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
