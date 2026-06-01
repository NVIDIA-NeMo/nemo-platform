# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for evaluator plugin job compilation and local execution."""

from __future__ import annotations

from typing import Any

from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.job_context import JobContext
from nmp.evaluator.app.datasets.nmp_datasets.fileset import download_dataset, download_dataset_sync
from nmp.evaluator.app.values import FilesetRef


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
