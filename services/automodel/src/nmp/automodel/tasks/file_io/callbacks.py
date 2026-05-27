# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Custom fsspec callbacks for progress reporting during file I/O operations."""

import logging
import os
import threading
from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fsspec.callbacks import Callback, TqdmCallback
from nmp.automodel.app.jobs.file_io.schemas import DownloadStats, TaskPhase, UploadStats
from nmp.automodel.tasks.file_io.progress_reporter import ProgressReporter
from nmp.common.jobs.schemas import PlatformJobStatus

logger = logging.getLogger(__name__)


def get_percentage(current: int, total: int) -> int:
    """Get percentage of current / total.

    Args:
        current: The current value (numerator).
        total: The total value (denominator).

    Returns:
        Integer percentage from 0-100.

    Raises:
        ValueError: If current > total, or if either value is negative.

    """
    if current > total:
        raise ValueError(
            f"Unexpected value of the current and total values: current={current} cannot be greater than total={total}",
        )
    if total < 0:
        raise ValueError(f"Unexpected negative value of the total value: total={total}, current={current}")
    if current < 0:
        raise ValueError(f"Unexpected negative value of the current value: current={current}, total={total}")

    if total == 0:
        return 0
    return int((current / total) * 100)


@dataclass
class FileInfo:
    """A dataclass for file information."""

    path: str
    size: int


class TqdmPerFileUploadCallback(Callback):
    """A callback that creates a separate tqdm progress bar for each file.

    Unlike TqdmCallback which shows overall progress, this callback creates a new
    tqdm progress bar when branched() is called for each file. Each file's progress
    bar shows byte-level progress for that individual file.

    Usage:
        callback = TqdmPerFileUploadCallback()
        filesystem_sdk.put(src, dest, recursive=True, callback=callback)
        # Creates a separate progress bar for each file being uploaded
    """

    def __init__(self, src_path: Path, **kwargs: Any):
        """Initialize the per-file tqdm callback.

        Args:
            **kwargs: Additional arguments passed to the base Callback.

        """
        self.src_path = src_path
        super().__init__(**kwargs)

    def branched(self, full_src_path: str, full_dest_path: str, **kwargs: Any) -> TqdmCallback:
        """Create a TqdmCallback for this specific file transfer.

        Args:
            full_src_path: Source file path.
            full_dest_path: Destination file path.
            **kwargs: Additional keyword arguments.

        Returns:
            A TqdmCallback configured for byte-level progress of this file.

        """
        # Extract just the filename for the progress bar description
        if self.src_path.is_file():
            relative_path_upload_dir = self.src_path.name
        else:
            relative_path_upload_dir = Path(full_src_path).relative_to(self.src_path)
        return TqdmCallback(
            # https://tqdm.github.io/docs/tqdm
            tqdm_kwargs={
                "desc": f"Uploading {relative_path_upload_dir!s}",
                # use bytes as the unit
                "unit": "B",
                # scale the unit to be more readable (e.g. 1024 bytes = 1 KB)
                "unit_scale": True,
                # divide the unit by 1024 to get the next unit
                "unit_divisor": 1024,
                # The minimum number of iterations (bytes processed) that must occur before the progress bar refreshes
                "miniters": 1,
            },
        )


