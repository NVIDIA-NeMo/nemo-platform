# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for evaluator plugin job compilation and local execution."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from nemo_evaluator.sdk.values.filesets import FilesetRef
from nemo_evaluator_sdk.datasets.loader import is_glob_pattern
from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_evaluator_sdk.metrics.types import MetricsUnion
from nemo_evaluator_sdk.values import DatasetRows
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform.filesets import FilesetFileSystem, build_fileset_ref, parse_fileset_ref
from nemo_platform_plugin.job_context import JobContext


def _fileset_ref_parts(dataset: FilesetRef) -> tuple[str, str, str]:
    """Return workspace, fileset name, and optional file selector."""
    return parse_fileset_ref(dataset.root, workspace_fallback=None)


def _base_download_path(destination: str, workspace: str, fileset: str) -> Path:
    return Path(destination) / workspace / fileset


async def dataset_exists(sdk: AsyncNeMoPlatform, dataset: FilesetRef) -> bool:
    """Return whether a persisted fileset reference resolves through the Files API."""
    fs = FilesetFileSystem(sdk=sdk)
    workspace, fileset, path = _fileset_ref_parts(dataset)
    base_path = build_fileset_ref("", workspace=workspace, fileset=fileset)
    try:
        if not path:
            return await fs._exists(base_path)
        if is_glob_pattern(path):
            files_resource = cast(Any, sdk.files)
            response = await files_resource.list(remote_path=path, fileset=fileset, workspace=workspace)
            return bool(response.data)
        return await fs._exists(build_fileset_ref(path, workspace=workspace, fileset=fileset))
    except FileNotFoundError:
        return False


async def download_dataset(
    *,
    sdk: AsyncNeMoPlatform,
    dataset: FilesetRef,
    destination: str,
) -> Path:
    """Download a persisted fileset reference to local storage."""
    workspace, fileset, path = _fileset_ref_parts(dataset)
    base_dest = _base_download_path(destination, workspace, fileset)
    base_dest.mkdir(parents=True, exist_ok=True)
    files_resource = cast(Any, sdk.files)

    if not path:
        await files_resource.download(
            remote_path="",
            fileset=fileset,
            workspace=workspace,
            local_path=str(base_dest),
            max_workers=None,
        )
        return base_dest

    if is_glob_pattern(path):
        await files_resource.download(
            remote_path=path,
            fileset=fileset,
            workspace=workspace,
            local_path=str(base_dest),
            max_workers=None,
        )
        return base_dest

    local_path = base_dest / path
    await files_resource.download(
        remote_path=path,
        fileset=fileset,
        workspace=workspace,
        local_path=str(local_path),
        max_workers=None,
    )
    return local_path


def download_dataset_sync(
    *,
    sdk: NeMoPlatform,
    dataset: FilesetRef,
    destination: str,
) -> Path:
    """Sync bridge for fileset reference downloads."""
    workspace, fileset, path = _fileset_ref_parts(dataset)
    base_dest = _base_download_path(destination, workspace, fileset)
    base_dest.mkdir(parents=True, exist_ok=True)
    files_resource = cast(Any, sdk.files)

    if not path:
        files_resource.download(
            remote_path="",
            fileset=fileset,
            workspace=workspace,
            local_path=str(base_dest),
            max_workers=None,
        )
        return base_dest

    if is_glob_pattern(path):
        files_resource.download(
            remote_path=path,
            fileset=fileset,
            workspace=workspace,
            local_path=str(base_dest),
            max_workers=None,
        )
        return base_dest

    local_path = base_dest / path
    files_resource.download(
        remote_path=path,
        fileset=fileset,
        workspace=workspace,
        local_path=str(local_path),
        max_workers=None,
    )
    return local_path


def remote_compile_metric(metric: MetricsUnion | Sequence[MetricsUnion]) -> MetricsUnion:
    """Return the single metric supported by evaluator plugin job compilation."""
    if isinstance(metric, Sequence):
        raise NotImplementedError("Remote benchmark compilation is not implemented for inline evaluator plugin specs.")
    return cast(MetricsUnion, metric)


async def resolve_submit_dataset(
    async_sdk: AsyncNeMoPlatform,
    dataset: list[dict[str, object]] | FilesetRef,
) -> tuple[DatasetRows | FilesetRef, FilesetRef | None]:
    """Resolve an evaluator plugin dataset for remote metric-job submission.

    FilesetRef datasets are validated via the async SDK and passed through;
    inline rows are wrapped as ``DatasetRows``.
    """
    if isinstance(dataset, FilesetRef):
        if not await dataset_exists(async_sdk, dataset):
            raise ValueError(f"FilesetRef dataset does not exist: {dataset.root}")
        return dataset, dataset
    return DatasetRows(rows=dataset), None


def resolve_run_dataset(
    dataset: list[dict[str, object]] | FilesetRef,
    *,
    ctx: JobContext,
    sdk: NeMoPlatform | None = None,
    async_sdk: AsyncNeMoPlatform | None = None,
) -> Any:
    """Resolve an evaluator plugin dataset for local SDK execution.

    Inline datasets pass through unchanged. ``FilesetRef`` datasets are downloaded
    via the async SDK when available, or the sync SDK otherwise.
    """
    if not isinstance(dataset, FilesetRef):
        return dataset

    destination = str(ctx.storage.persistent / "dataset")
    if async_sdk is not None:
        return run_sync(
            lambda: download_dataset(
                sdk=async_sdk,
                dataset=dataset,
                destination=destination,
            )
        )
    if sdk is not None:
        return download_dataset_sync(
            sdk=sdk,
            dataset=dataset,
            destination=destination,
        )
    raise ValueError("FilesetRef datasets require an SDK client for local evaluator job execution.")
