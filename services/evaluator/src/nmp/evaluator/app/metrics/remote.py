# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compatibility wrappers for remote metric runtime implementations."""

from __future__ import annotations

from typing import Any

import httpx
import nemo_evaluator_sdk.metrics.remote as _sdk_remote
from nemo_evaluator_sdk import inference
from nemo_evaluator_sdk.resilience.api import run_with_resilience
from nemo_evaluator_sdk.values import MetricInput, MetricResult


def _sync_sdk_remote_bindings() -> None:
    """Mirror patchable service symbols into SDK module globals."""
    _sdk_remote.requests_log_var = inference.requests_log_var
    setattr(_sdk_remote, "httpx", httpx)
    _sdk_remote.run_with_resilience = run_with_resilience


async def _post_to_remote_endpoint(
    url: str,
    payload: dict[str, Any],
    api_key: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 0,
    log=_sdk_remote._logger,
) -> dict[str, Any]:
    _sync_sdk_remote_bindings()
    return await _sdk_remote._post_to_remote_endpoint(
        url=url,
        payload=payload,
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
        log=log,
    )


class RemoteMetric(_sdk_remote.RemoteMetric):
    async def compute_scores(self, input: MetricInput) -> MetricResult:
        _sync_sdk_remote_bindings()
        return await super().compute_scores(input)


class NemoAgentToolkitRemoteMetric(_sdk_remote.NemoAgentToolkitRemoteMetric):
    async def compute_scores(self, input: MetricInput) -> MetricResult:
        _sync_sdk_remote_bindings()
        return await super().compute_scores(input)


__all__ = ["NemoAgentToolkitRemoteMetric", "RemoteMetric", "_post_to_remote_endpoint", "httpx", "run_with_resilience"]
