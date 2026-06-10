# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import tarfile
from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Literal, Type, TypeVar, overload

from nemo_platform import APIError, AsyncNeMoPlatform, ConflictError, NeMoPlatform
from nemo_platform.filesets import parse_fileset_ref
from nemo_platform.types import PlatformJobResultResponse as SDKPlatformJobResult
from nemo_platform_plugin.jobs.constants import NEMO_JOB_WORKSPACE_ENVVAR
from nemo_platform_plugin.jobs.file_manager import (
    AsyncFilesetFileManager,
    FilesetFileManager,
    TmpDirPath,
)

logger = logging.getLogger(__name__)


class CreateJobResultError(Exception): ...


class FileDoesNotExist(Exception): ...


FileManagerClsT = TypeVar("FileManagerClsT", Type["FilesetFileManager"], Type["AsyncFilesetFileManager"])
PlatformSDKT = TypeVar("PlatformSDKT", "NeMoPlatform", "AsyncNeMoPlatform")


@dataclass
class BaseResultManager(Generic[FileManagerClsT, PlatformSDKT], ABC):
    """
    Base class for sync and async versions of the ResultManager. If there is any common code that can be used across
    both versions of the ResultManager, try to lift it up into this class to reduce duplication.
    """

    job_name: str
    workspace: str
    file_manager_cls: FileManagerClsT
    files_sdk: PlatformSDKT
    jobs_sdk: PlatformSDKT
    attempt_id: str | None = field(default=None)

    def _validate_local_path(self, artifact_local_path: str | Path) -> Path:
        if isinstance(artifact_local_path, str):
            artifact_local_path = Path(artifact_local_path)

        if not artifact_local_path.exists():
            raise FileDoesNotExist(f"No file exists at: {artifact_local_path}")

        return artifact_local_path

    def _result_remote_path(self, attempt_id: str, result_name: str) -> str:
        """Build the remote path for a result artifact."""
        return f"results/{attempt_id}/{result_name}"


@dataclass
class ResultManager(BaseResultManager[Type[FilesetFileManager], NeMoPlatform]):
    def _fetch_job_metadata(self) -> tuple[str, str]:
        """Fetch job and return (attempt_id, fileset_name)."""
        job = self.jobs_sdk.jobs.retrieve(name=self.job_name, workspace=self.workspace)
        attempt_id = self.attempt_id if self.attempt_id is not None else job.attempt_id
        return attempt_id, job.fileset

    def _create_file_manager(self, fileset_name: str) -> FilesetFileManager:
        """Create a file manager for the given fileset."""
        return self.file_manager_cls(
            workspace=self.workspace,
            fileset_name=fileset_name,
            sdk=self.files_sdk,
        )

    def create_result(
        self,
        result_name: str,
        artifact_local_path: str | Path,
        ignore_patterns: list[str] | str | None = None,
    ) -> SDKPlatformJobResult:
        attempt_id, fileset_name = self._fetch_job_metadata()
        file_manager = self._create_file_manager(fileset_name)
        file_manager.validate_storage()
        artifact_local_path = self._validate_local_path(artifact_local_path)
        remote_path = self._result_remote_path(attempt_id, result_name)
        artifact_url = file_manager.upload(
            local_path=artifact_local_path, remote_path=remote_path, ignore_patterns=ignore_patterns
        )
        try:
            job_result = self.jobs_sdk.jobs.results.create(
                name=result_name,
                job=self.job_name,
                workspace=self.workspace,
                artifact_url=artifact_url,
                artifact_storage_type=file_manager.storage_type().value,
            )
        except ConflictError:
            # Result already exists - fetch and return the existing one
            # This supports the use case of saving partial results across multiple batches
            job_result = self.jobs_sdk.jobs.results.retrieve(
                name=result_name,
                job=self.job_name,
                workspace=self.workspace,
            )
        except APIError as e:
            msg = f"Error creating job result: {str(e)}"
            logger.exception(msg)
            raise CreateJobResultError(msg) from e

        return job_result

    def download_artifact(self, artifact_url: str, local_dir: str | Path | None = None) -> TmpDirPath:
        _, fileset_name, _ = parse_fileset_ref(artifact_url, workspace_fallback=self.workspace)
        if fileset_name is None:
            raise ValueError(f"Could not extract fileset name from URL: {artifact_url}")
        file_manager = self._create_file_manager(fileset_name)
        return file_manager.download_from_url(url=artifact_url, local_dir=local_dir)


