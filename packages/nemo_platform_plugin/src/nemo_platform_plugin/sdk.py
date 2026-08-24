# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin SDK resource container."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient

SyncResourceT = TypeVar("SyncResourceT")
AsyncResourceT = TypeVar("AsyncResourceT")


@dataclass(frozen=True, slots=True)
class NemoPluginSDKResources(Generic[SyncResourceT, AsyncResourceT]):
    """Container for plugin SDK resources exposed on platform clients."""

    sync_resource: Callable[[NemoClient], SyncResourceT] | None = None
    async_resource: Callable[[AsyncNemoClient], AsyncResourceT] | None = None

    def __post_init__(self) -> None:
        if self.sync_resource is None and self.async_resource is None:
            raise ValueError("At least one of sync_resource or async_resource must be provided")


__all__ = [
    "AsyncNemoClient",
    "NemoClient",
    "NemoPluginSDKResources",
]
