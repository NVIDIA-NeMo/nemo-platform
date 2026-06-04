# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contributor protocol for customization training backends."""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

import typer
from nemo_platform_plugin.authz import AuthzContribution
from nemo_platform_plugin.service import RouterSpec


@runtime_checkable
class CustomizationContributor(Protocol):
    """One training backend mounted under ``/apis/customization``."""

    name: ClassVar[str]
    dependencies: ClassVar[list[str]]

    def get_routers(self) -> list[RouterSpec]:
        """HTTP routes for this backend (workspace-scoped prefix per backend)."""

    def get_cli(self) -> typer.Typer | None:
        """CLI subgroup mounted at ``nemo customization <name>``."""

    def get_authz_contribution(self) -> AuthzContribution | None:
        """Optional authorization policy (endpoints + permissions) for this contributor.

        Implement to return :class:`~nemo_platform_plugin.authz.AuthzContribution`, or
        register a ``nemo.authz`` entry point instead.
        """
        ...