@dataclass
class AsyncResultManager(BaseResultManager[Type[AsyncFilesetFileManager], AsyncNeMoPlatform]):
    async def _fetch_job_metadata(self) -> tuple[str, str]:
        """Fetch job and return (attempt_id, fileset_name)."""
        job = await self.jobs_sdk.jobs.retrieve(name=self.job_name, workspace=self.workspace)
        attempt_id = self.attempt_id if self.attempt_id is not None else job.attempt_id
        return attempt_id, job.fileset

    def _create_file_manager(self, fileset_name: str) -> AsyncFilesetFileManager:
        """Create a file manager for the given fileset."""
        return self.file_manager_cls(
            workspace=self.workspace,
            fileset_name=fileset_name,
            sdk=self.files_sdk,
        )

    async def create_result(
        self,
        result_name: str,
        artifact_local_path: str | Path,
        ignore_patterns: list[str] | str | None = None,
    ) -> SDKPlatformJobResult:
        attempt_id, fileset_name = await self._fetch_job_metadata()
        file_manager = self._create_file_manager(fileset_name)
        await file_manager.validate_storage()
        artifact_local_path = self._validate_local_path(artifact_local_path)
        remote_path = self._result_remote_path(attempt_id, result_name)
        artifact_url = await file_manager.upload(
            local_path=artifact_local_path, remote_path=remote_path, ignore_patterns=ignore_patterns
        )
        try:
            job_result = await self.jobs_sdk.jobs.results.create(
                name=result_name,
                job=self.job_name,
                workspace=self.workspace,
                artifact_url=artifact_url,
                artifact_storage_type=file_manager.storage_type().value,
            )
        except ConflictError:
            # Result already exists - fetch and return the existing one
            # This supports the use case of saving partial results across multiple batches
            job_result = await self.jobs_sdk.jobs.results.retrieve(
                name=result_name,
                job=self.job_name,
                workspace=self.workspace,
            )
        except APIError as e:
            msg = f"Error creating job result: {str(e)}"
            logger.exception(msg)
            raise CreateJobResultError(msg) from e

        return job_result

    async def download_artifact(self, artifact_url: str, local_dir: str | Path | None = None) -> TmpDirPath:
        _, fileset_name, _ = parse_fileset_ref(artifact_url, workspace_fallback=self.workspace)
        if fileset_name is None:
            raise ValueError(f"Could not extract fileset name from URL: {artifact_url}")
        file_manager = self._create_file_manager(fileset_name)
        return await file_manager.download_from_url(url=artifact_url, local_dir=local_dir)


@overload
def result_manager_factory(
    job_name: str,
    *,
    attempt_id: str | None = None,
    workspace: str | None = None,
    files_sdk: AsyncNeMoPlatform,
    jobs_sdk: AsyncNeMoPlatform | None = None,
    is_async: Literal[True] = True,
) -> AsyncResultManager: ...


@overload
def result_manager_factory(
    job_name: str,
    *,
    attempt_id: str | None = None,
    workspace: str | None = None,
    files_sdk: NeMoPlatform,
    jobs_sdk: NeMoPlatform | None = None,
    is_async: Literal[False],
) -> ResultManager: ...


def result_manager_factory(
    job_name: str,
    *,
    attempt_id: str | None = None,
    workspace: str | None = None,
    files_sdk: NeMoPlatform | AsyncNeMoPlatform,
    jobs_sdk: NeMoPlatform | AsyncNeMoPlatform | None = None,
    is_async: bool = True,
) -> ResultManager | AsyncResultManager:
    """Create a ResultManager for uploading job results.

    Args:
        job_name: Name of the job to create results for.
        attempt_id: Optional attempt ID for the job.
        workspace: Job workspace. If not provided, reads from NEMO_JOB_WORKSPACE env var.
        files_sdk: SDK instance for file operations (required).
        jobs_sdk: SDK instance for job operations. If not provided, uses files_sdk.
        is_async: Whether to create an async result manager.

    Returns:
        ResultManager or AsyncResultManager instance.
    """

    if workspace is None:
        workspace = _get_job_workspace()

    if jobs_sdk is None:
        jobs_sdk = files_sdk

    file_manager_cls = AsyncFilesetFileManager if is_async else FilesetFileManager
    result_manager_cls = AsyncResultManager if is_async else ResultManager
    return result_manager_cls(
        job_name=job_name,
        workspace=workspace,
        attempt_id=attempt_id,
        file_manager_cls=file_manager_cls,  # type: ignore
        files_sdk=files_sdk,  # type: ignore
        jobs_sdk=jobs_sdk,  # type: ignore
    )


def _get_job_workspace() -> str:
    workspace = os.getenv(NEMO_JOB_WORKSPACE_ENVVAR)
    if not workspace:
        raise ValueError(f"{NEMO_JOB_WORKSPACE_ENVVAR} environment variable is not set")
    return workspace


async def download_from_result_info(
    result_name: str,
    job_name: str,
    *,
    artifact_url: str,
    workspace: str | None = None,
    files_sdk: AsyncNeMoPlatform,
) -> tuple[str, TmpDirPath]:
    """
    This is a helper composition function that creates a result_manager
    and prepares the artifact for download.

    Returns:
        A tuple containing:
          - filename (str): The final filename of the artifact (may include .tar.gz extension if compressed)
          - tmp_dir_path (TmpDirPath): Path object pointing to the downloaded artifact
    """
    result_manager = result_manager_factory(
        job_name=job_name,
        workspace=workspace,
        files_sdk=files_sdk,
    )

    tmp_dir_path = await result_manager.download_artifact(artifact_url=artifact_url)
    filename = result_name

    if tmp_dir_path.path.is_dir():
        filename = f"{filename}.tar.gz"
        tar_path = tmp_dir_path.tmp_dir / filename
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(tmp_dir_path.path, arcname=os.path.basename(tmp_dir_path.path))

        tmp_dir_path.path = tar_path

    return filename, tmp_dir_path
