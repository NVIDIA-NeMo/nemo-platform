# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""File I/O task entry point for the customizer service."""

from nemo_platform import ConflictError

from nmp.customizer.app.constants import SERVICE_NAME
from nmp.customizer.shared.tasks.file_io.runner import (
    CREATE_FILESET_TIMEOUT,
    DOWNLOAD_TIMEOUT,
    INITIAL_BACKOFF_SECONDS,
    LIST_FILES_TIMEOUT,
    MAX_BACKOFF_SECONDS,
    MAX_RETRIES,
    TRANSIENT_FILESYSTEM_EXCEPTIONS,
    UPLOAD_TIMEOUT,
    FileIORunner,
    run_file_io_task,
)

SERVICE_SOURCE = SERVICE_NAME


def run(sdk=None, job_ctx=None) -> int:
    """Execute the customizer file I/O task."""
    return run_file_io_task(
        service_name=SERVICE_NAME,
        service_source=SERVICE_SOURCE,
        sdk=sdk,
        job_ctx=job_ctx,
    )


__all__ = [
    "CREATE_FILESET_TIMEOUT",
    "ConflictError",
    "DOWNLOAD_TIMEOUT",
    "FileIORunner",
    "INITIAL_BACKOFF_SECONDS",
    "LIST_FILES_TIMEOUT",
    "MAX_BACKOFF_SECONDS",
    "MAX_RETRIES",
    "SERVICE_SOURCE",
    "TRANSIENT_FILESYSTEM_EXCEPTIONS",
    "UPLOAD_TIMEOUT",
    "run",
]
