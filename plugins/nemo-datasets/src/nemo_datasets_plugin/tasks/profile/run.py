# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Dataset-profiler task.

Runs as a platform job -- inside the ``nmp-cpu-tasks`` container in a real deployment, or directly
in the platform virtualenv via the subprocess job backend for local development. It reads a
``{"workspace", "fileset"}`` step config, profiles that fileset, and publishes the resulting
``DatasetProfile`` both onto the fileset and as a job result artifact named ``profile``
(``profile.json``).

Not a ``nemo`` CLI subcommand: the profiler's inputs and output contract are both still moving, and a
published subcommand is a promise to keep them still.

The fileset is staged on local disk for the duration of the run. That is the whole of what
:func:`_fileset_source` does, and the one part a ranged-read source replaces later; the profiler core
stays blind to where its bytes come from, which is what the ``FileSource`` seam is for.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from nemo_datasets_plugin.profiler.file_source import FileSource, LocalFileSource
from nemo_datasets_plugin.profiler.pipeline import DEFAULT_ROW_BUDGET, profile
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import FilesClient
from nemo_platform_plugin.files.dataset_profile import DatasetProfile
from nemo_platform_plugin.files.metadata import DatasetMetadataContent, FilesetMetadata
from nemo_platform_plugin.files.types import UpdateFilesetRequest
from nemo_platform_plugin.job_results import PlatformJobResults
from nemo_platform_plugin.jobs.constants import (
    EPHEMERAL_TASK_STORAGE_PATH_ENVVAR,
    NEMO_JOB_FILESET_ENVVAR,
    NEMO_JOB_ID_ENVVAR,
    NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
    NEMO_JOB_WORKSPACE_ENVVAR,
)
from nemo_platform_plugin.jobs.file_manager import FilesetFileManager
from nemo_platform_plugin.sdk_provider import get_platform_sdk

logger = logging.getLogger(__name__)

# The service identity the task authenticates as. Any ``service:*`` principal gets the internal
# ``ServiceSystem`` role, so no registration is required; a dedicated name keeps audit logs and traces
# attributable.
_SERVICE_IDENTITY = "datasets"

# Result artifact published back to the job's fileset.
_PROFILE_RESULT_NAME = "profile"
_PROFILE_FILE_NAME = "profile.json"


def run(sdk: NeMoPlatform | None = None) -> int:
    """Entry point for the profiler task. Returns a process exit code."""
    _configure_logging()
    try:
        service_sdk = sdk or get_platform_sdk(as_service=_SERVICE_IDENTITY)
        config = _load_step_config()
        workspace = config.get("workspace") or _required_env(NEMO_JOB_WORKSPACE_ENVVAR)
        fileset = config.get("fileset") or _required_env(NEMO_JOB_FILESET_ENVVAR)
        with _fileset_source(service_sdk, workspace=workspace, fileset=fileset) as source:
            return _profile_and_publish(
                service_sdk,
                source=source,
                workspace=workspace,
                fileset=fileset,
                job_name=_required_env(NEMO_JOB_ID_ENVVAR),
                row_budget=_resolve_row_budget(config),
                column_roles=_resolve_column_roles(config),
            )
    except Exception:
        logger.exception("Dataset profiler task failed")
        return 1


@contextmanager
def _fileset_source(sdk: NeMoPlatform, *, workspace: str, fileset: str) -> Iterator[FileSource]:
    """The fileset's files, staged on local disk for the duration of the profile.

    Downloading the whole fileset is what this costs today. It is also the only part of the task
    that knows where the bytes live, so a ranged-read source over the Files API replaces it without
    the profiler core noticing.
    """
    manager = FilesetFileManager(
        workspace=workspace,
        fileset_name=fileset,
        sdk=sdk,
        ensure_fileset_exists=False,
    )
    logger.info("Downloading fileset %s/%s", workspace, fileset)
    downloaded = manager.download_from_url(manager.url())
    try:
        yield LocalFileSource(downloaded.path)
    finally:
        downloaded.cleanup_tmp_dir()