class TqdmPerFileDownloadCallback(Callback):
    """A callback that creates a separate tqdm progress bar for each file download.

    Similar to TqdmPerFileUploadCallback but for download operations. Creates a new
    tqdm progress bar when branched() is called for each file being downloaded.

    The callback accepts a file_sizes dict to set the total size for each file's
    progress bar. This is necessary because the SDK may not receive Content-Length
    headers for streaming downloads (e.g., when chunked transfer encoding is used).

    Usage:
        # Build file_sizes from listing
        files = list_fileset_files(fileset)
        file_sizes = {f.path.lstrip("/"): f.size for f in files}

        callback = TqdmPerFileDownloadCallback(
            dest_path=dest_dir,
            fileset_path="workspace/fileset",
            file_sizes=file_sizes,
        )
        filesystem_sdk.get(src, dest, recursive=True, callback=callback)
        # Creates a separate progress bar for each file being downloaded
    """

    def __init__(self, dest_path: Path, fileset_path: str, file_sizes: dict[str, int] | None = None, **kwargs: Any):
        """Initialize the per-file tqdm download callback.

        Args:
            dest_path: The local destination directory path.
            fileset_path: The fileset path (e.g., "workspace/fileset") used to extract
                          relative file paths from full source paths.
            file_sizes: Optional dict mapping relative file paths to their sizes in bytes.
                        Used to set the progress bar's total for percentage display.
            **kwargs: Additional arguments passed to the base Callback.

        """
        self.dest_path = dest_path
        self.fileset_path = fileset_path.rstrip("/")
        self.file_sizes = file_sizes or {}
        super().__init__(**kwargs)

    def branched(self, full_src_path: str, full_dest_path: str, **kwargs: Any) -> TqdmCallback:
        """Create a TqdmCallback for this specific file download.

        Args:
            full_src_path: Source file path in the fileset (e.g., "workspace/fileset/dir/file.txt").
            full_dest_path: Destination local file path.
            **kwargs: Additional keyword arguments.

        Returns:
            A TqdmCallback configured for byte-level progress of this file.

        """
        # Extract relative path for the progress bar description
        # full_dest_path is the full local path, we want to show just the filename or relative path
        dest_full_path = Path(full_dest_path)
        if self.dest_path.is_file():
            relative_path = dest_full_path.name
        else:
            try:
                relative_path = dest_full_path.relative_to(self.dest_path)
            except ValueError:
                # If can't compute relative path, use filename
                relative_path = dest_full_path.name

        # Extract relative file path from full source path to look up size
        # full_src_path format: "workspace/fileset/relative/path/to/file.txt"
        # We need to extract "relative/path/to/file.txt"
        relative_file_path = full_src_path
        if full_src_path.startswith(self.fileset_path):
            relative_file_path = full_src_path[len(self.fileset_path) :].lstrip("/")

        # Look up file size from pre-computed mapping
        file_size = self.file_sizes.get(relative_file_path)

        callback = TqdmCallback(
            tqdm_kwargs={
                "desc": f"Downloading {relative_path!s}",
                "unit": "B",
                "unit_scale": True,
                "unit_divisor": 1024,
                "miniters": 1,
            },
        )

        # Set size if we know it - this enables percentage display in tqdm
        # Must be called via set_size() rather than tqdm_kwargs["total"] because
        # the SDK may also call set_size() from Content-Length header
        if file_size is not None:
            callback.set_size(file_size)

        return callback


