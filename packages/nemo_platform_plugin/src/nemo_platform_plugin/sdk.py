# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin SDK resource container."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from nemo_platform import AsyncNeMoPlatform, NeMoPlatform

SyncResourceT = TypeVar("SyncResourceT")
AsyncResourceT = TypeVar("AsyncResourceT")


@dataclass(frozen=True, slots=True)
class NemoPluginSDKResources(Generic[SyncResourceT, AsyncResourceT]):
    """Container for plugin SDK resources exposed on platform clients.

    Each factory is called with the client that owns the namespace: the legacy
    ``NeMoPlatform`` / ``AsyncNeMoPlatform`` SDK, or ``NemoClient`` /
    ``AsyncNemoClient`` when the caller uses the typed client. Both expose the
    ``_client`` and ``default_headers`` surface plugin resources rely on, so
    the factory parameter is deliberately left open.
    """

    sync_resource: Callable[[Any], SyncResourceT] | None = None
    async_resource: Callable[[Any], AsyncResourceT] | None = None

    def __post_init__(self) -> None:
        if self.sync_resource is None and self.async_resource is None:
            raise ValueError("At least one of sync_resource or async_resource must be provided")


__all__ = [
    "AsyncNeMoPlatform",
    "NeMoPlatform",
    "NemoPluginSDKResources",
]