def _profile_and_publish(
    sdk: NeMoPlatform,
    *,
    source: FileSource,
    workspace: str,
    fileset: str,
    job_name: str,
    row_budget: int | None,
    column_roles: dict[str, str],
) -> int:
    # Uncapped by default, and especially right for this task: the whole fileset has already been
    # downloaded, so capping would pay the full transfer cost and still hand back partial statistics
    # and an incomplete profile. Having bought the bytes, read them.
    logger.info("Profiling with a row budget of %s per partition", row_budget if row_budget else "unbounded")
    dataset_profile = profile(source, row_budget=row_budget, column_roles=column_roles)

    # Persisted onto the fileset first, so the profile is discoverable via
    # GET .../filesets/{name}/profile, then published as a job artifact as well.
    _persist_profile_to_fileset(sdk, workspace=workspace, fileset=fileset, dataset_profile=dataset_profile)

    # Scoped to the job's ephemeral storage when the platform provided one, and cleaned up either
    # way: under the local subprocess backend this runs on a developer's machine, where an abandoned
    # mkdtemp accumulates one directory per profiling run.
    with tempfile.TemporaryDirectory(
        prefix="dataset-profile-",
        dir=os.environ.get(EPHEMERAL_TASK_STORAGE_PATH_ENVVAR) or None,
    ) as scratch:
        result_dir = Path(scratch) / _PROFILE_RESULT_NAME
        result_dir.mkdir(parents=True)
        (result_dir / _PROFILE_FILE_NAME).write_text(dataset_profile.model_dump_json(indent=2))

        results = PlatformJobResults(job_name=job_name, workspace=workspace, sdk=sdk)
        ref = results.save(_PROFILE_RESULT_NAME, result_dir)
    logger.info("Published dataset profile for %s/%s: %s", workspace, fileset, ref.artifact_url)
    return 0


def _persist_profile_to_fileset(
    sdk: NeMoPlatform,
    *,
    workspace: str,
    fileset: str,
    dataset_profile: DatasetProfile,
) -> None:
    """Write ``dataset_profile`` onto the fileset's dataset metadata, preserving other metadata."""
    files_client = client_from_platform(sdk, FilesClient)
    current = files_client.get_fileset(workspace=workspace, name=fileset).data()
    metadata = current.metadata or FilesetMetadata()
    dataset_meta = metadata.dataset or DatasetMetadataContent()
    dataset_meta = dataset_meta.model_copy(update={"profile": dataset_profile})
    metadata = metadata.model_copy(update={"dataset": dataset_meta})
    files_client.update_fileset(workspace=workspace, name=fileset, body=UpdateFilesetRequest(metadata=metadata))
    logger.info("Persisted profile to fileset %s/%s metadata", workspace, fileset)


def _resolve_row_budget(config: dict) -> int | None:
    """Rows the profiler may read per partition, from the step config.

    Defaults to reading everything: the profiler folds, so memory is flat in rows and a budget buys
    only a shorter run.

    ``0`` and ``null`` both ask for every row, and are kept so a caller that set them explicitly
    still means what it meant.
    """
    if "row_budget" not in config:
        return DEFAULT_ROW_BUDGET
    requested = config["row_budget"]
    if requested is None:
        return None
    # Validated here as well as at any API boundary that produced it: this reads a file off disk, so
    # nothing upstream is guaranteed to have checked it. `int()` alone was too forgiving -- it turned
    # 1.9 into 1, `true` into 1, and `false` into 0, which this function reads as "every row". A
    # budget that quietly means something other than what the config says is worse than a failed job.
    if not isinstance(requested, int) or isinstance(requested, bool):
        raise ValueError(f"row_budget must be an integer or null, got {requested!r}")
    if requested < 0:
        raise ValueError(f"row_budget must be >= 0, got {requested}")
    return requested or None


def _resolve_column_roles(config: dict) -> dict[str, str]:
    """Caller-declared column roles, for datasets whose column names the role table does not know.

    Not validated against the role vocabulary here. The profiler applies its own dtype gates and
    reports an unsupportable hint as evidence on the profile, which is a better place for the finding
    than a task that fails before producing anything.
    """
    roles = config.get("column_roles") or {}
    if not isinstance(roles, dict):
        raise ValueError(f"column_roles must map column name to role, got {type(roles).__name__}")
    return {str(name): str(role) for name, role in roles.items()}


def _load_step_config() -> dict:
    path = os.environ.get(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR)
    if not path:
        raise RuntimeError(f"{NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR} not set; running outside the platform?")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required job environment variable: {name}")
    return value


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
