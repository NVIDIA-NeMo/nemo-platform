# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""File I/O task entry point.

Handles file operations between NeMo Platform Files Service and the job's shared PVC.

The task reads configuration and performs:
- Downloads: If config.download is non-empty, download files from FileSets to local paths
- Uploads: If config.upload is non-empty, upload files from local paths to FileSets

Usage:
    export NEMO_JOB_STEP_CONFIG_FILE_PATH=<path to job_step_config.json>
    python -m nmp.unsloth.tasks.file_io
"""

import logging
from pathlib import Path

import httpx

# https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#handling-errors
from nemo_platform import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    NeMoPlatform,
    NotFoundError,
)
from nemo_platform.types.files.fileset_file import FilesetFile
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.errors import (
    ConflictError,
)
from nemo_platform_plugin.client.errors import (
    InternalServerError as ClientInternalServerError,
)
from nemo_platform_plugin.client.types import RetryPolicy
from nemo_platform_plugin.files.client import FilesClient
from nemo_platform_plugin.files.types import CreateFilesetRequest, UpdateFilesetRequest
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.common.sdk_factory import get_task_sdk
from nmp.customization_common.schemas.file_io import (
    DownloadItem,
    DownloadStats,
    FileDownloadError,
    FileSetRef,
    FileUploadError,
    PathTraversalError,
    TaskPhase,
    UploadItem,
    UploadStats,
)
from nmp.customization_common.service.context import NMPJobContext
from nmp.customization_common.tasks.file_io_progress_reporter import JobsServiceProgressReporter, ProgressReporter
from nmp.customization_common.tasks.file_io_utils import (
    filesystem_sdk_error_handler,
    get_config,
    sdk_error_handler,
    validate_safe_path,
    validate_storage_path,
)
from nmp.unsloth.app.constants import SERVICE_NAME
from nmp.unsloth.tasks.file_io.callbacks import (
    CompositeCallback,
    FileDownloadProgressCallback,
    FileUploadProgressCallback,
    TqdmPerFileDownloadCallback,
    TqdmPerFileUploadCallback,
)
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Service-source tag stamped onto every upload-created fileset. Lets operators
# filter filesets by training backend.
SERVICE_SOURCE = "unsloth"

CREATE_FILESET_TIMEOUT = 10.0
LIST_FILES_TIMEOUT = httpx.Timeout(10.0, connect=10.0)

# Timeout configurations for FilesetFileSystem operations. Passed via
# sdk.with_options(timeout=...). httpx.Timeout(read=...) is per-chunk
# (the SDK chunks at 16MB), NOT total transfer time — it's a socket-level
# timeout. SDK defaults are httpx.Timeout(timeout=60, connect=5.0).
DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, read=5 * 60)
UPLOAD_TIMEOUT = httpx.Timeout(30.0, write=10 * 60, read=5 * 60)

# Retry configuration.
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0

# Transient exceptions that should trigger retries for filesystem operations.
# FilesetFileSystem uses httpx under the hood, so we retry httpx transients
# in addition to SDK-level transients.
TRANSIENT_FILESYSTEM_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadTimeout,
    # Connection dropped mid-transfer (CDN/proxy closed the socket before the
    # full body arrived). Common on large multi-GB model shards; safe to retry.
    httpx.RemoteProtocolError,
    httpx.ReadError,
)


class FileIORunner:
    """Runner for file I/O operations against the Files service."""

    def __init__(
        self,
        sdk: NeMoPlatform,
        progress_reporter: ProgressReporter,
        job_ctx: NMPJobContext,
    ):
        self.sdk = sdk
        self.progress_reporter = progress_reporter
        self.job_ctx = job_ctx

    def list_fileset_files(self, fileset: FileSetRef) -> list[FilesetFile]:
        """List files in a FileSet. Returns a list of ``FilesetFile`` objects."""
        try:
            with sdk_error_handler(FileDownloadError, f"list files in fileset {fileset}", passthrough=(NotFoundError,)):
                response = self.sdk.with_options(timeout=LIST_FILES_TIMEOUT).files.list(
                    fileset=fileset.name,
                    workspace=fileset.workspace,
                )
                logger.info(f"Found {len(response.data)} files in FileSet {fileset!s}")
                return response.data
        except NotFoundError as e:
            raise FileDownloadError(
                f"FileSet {fileset!s} not found. Please ensure the FileSet exists and contains the expected files.",
            ) from e

    def download_fileset(self, fileset: FileSetRef, dest_dir: Path) -> DownloadStats:
        """Download all files from a FileSet to a destination directory.

        Uses ``FilesetFileSystem.get()`` with ``recursive=True`` for efficient batch
        downloads. Progress is tracked via two callbacks combined in a
        ``CompositeCallback``:

        - ``TqdmPerFileDownloadCallback`` — separate console progress bar per file
        - ``FileDownloadProgressCallback`` — reports to Jobs service after each file

        Raises:
            FileDownloadError: If the download fails.
        """
        stats = DownloadStats()
        fileset_name = str(fileset)

        files = self.list_fileset_files(fileset)

        if not files:
            logger.warning(f"FileSet {fileset_name} contains no files")
            return stats

        total_files = len(files)
        total_size = sum(f.size for f in files)

        dest_dir.mkdir(parents=True, exist_ok=True)

        # Maps relative file paths to byte sizes for tqdm percent display.
        file_sizes = {f.path.lstrip("/"): f.size for f in files}

        tqdm_callback = TqdmPerFileDownloadCallback(
            dest_path=dest_dir,
            fileset_path=fileset_name,
            file_sizes=file_sizes,
        )
        jobs_callback = FileDownloadProgressCallback(
            progress_reporter=self.progress_reporter,
            fileset_name=fileset_name,
            total_files=total_files,
            total_size=total_size,
            stats=stats,
        )
        composite_callback = CompositeCallback(tqdm_callback, jobs_callback)

        with filesystem_sdk_error_handler(
            FileDownloadError,
            f"download from '{fileset_name}' to '{dest_dir}'",
        ):
            self._download_with_retry(
                fileset_name=fileset.name,
                fileset_workspace=fileset.workspace,
                dest_dir=str(dest_dir),
                callback=composite_callback,
            )

        logger.info(f"Download complete: {stats.files_downloaded} files, {stats.total_bytes} bytes")
        return stats

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=INITIAL_BACKOFF_SECONDS, max=MAX_BACKOFF_SECONDS),
        retry=retry_if_exception_type(TRANSIENT_FILESYSTEM_EXCEPTIONS),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _download_with_retry(
        self,
        fileset_name: str,
        fileset_workspace: str | None,
        dest_dir: str,
        callback: CompositeCallback,
    ) -> None:
        """Internal method with retry logic for downloading from FilesetFileSystem."""
        self.sdk.with_options(timeout=DOWNLOAD_TIMEOUT).files.download(
            fileset=fileset_name,
            workspace=fileset_workspace,
            local_path=dest_dir,
            callback=callback,
        )

    def upload_fileset(self, fileset: FileSetRef, src_path: Path) -> UploadStats:
        """Upload all files from a source path (file or directory) to a FileSet.

        Uses ``FilesetFileSystem.put()`` with ``recursive=True`` for efficient batch
        uploads. Progress is tracked via the same composite-callback pattern as
        downloads.

        Raises:
            FileUploadError: If the upload fails.
        """
        stats = UploadStats()
        fileset_name = str(fileset)

        tqdm_callback = TqdmPerFileUploadCallback(src_path=src_path)
        jobs_callback = FileUploadProgressCallback(
            progress_reporter=self.progress_reporter,
            src_path=src_path,
            fileset_name=fileset_name,
            stats=stats,
        )
        composite_callback = CompositeCallback(tqdm_callback, jobs_callback)

        # Build local and remote paths for upload. ``remote_path`` is relative within
        # the fileset ("" for root, "filename" for single file). Trailing slash on
        # ``local_path`` follows rsync/scp convention: "dir/" copies contents,
        # "dir" copies the directory itself.
        if src_path.is_dir():
            local_path = f"{src_path}/"
            remote_path = ""
        else:
            local_path = str(src_path)
            remote_path = src_path.name

        with filesystem_sdk_error_handler(
            FileUploadError,
            f"upload from '{src_path}' to '{fileset_name}'",
        ):
            self._upload_with_retry(
                local_path=local_path,
                remote_path=remote_path,
                fileset_name=fileset.name,
                fileset_workspace=fileset.workspace,
                callback=composite_callback,
            )

        logger.info(f"Upload complete: {stats.files_uploaded} files, {stats.total_bytes} bytes")
        return stats

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=INITIAL_BACKOFF_SECONDS, max=MAX_BACKOFF_SECONDS),
        retry=retry_if_exception_type(TRANSIENT_FILESYSTEM_EXCEPTIONS),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING, exc_info=True),
    )
    def _upload_with_retry(
        self,
        local_path: str,
        remote_path: str,
        fileset_name: str,
        fileset_workspace: str | None,
        callback: CompositeCallback,
    ) -> None:
        """Internal method with retry logic for uploading to FilesetFileSystem."""
        self.sdk.with_options(timeout=UPLOAD_TIMEOUT).files.upload(
            local_path=local_path,
            remote_path=remote_path,
            fileset=fileset_name,
            workspace=fileset_workspace,
            callback=callback,
        )

    def create_fileset(self, fileset: FileSetRef, metadata: dict | None = None) -> None:
        """Create a FileSet. Skip if it already exists.

        Wraps the retry with ``sdk_error_handler`` to convert exceptions after
        all retries exhaust.
        """
        with sdk_error_handler(FileUploadError, f"create fileset {fileset}", passthrough=(ConflictError,)):
            self._create_fileset_with_retry(fileset, metadata)

    # We don't use the SDK's built-in retry: it would retry on ConflictError,
    # which is expected here and would just waste calls.
    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=2, min=INITIAL_BACKOFF_SECONDS, max=MAX_BACKOFF_SECONDS),
        retry=retry_if_exception_type(
            (
                InternalServerError,
                APITimeoutError,
                APIConnectionError,
                ClientInternalServerError,
                httpx.TimeoutException,
                httpx.ConnectError,
            )
        ),
        reraise=True,
    )
    def _create_fileset_with_retry(self, fileset: FileSetRef, metadata: dict | None = None) -> None:
        """Internal method with retry logic for creating a FileSet."""
        files = client_from_platform(self.sdk, FilesClient).with_options(
            timeout=CREATE_FILESET_TIMEOUT, retry=RetryPolicy(max_retries=0)
        )
        try:
            body_kwargs: dict = {
                "name": fileset.name,
                "custom_fields": {"service_source": SERVICE_SOURCE},
            }
            if metadata is not None:
                body_kwargs["metadata"] = metadata
            result = files.create_fileset(workspace=fileset.workspace, body=CreateFilesetRequest(**body_kwargs)).data()
            logger.info(f"Created FileSet: {result.workspace}/{result.name}")
        except ConflictError:
            workspace = fileset.workspace or self.job_ctx.workspace
            if metadata is not None:
                try:
                    files.update_fileset(
                        workspace=workspace,
                        name=fileset.name,
                        body=UpdateFilesetRequest(metadata=metadata),
                    )
                    logger.info(f"Patched existing FileSet metadata: {workspace}/{fileset.name}")
                except Exception as e:
                    logger.warning(
                        f"Could not patch metadata on existing fileset {workspace}/{fileset.name}: {e}. "
                        "Upload will continue; downstream consumers may lack the latest metadata.",
                    )

    def run_download(self, downloads: list[DownloadItem]) -> None:
        """Execute download operations."""
        if not downloads:
            logger.info("No downloads configured, skipping download operation")
            return

        storage_path = validate_storage_path(self.job_ctx.storage_path)

        logger.info(f"Starting download operation: {len(downloads)} fileset(s) to download")

        self.progress_reporter.update_progress(
            status=PlatformJobStatus.ACTIVE,
            status_details={
                "phase": TaskPhase.DOWNLOADING,
                "total_filesets": len(downloads),
                "completed_filesets": 0,
            },
        )

        total_stats = DownloadStats()

        for idx, item in enumerate(downloads):
            fileset = item.src
            dest_dir = validate_safe_path(storage_path, item.dest)

            logger.info(f"[{idx + 1}/{len(downloads)}] Downloading from {fileset!s} to {dest_dir}")

            self.progress_reporter.update_progress(
                status=PlatformJobStatus.ACTIVE,
                status_details={
                    "phase": TaskPhase.DOWNLOADING,
                    "total_filesets": len(downloads),
                    "completed_filesets": idx,
                    "current_fileset": f"{fileset!s}",
                },
            )

            stats = self.download_fileset(fileset, dest_dir)
            total_stats.files_downloaded += stats.files_downloaded
            total_stats.total_bytes += stats.total_bytes

            logger.info(f"FileSet download complete: {stats.files_downloaded} files, {stats.total_bytes} bytes")

        logger.info(
            f"All downloads complete: {total_stats.files_downloaded} files, {total_stats.total_bytes} bytes total",
        )

    def run_upload(self, uploads: list[UploadItem]) -> None:
        """Execute upload operations."""
        if not uploads:
            logger.info("No uploads configured, skipping upload operation")
            return

        storage_path = validate_storage_path(self.job_ctx.storage_path)

        logger.info(f"Starting upload operation: {len(uploads)} fileset(s) to upload")

        self.progress_reporter.update_progress(
            status=PlatformJobStatus.ACTIVE,
            status_details={
                "phase": TaskPhase.UPLOADING,
                "total_filesets": len(uploads),
                "completed_filesets": 0,
            },
        )

        total_stats = UploadStats()

        for idx, item in enumerate(uploads):
            if item.dest.workspace is None:
                item.dest.workspace = self.job_ctx.workspace
            fileset = item.dest
            src_path = validate_safe_path(storage_path, item.src)
            if not src_path.exists():
                raise FileUploadError(f"Source path does not exist: {src_path}. Ensure the source path exists.")
            if not src_path.is_dir() and not src_path.is_file():
                raise FileUploadError(
                    f"Source path is not a file or directory: {src_path}. "
                    "Ensure the source path is a file or directory.",
                )

            logger.info(f"[{idx + 1}/{len(uploads)}] Uploading from {src_path} to {fileset!s}")

            self.progress_reporter.update_progress(
                status=PlatformJobStatus.ACTIVE,
                status_details={
                    "phase": TaskPhase.UPLOADING,
                    "total_filesets": len(uploads),
                    "completed_filesets": idx,
                    "current_fileset": str(fileset),
                },
            )

            self.create_fileset(fileset, metadata=item.metadata)

            stats = self.upload_fileset(fileset, src_path)
            total_stats.files_uploaded += stats.files_uploaded
            total_stats.total_bytes += stats.total_bytes

            logger.info(f"FileSet upload complete: {stats.files_uploaded} files, {stats.total_bytes} bytes")

        logger.info(f"All uploads complete: {total_stats.files_uploaded} files, {total_stats.total_bytes} bytes total")


def run(sdk: NeMoPlatform | None = None, job_ctx: NMPJobContext | None = None) -> int:
    """Execute the file I/O task.

    Args:
        sdk: Optional SDK instance for dependency injection (for testing).
            If None, creates one via get_task_sdk().
        job_ctx: Optional job context for dependency injection (for testing).
            If None, creates one via NMPJobContext.from_env().

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    job_ctx = job_ctx or NMPJobContext.from_env()
    validate_storage_path(job_ctx.storage_path)

    sdk_owned = sdk is None
    progress_reporter: ProgressReporter | None = None
    try:
        sdk = sdk or get_task_sdk(SERVICE_NAME)
        progress_reporter = JobsServiceProgressReporter.create_progress_reporter(sdk, job_ctx)
        runner = FileIORunner(sdk=sdk, progress_reporter=progress_reporter, job_ctx=job_ctx)

        config = get_config(job_ctx.config_path)

        logger.info(f"Starting file I/O task with job context: {job_ctx}")
        logger.info(f"Config: {config.model_dump_json(indent=2)}")
        logger.info(f"NeMo Platform service URL: {sdk.base_url}")

        runner.run_upload(config.upload)
        runner.run_download(config.download)

        progress_reporter.update_progress(
            status=PlatformJobStatus.COMPLETED,
            status_details={"phase": TaskPhase.COMPLETED, "message": "File I/O task completed successfully"},
        )

        return 0
    except PathTraversalError as e:
        logger.error(f"Security error - path traversal detected: {e}")
        if progress_reporter:
            progress_reporter.update_progress(
                status=PlatformJobStatus.ERROR,
                error_details={"message": str(e), "type": type(e).__name__},
            )
        return 1
    except (FileDownloadError, FileUploadError) as e:
        logger.exception(f"File operation failed: {e}")
        if progress_reporter:
            progress_reporter.update_progress(
                status=PlatformJobStatus.ERROR,
                error_details={"message": str(e), "type": type(e).__name__},
            )
        return 1
    except Exception as e:
        logger.exception(f"File I/O task failed: {e}")
        if progress_reporter:
            progress_reporter.update_progress(
                status=PlatformJobStatus.ERROR,
                error_details={"message": str(e), "type": type(e).__name__},
            )
        return 1
    finally:
        if sdk_owned and sdk is not None:
            sdk.close()


def build_output_metadata(spec) -> dict:
    """Build the metadata dict stamped onto the output fileset.

    Captures the bits a downstream consumer (model-entity creation,
    deployment) needs about this artefact without re-deriving them
    from the training spec.
    """
    return {
        "model": spec.model.name,
        "finetuning_type": spec.training.finetuning_type,
        "save_method": spec.output.save_method,
        "output_type": spec.output.type,
    }
