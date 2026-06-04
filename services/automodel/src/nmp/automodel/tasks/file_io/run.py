# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""File I/O task entry point for the automodel service."""

from nemo_platform import ConflictError

from nmp.automodel.app.constants import SERVICE_NAME
from nmp.customizer.shared.tasks.file_io.runner import FileIORunner, run_file_io_task

SERVICE_SOURCE = "automodel"


def run(sdk=None, job_ctx=None) -> int:
    """Execute the automodel file I/O task."""
    return run_file_io_task(
        service_name=SERVICE_NAME,
        service_source=SERVICE_SOURCE,
        sdk=sdk,
        job_ctx=job_ctx,
    )


__all__ = ["ConflictError", "FileIORunner", "SERVICE_SOURCE", "run"]