class BaseProgressCallback(Callback):
    """Base class for file upload/download progress callbacks.

    This abstract base class provides common functionality for tracking file transfer
    progress and reporting to the Jobs service. Subclasses implement operation-specific
    behavior (upload vs download).

    Thread Safety:
        This callback uses threading.Lock for synchronization. FilesetFileSystem is
        async-first and transfers files concurrently. The lock protects against
        concurrent access when multiple files complete simultaneously.

    Attributes:
        progress_reporter: The progress reporter for sending updates to Jobs service.
        fileset_name: The name of the fileset (workspace/name format).
        total_files: Total number of files to transfer.
        total_size: Total size of all files in bytes.
        stats: Mutable stats object to track progress (UploadStats or DownloadStats).
        _lock: Threading lock for thread-safe stats updates.

    """

    progress_reporter: ProgressReporter
    fileset_name: str
    total_files: int
    total_size: int
    stats: UploadStats | DownloadStats
    _lock: threading.Lock

    def __init__(
        self,
        progress_reporter: ProgressReporter,
        fileset_name: str,
        total_files: int,
        total_size: int,
        stats: UploadStats | DownloadStats,
        **kwargs: Any,
    ):
        """Initialize the progress callback.

        Args:
            progress_reporter: The progress reporter for sending updates to Jobs service.
            fileset_name: The name of the fileset (workspace/name format).
            total_files: Total number of files to transfer.
            total_size: Total size of all files in bytes.
            stats: Mutable stats object to track progress.
            **kwargs: Additional arguments passed to the base Callback.

        """
        super().__init__(**kwargs)
        self.progress_reporter = progress_reporter
        self.fileset_name = str(fileset_name)
        self.total_files = total_files
        self.total_size = total_size
        self.stats = stats
        self._lock = threading.Lock()

    @staticmethod
    def list_local_files(src_path: Path) -> list[FileInfo]:
        """List all files from a local path (file or directory).

        If src_path is a file, returns a single FileInfo with the filename.
        If src_path is a directory, recursively lists all files.

        Returns list of FileInfo objects with 'path' (relative path) and 'size' keys.
        This mirrors the format returned by list_fileset_files.
        """
        if not src_path.exists():
            logger.warning(f"Failed to list local files. Source path does not exist: {src_path}")
            return []

        try:
            # Handle single file
            if src_path.is_file():
                logger.info(f"Found 1 file: {src_path.name}")
                return [
                    FileInfo(
                        path=src_path.name,
                        size=src_path.stat().st_size,
                    ),
                ]

            # Handle directory
            files = []
            for root, _, filenames in os.walk(src_path):
                for filename in filenames:
                    full_path = Path(root) / filename
                    relative_path = full_path.relative_to(src_path)
                    files.append(
                        FileInfo(
                            path=str(relative_path),
                            size=full_path.stat().st_size,
                        ),
                    )
            logger.info(f"Found {len(files)} files in {src_path}")
            return files
        except Exception as e:
            logger.warning(f"Failed to list local files. Source path: {src_path}. Error: {e}")
            return []

    @abstractmethod
    def branched(self, source_path: str, dest_path: str, **kwargs: Any) -> "BaseSingleFileCallback":
        """Create a child callback for a single file transfer.

        Args:
            source_path: Source file path.
            dest_path: Destination file path.
            **kwargs: Additional keyword arguments.

        Returns:
            A BaseSingleFileCallback subclass for tracking this file's transfer.

        """
        ...


class BaseSingleFileCallback(Callback):
    """Base class for single file upload/download callbacks.

    This abstract base class provides common functionality for tracking individual
    file transfers within a batch operation. Subclasses implement operation-specific
    behavior via the template method pattern.

    The close() method uses the template method pattern, calling abstract methods
    that subclasses override to provide operation-specific behavior:
    - _get_phase(): Returns the TaskPhase for this operation
    - _get_file_display_path(): Returns the path to display for logging
    - _update_stats(): Updates the parent's stats for this operation
    - _build_status_details(): Builds the status_details dict for progress reporting
    """

    parent: BaseProgressCallback
    source_path: str
    dest_path: str
    _completed: bool

    def __init__(
        self,
        parent: BaseProgressCallback,
        source_path: str,
        dest_path: str,
        **kwargs: Any,
    ):
        """Initialize the single file callback.

        Args:
            parent: The parent progress callback.
            source_path: Path to the source file.
            dest_path: Destination path for the file.
            **kwargs: Additional arguments passed to the base Callback.

        """
        super().__init__(**kwargs)
        self.parent = parent
        self.source_path = source_path
        self.dest_path = dest_path
        self._completed = False

    @abstractmethod
    def _get_phase(self) -> str:
        """Return the TaskPhase for this operation."""
        ...

    @abstractmethod
    def _get_file_display_path(self) -> str:
        """Return the path to use for display/logging."""
        ...

    @abstractmethod
    def _update_stats(self) -> None:
        """Update the parent's stats for this operation (called within lock)."""
        ...

    @abstractmethod
    def _get_files_count(self) -> int:
        """Return the current files count from stats (called within lock)."""
        ...

    @abstractmethod
    def _build_status_details(self, files_count: int, total_bytes: int, current_file: str) -> dict[str, Any]:
        """Build the status_details dict for progress reporting.

        Args:
            files_count: Number of files transferred so far.
            total_bytes: Total bytes transferred so far.
            current_file: Name of the current file for display.

        Returns:
            Dictionary with status details for the progress report.

        """
        ...

    def close(self) -> None:
        """Called when the file transfer completes.

        Updates the parent's statistics and reports progress to the Jobs service.
        Thread-safe: uses parent's lock to protect stats updates.
        """
        if self._completed:
            return

        self._completed = True
        parent = self.parent

        # Extract the filename for logging/display
        current_file = self._get_file_display_path()

        # Thread-safe stats update
        with parent._lock:
            # Update stats (operation-specific)
            self._update_stats()

            # Capture current values while holding the lock
            files_count = self._get_files_count()
            total_bytes = parent.stats.total_bytes

        logger.debug(f"File transferred: {current_file} ({files_count}/{parent.total_files})")

        # Report progress to Jobs service (outside lock to avoid holding it during I/O)
        parent.progress_reporter.update_progress(
            status=PlatformJobStatus.ACTIVE,
            status_details=self._build_status_details(files_count, total_bytes, current_file),
        )

    def __enter__(self) -> "BaseSingleFileCallback":
        return self

    def __exit__(self, *exc_args: object) -> None:
        self.close()


