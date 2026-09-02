# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for evaluator plugin jobs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
from nemo_evaluator_sdk.execution.metric_execution import run_sync
from nemo_platform_plugin import AsyncNemoClient

T = TypeVar("T")
AsyncClientT = TypeVar("AsyncClientT", bound=AsyncNemoClient)


def run_with_isolated_async_client(
    async_client: AsyncClientT,
    fn: Callable[[AsyncClientT], Awaitable[T]],
) -> T:
    """Run ``fn(cloned_client)`` via ``run_sync`` without binding ``async_client``'s httpx client.

    Clones ``async_client`` onto a throwaway httpx client for the duration of ``fn`` so the injected
    client's transport is not bound to this temporary event loop (and later ``run_sync`` calls can
    still reuse ``async_client``).
    """

    async def _run() -> T:
        async with httpx.AsyncClient() as http_client:
            return await fn(async_client.with_http_client(http_client))

    return run_sync(_run)
