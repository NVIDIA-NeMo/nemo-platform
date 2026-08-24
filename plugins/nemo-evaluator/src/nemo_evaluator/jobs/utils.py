# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for evaluator plugin jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_platform_plugin.client.client import AsyncNemoClient, DefaultAsyncHttpxClient

T = TypeVar("T")


def run_with_isolated_async_sdk(
    async_sdk: AsyncNemoClient,
    fn: Callable[[AsyncNemoClient], Awaitable[T]],
) -> T:
    """Run ``fn(cloned_sdk)`` via ``run_sync`` without binding ``async_sdk``'s httpx client.

    Clones ``async_sdk`` onto a throwaway httpx client for the duration of ``fn`` so the injected
    client's transport is not bound to this temporary event loop (and later ``run_sync`` calls can
    still reuse ``async_sdk``).
    """

    async def _run() -> T:
        async with DefaultAsyncHttpxClient() as http_client:
            return await fn(async_sdk.copy(http_client=http_client))

    return run_sync(_run)
