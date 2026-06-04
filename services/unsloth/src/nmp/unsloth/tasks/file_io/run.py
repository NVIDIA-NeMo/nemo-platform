# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""File I/O task entry point for the unsloth service."""

from nemo_platform import ConflictError

from nmp.customizer.shared.tasks.file_io.runner import FileIORunner, run_file_io_task
from nmp.unsloth.app.constants import SERVICE_NAME

SERVICE_SOURCE = SERVICE_NAME


def run(sdk=None, job_ctx=None) -> int:
    """Execute the unsloth file I/O task."""
    return run_file_io_task(
        service_name=SERVICE_NAME,
        service_source=SERVICE_SOURCE,
        sdk=sdk,
        job_ctx=job_ctx,
    )


def build_output_metadata(spec) -> dict:
    """Build the metadata dict stamped onto the output fileset."""
    return {
        "model": spec.model.name,
        "finetuning_type": spec.training.finetuning_type,
        "save_method": spec.output.save_method,
        "output_type": spec.output.type,
    }


__all__ = ["ConflictError", "FileIORunner", "SERVICE_SOURCE", "build_output_metadata", "run"]