class FileUploadProgressCallback(BaseProgressCallback):
    """Callback for tracking file upload progress and reporting to the Jobs service.

    This callback integrates with fsspec's callback mechanism to report progress
    after each file is uploaded. It uses the branched callback pattern where:
    - The parent callback tracks overall upload statistics
    - Child callbacks are created for each file via `branched()`
    - When a child callback closes, it signals file completion to the parent

    Usage:
        callback = FileUploadProgressCallback(
            progress_reporter=reporter,
            src_path=src_path,
            fileset_name="workspace/fileset",
            stats=upload_stats,
        )
        filesystem_sdk.put(src, dest, recursive=True, callback=callback)
    """

    stats: UploadStats

    def __init__(
        self,
        progress_reporter: ProgressReporter,
        src_path: Path,
        fileset_name: str,
        stats: UploadStats,
        **kwargs: Any,
    ):
        """Initialize the upload progress callback.

        Args:
            progress_reporter: The progress reporter for sending updates to Jobs service.
            src_path: The source path (file or directory) to upload.
            fileset_name: The name of the target fileset (workspace/name format).
            stats: Mutable UploadStats object to track progress.
            **kwargs: Additional arguments passed to the base Callback.

        """
        # List files to get stats before upload
        files = self.list_local_files(src_path)

        if not files:
            logger.warning(f"Source path {src_path} contains no files")

        total_files = len(files)
        total_size = sum(f.size for f in files)

        # Initialize base class with computed values
        super().__init__(
            progress_reporter=progress_reporter,
            fileset_name=fileset_name,
            total_files=total_files,
            total_size=total_size,
            stats=stats,
            **kwargs,
        )

        logger.info(f"Uploading {total_files} files ({total_size} bytes) to {self.fileset_name}")

        # Report initial progress
        progress_reporter.update_progress(
            status=PlatformJobStatus.ACTIVE,
            status_details={
                "phase": TaskPhase.UPLOADING,
                "fileset": self.fileset_name,
                "total_files": total_files,
                "total_size": total_size,
                "uploaded_files": 0,
                "uploaded_bytes": 0,
            },
        )

    def branched(self, source_path: str, dest_path: str, **kwargs: Any) -> "SingleFileUploadCallback":
        """Create a child callback for a single file upload.

        This method is called by fsspec when starting a file transfer within
        a recursive put operation. It returns a child callback that tracks
        the individual file's progress and reports completion to the parent.

        Args:
            source_path: Source file path.
            path_2: Destination file path.
            **kwargs: Additional keyword arguments.

        Returns:
            A SingleFileUploadCallback for tracking this file's upload.

        """
        return SingleFileUploadCallback(
            parent=self,
            source_path=source_path,
            dest_path=dest_path,
            **kwargs,
        )


