# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contributor protocol for customization training backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, runtime_checkable

import typer
from nemo_platform_plugin.service import RouterSpec


class CustomizationContributorDiscoveryError(RuntimeError):
    """Raised when customization contributor discovery fails."""


@dataclass(frozen=True, slots=True)
class CustomizationContributorSDKResources:
    """Sync/async resource classes mounted under ``client.customization.<name>``."""

    sync_resource: type[Any] | None = None
    async_resource: type[Any] | None = None

    def __post_init__(self) -> None:
        if self.sync_resource is None and self.async_resource is None:
            raise ValueError("At least one of sync_resource or async_resource must be provided")


@runtime_checkable
class CustomizationContributor(Protocol):
    """One training backend mounted under ``/apis/customization``."""

    name: ClassVar[str]
    dependencies: ClassVar[list[str]]

    def get_routers(self) -> list[RouterSpec]:
        """HTTP routes for this backend (workspace-scoped prefix per backend)."""

    def get_cli(self) -> typer.Typer | None:
        """CLI subgroup mounted at ``nemo customization <name>``.

        HTTP authorization is **not** declared here: it is derived from the
        ``@path_rule``-decorated routes returned by :meth:`get_routers`, which the
        customization hub aggregates into its own ``nemo.services`` route surface.
        """

    def get_sdk_resources(self) -> CustomizationContributorSDKResources | None:
        """Return SDK resource classes for ``client.customization.<name>``.

        Return :class:`CustomizationContributorSDKResources` with sync and/or async
        resource classes (each accepts a :class:`~nemo_platform.NeMoPlatform` or
        :class:`~nemo_platform.AsyncNeMoPlatform` in ``__init__``). Return ``None``
        when the backend has no Python SDK surface. Do not register a separate
        ``nemo.sdk`` entry point — the customization hub composes contributors.
        """
        ...
