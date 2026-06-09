# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fileset download job step utilities."""

from nemo_evaluator_sdk.values import DatasetRows
from nemo_platform_plugin.jobs.api_factory import (
    ContainerSpec,
    CPUExecutionProviderSpec,
    EnvironmentVariable,
    PlatformJobStep,
)
from nemo_platform_plugin.jobs.image import get_qualified_image
from nmp.common.jobs.constants import (
    DEFAULT_NEMO_JOB_STEP_CONFIG_FILE_PATH,
    EPHEMERAL_TASK_STORAGE_PATH_ENVVAR,
    PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
)
from nmp.evaluator.app.values import Dataset, Fileset, FilesetRef
from nmp.evaluator.config import settings


def fileset_entrypoint() -> list[str]:
    """Python task entrypoint for fileset download commands."""
    return ["python", "-m", "nmp.evaluator.tasks.download_fileset"]


def fileset_entrypoint_args(dataset: Dataset, target_download_dir: str, scratch_path: str) -> list[str]:
    """
    Entrypoint args to download fileset using the NeMo Platform SDK.

    Downloads to local scratch first then moves to shared storage to avoid
    issues with file locking on shared filesystems.

    Args:
        dataset: Dataset object (FilesetRef, DatasetRows, or Fileset).
        target_download_dir: Final destination directory on shared storage.
        scratch_path: Temporary local scratch directory (may contain env var references).

    Returns:
        CLI args list for the download_fileset task.
    """
    args = ["--local-dir", scratch_path, "--target-dir", target_download_dir]

    if isinstance(dataset, FilesetRef) or isinstance(dataset, Fileset):
        args.extend(["--dataset", dataset.model_dump_json()])
    elif isinstance(dataset, DatasetRows):
        args.extend(["--dataset-file", DEFAULT_NEMO_JOB_STEP_CONFIG_FILE_PATH])
    else:
        raise TypeError(f"Unexpected dataset type to configure entrypoint args {type(dataset)}")
    return args


def get_fileset_step(dataset: Dataset, step_name: str) -> PlatformJobStep:
    """
    Create a job step to download a fileset from NeMo Platform.

    Args:
        dataset: Dataset object (FilesetRef, DatasetRows, or Fileset).
        step_name: Unique name for the step.

    Returns:
        PlatformJobStep configured to download the fileset.
    """
    scratch_path = "${" + EPHEMERAL_TASK_STORAGE_PATH_ENVVAR + "}"
    target_download_dir = "${" + PERSISTENT_JOB_STORAGE_PATH_ENVVAR + "}/datasets"

    command = fileset_entrypoint_args(dataset, target_download_dir, scratch_path)

    job_step = PlatformJobStep(
        name=step_name,
        executor=CPUExecutionProviderSpec(
            provider="cpu",
            container=ContainerSpec(
                image=get_qualified_image("nmp-cpu-tasks"),
                entrypoint=fileset_entrypoint(),
                command=command,
            ),
        ),
        environment=[
            EnvironmentVariable(name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR, value=settings.jobs.volume_path),
        ],
    )
    if isinstance(dataset, DatasetRows):
        job_step["config"] = dataset.model_dump(mode="json", exclude_none=True)
    return job_step
