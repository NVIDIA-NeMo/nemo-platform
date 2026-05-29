# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for evaluator plugin job compilation and local execution."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from nemo_evaluator.jobs.filesets import dataset_exists, download_dataset, download_dataset_sync
from nemo_evaluator.sdk.types import FilesetRef
from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_evaluator_sdk.metrics.types import MetricsUnion
from nemo_evaluator_sdk.values import DatasetRows
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.job_context import JobContext


def remote_compile_metric(metric: MetricsUnion | Sequence[MetricsUnion]) -> MetricsUnion:
    """Return the single metric supported by remote service metric-job compilation."""
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
