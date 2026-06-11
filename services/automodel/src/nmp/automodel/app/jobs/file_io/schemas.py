# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Schemas for the automodel file_io task configuration.

Re-exports the shared :mod:`nmp.customization_common.schemas.file_io` so existing
``nmp.automodel.app.jobs.file_io.schemas`` import paths keep working.
"""

from nmp.customization_common.schemas.file_io import (
    FILESET_PROTOCOL,
    DownloadItem,
    DownloadStats,
    FileDownloadError,
    FileIOTaskConfig,
    FileSetRef,
    FileStats,
    FileUploadError,
    PathTraversalError,
    ProgressReportError,
    TaskCompilationError,
    TaskPhase,
    TaskStatus,
    UploadItem,
    UploadStats,
)

__all__ = [
    "FILESET_PROTOCOL",
    "DownloadItem",
    "DownloadStats",
    "FileDownloadError",
    "FileIOTaskConfig",
    "FileSetRef",
    "FileStats",
    "FileUploadError",
    "PathTraversalError",
    "ProgressReportError",
    "TaskCompilationError",
    "TaskPhase",
    "TaskStatus",
    "UploadItem",
    "UploadStats",
]