class SingleFileUploadCallback(BaseSingleFileCallback):
    """Callback for tracking a single file upload within a batch operation.

    This child callback is created by FileUploadProgressCallback.branched()
    for each file being uploaded. When the upload completes and this callback
    is closed, it notifies the parent to update overall progress.
    """

    parent: FileUploadProgressCallback

    def _get_phase(self) -> str:
        """Return the TaskPhase for upload operations."""
        return TaskPhase.UPLOADING

    def _get_file_display_path(self) -> str:
        """Return the destination filename for display."""
        return self.dest_path.split("/")[-1] if "/" in self.dest_path else self.dest_path

    def _update_stats(self) -> None:
        """Update the parent's upload stats."""
        self.parent.stats.files_uploaded += 1
        if self.size is not None:
            self.parent.stats.total_bytes += self.size

    def _get_files_count(self) -> int:
        """Return the current uploaded files count."""
        return self.parent.stats.files_uploaded

    def _build_status_details(self, files_count: int, total_bytes: int, current_file: str) -> dict[str, Any]:
        """Build the status_details dict for upload progress reporting."""
        return {
            "phase": TaskPhase.UPLOADING,
            "fileset": self.parent.fileset_name,
            "total_files": self.parent.total_files,
            "total_size": self.parent.total_size,
            "uploaded_files": files_count,
            "uploaded_bytes": total_bytes,
            "current_file": current_file,
            "progress_pct": get_percentage(files_count, self.parent.total_files),
        }


class FileDownloadProgressCallback(BaseProgressCallback):
    """Callback for tracking file download progress and reporting to the Jobs service.

    Similar to FileUploadProgressCallback but for download operations.

    Usage:
        callback = FileDownloadProgressCallback(
            progress_reporter=reporter,
            fileset_name="workspace/fileset",
            total_files=10,
            total_size=1024000,
            stats=download_stats,
        )
        filesystem_sdk.get(src, dest, recursive=True, callback=callback)
    """

    stats: DownloadStats

    def __init__(
        self,
        progress_reporter: ProgressReporter,
        fileset_name: str,
        total_files: int,
        total_size: int,
        stats: DownloadStats,
        **kwargs: Any,
    ):
        """Initialize the download progress callback.

        Args:
            progress_reporter: The progress reporter for sending updates to Jobs service.
            fileset_name: The name of the source fileset (workspace/name format).
            total_files: Total number of files to download.
            total_size: Total size of all files in bytes.
            stats: Mutable DownloadStats object to track progress.
            **kwargs: Additional arguments passed to the base Callback.

        """
        super().__init__(
            progress_reporter=progress_reporter,
            fileset_name=fileset_name,
            total_files=total_files,
            total_size=total_size,
            stats=stats,
            **kwargs,
        )

        logger.info(f"Downloading {total_files} files ({total_size} bytes) from {self.fileset_name}")

        # Report initial progress
        progress_reporter.update_progress(
            status=PlatformJobStatus.ACTIVE,
            status_details={
                "phase": TaskPhase.DOWNLOADING,
                "fileset": self.fileset_name,
                "total_files": total_files,
                "total_size": total_size,
                "downloaded_files": 0,
                "downloaded_bytes": 0,
            },
        )

    def branched(self, source_path: str, dest_path: str, **kwargs: Any) -> "SingleFileDownloadCallback":
        """Create a child callback for a single file download.

        Args:
            source_path: Source file path in the fileset.
            dest_path: Destination local file path.
            **kwargs: Additional keyword arguments.

        Returns:
            A SingleFileDownloadCallback for tracking this file's download.

        """
        return SingleFileDownloadCallback(
            parent=self,
            source_path=source_path,
            dest_path=dest_path,
            **kwargs,
        )


