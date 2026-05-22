# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Local metric preparation helpers for evaluator SDK runtime."""

from __future__ import annotations

import copy
import os
from collections.abc import Sequence
from typing import cast

from nemo_evaluator_sdk.execution._protocols import JobParamsConfigurableMetric
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricWithPreflight, MetricWithSecrets
from nemo_evaluator_sdk.metrics.utils import metric_type_name
from nemo_evaluator_sdk.values.params import RunConfig
from pydantic import BaseModel


def unique_metric_keys(metrics: Sequence[Metric]) -> list[str]:
    """Assign stable unique keys to a sequence of metrics.

    Args:
        metrics: Metrics submitted in one evaluator call.

    Returns:
        Unique metric keys in the same order as the input metrics.
    """

    seen: dict[str, int] = {}
    keys: list[str] = []
    for metric in metrics:
        base = metric_type_name(metric)
        seen[base] = seen.get(base, 0) + 1
        suffix = seen[base]
        keys.append(base if suffix == 1 else f"{base}_{suffix}")
    return keys


def _copy_metric(metric: Metric) -> Metric:
    """Create a best-effort isolated copy of a metric instance.

    Preparation mutates metrics in-place (run-config overrides, secret
    resolution, preflight) so we copy first to avoid side-effects on the
    caller's original instance. Pydantic models are copied via
    ``model_copy(deep=True)``; regular Python metric classes are also
    supported when ``copy.deepcopy()`` works, for example by implementing
    ``__deepcopy__``.
    """
    if isinstance(metric, BaseModel):
        return cast(Metric, metric.model_copy(deep=True))

    try:
        return copy.deepcopy(metric)
    except Exception as exc:
        raise TypeError(
            f"Cannot copy metric {type(metric).__name__}; use a Pydantic model or ensure the metric "
            "supports copy.deepcopy() (for example, by implementing __deepcopy__)."
        ) from exc


def _candidate_env_names(secret_name: str) -> list[str]:
    """Generate environment variable names that may contain one secret."""
    names = [secret_name, secret_name.upper()]
    normalized = secret_name.replace("-", "_").replace("/", "_")
    names.extend([normalized, normalized.upper()])
    if normalized and normalized[0].isdigit():
        prefixed = f"_{normalized}"
        names.extend([prefixed, prefixed.upper()])
    return list(dict.fromkeys(names))


async def _resolve_secret_from_env(secret_name: str) -> str | None:
    """Resolve one secret value from environment variables.

    Async to satisfy the ``SecretResolver`` protocol expected by metrics.
    """
    for candidate in _candidate_env_names(secret_name):
        value = os.getenv(candidate)
        if value:
            return value
    return None


def _apply_runtime_params(metric: Metric, params: RunConfig) -> None:
    """Apply runtime execution params to one prepared metric.

    Args:
        metric: Copied metric instance to mutate for this run only.
        params: Materialized execution params for this run.

    Returns:
        None.
    """
    if isinstance(metric, JobParamsConfigurableMetric):
        metric.apply_evaluation_job_params(params)


async def prepare_metric_for_local_execution(metric: Metric, params: RunConfig) -> Metric:
    """Prepare one metric for execution.

    Args:
        metric: User-provided metric instance.
        params: Materialized execution params for this run.

    Returns:
        A metric object ready for execution in the selected backend.
    """
    prepared = _copy_metric(metric)
    _apply_runtime_params(prepared, params)

    if isinstance(prepared, MetricWithSecrets):
        await prepared.resolve_secrets(_resolve_secret_from_env)
    if isinstance(prepared, MetricWithPreflight):
        await prepared.preflight()
    return prepared