class SingleFileDownloadCallback(BaseSingleFileCallback):
    """Callback for tracking a single file download within a batch operation.

    This child callback is created by FileDownloadProgressCallback.branched()
    for each file being downloaded. When the download completes and this callback
    is closed, it notifies the parent to update overall progress.
    """

    parent: FileDownloadProgressCallback

    def _get_phase(self) -> str:
        """Return the TaskPhase for download operations."""
        return TaskPhase.DOWNLOADING

    def _get_file_display_path(self) -> str:
        """Return the source filename for display."""
        return self.source_path.split("/")[-1] if "/" in self.source_path else self.source_path

    def _update_stats(self) -> None:
        """Update the parent's download stats."""
        self.parent.stats.files_downloaded += 1
        if self.size is not None:
            self.parent.stats.total_bytes += self.size

    def _get_files_count(self) -> int:
        """Return the current downloaded files count."""
        return self.parent.stats.files_downloaded

    def _build_status_details(self, files_count: int, total_bytes: int, current_file: str) -> dict[str, Any]:
        """Build the status_details dict for download progress reporting."""
        return {
            "phase": TaskPhase.DOWNLOADING,
            "fileset": self.parent.fileset_name,
            "total_files": self.parent.total_files,
            "total_size": self.parent.total_size,
            "downloaded_files": files_count,
            "downloaded_bytes": total_bytes,
            "current_file": current_file,
            "progress_pct": get_percentage(files_count, self.parent.total_files),
        }


class CompositeCallback(Callback):
    """A callback that delegates to multiple child callbacks.

    This allows combining multiple callbacks (e.g., TqdmCallback for console progress
    and FileUploadProgressCallback for Jobs service reporting) into a single callback
    that can be passed to fsspec operations.

    All callback methods are forwarded to each child callback in order.

    Usage:
        tqdm_cb = TqdmCallback(tqdm_kwargs={"desc": "Uploading"})
        progress_cb = FileUploadProgressCallback(...)
        composite = CompositeCallback(tqdm_cb, progress_cb)
        filesystem_sdk.put(src, dest, recursive=True, callback=composite)
    """

    def __init__(self, *callbacks: Callback, **kwargs: Any):
        """Initialize with multiple callbacks.

        Args:
            *callbacks: Variable number of Callback instances to delegate to.
            **kwargs: Additional arguments passed to the base Callback.

        """
        super().__init__(**kwargs)
        self.callbacks = list(callbacks)

    def set_size(self, size: int) -> None:
        """Set size on all child callbacks."""
        self.size = size
        for cb in self.callbacks:
            cb.set_size(size)

    def absolute_update(self, value: int) -> None:
        """Update absolute value on all child callbacks."""
        self.value = value
        for cb in self.callbacks:
            cb.absolute_update(value)

    def relative_update(self, inc: int = 1) -> None:
        """Update relative value on all child callbacks."""
        self.value += inc
        for cb in self.callbacks:
            cb.relative_update(inc)

    def branched(self, source_path: str, dest_path: str, **kwargs: Any) -> "CompositeCallback":
        """Create a composite child callback from all child callbacks' branched results.

        Each child callback's branched() method is called, and the results are
        wrapped in a new CompositeCallback.

        Args:
            source_path: Source path.
            dest_path: Destination path.
            **kwargs: Additional keyword arguments.

        Returns:
            A new CompositeCallback wrapping all child callbacks' branched results.

        """
        child_callbacks = [cb.branched(source_path, dest_path, **kwargs) for cb in self.callbacks]
        return CompositeCallback(*child_callbacks)

    def call(self, hook_name: str | None = None, **kwargs: Any) -> None:
        """Call hooks on all child callbacks."""
        for cb in self.callbacks:
            cb.call(hook_name, **kwargs)

    def close(self) -> None:
        """Close all child callbacks."""
        for cb in self.callbacks:
            cb.close()

    def __enter__(self) -> "CompositeCallback":
        for cb in self.callbacks:
            cb.__enter__()
        return self

    def __exit__(self, *exc_args: object) -> None:
        for cb in self.callbacks:
            cb.__exit__(*exc_args)
