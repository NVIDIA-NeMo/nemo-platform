# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Customization router service — merges contributor HTTP routes."""

from __future__ import annotations

from typing import ClassVar

from fastapi import APIRouter
from nemo_platform_plugin.discovery import (
    CUSTOMIZATION_CONTRIBUTORS_GROUP,
    discover_customization_contributors,
)
from nemo_platform_plugin.service import NemoService, RouterSpec


class CustomizationRouterError(RuntimeError):
    """Raised when the customization router cannot start."""


_ROUTER_BASE_DEPENDENCIES = ("entities", "auth", "jobs", "secrets", "files", "models")


def merge_router_dependencies(contributors: dict[str, object]) -> list[str]:
    """Union platform router deps with each contributor's ``dependencies``."""
    deps = set(_ROUTER_BASE_DEPENDENCIES)
    for contributor in contributors.values():
        contrib_deps = getattr(type(contributor), "dependencies", None) or []
        deps.update(contrib_deps)
    return sorted(deps)


def _assert_no_prefix_collisions(contributors: dict[str, object]) -> None:
    prefixes: dict[str, str] = {}
    for key, contributor in contributors.items():
        for spec in contributor.get_routers():  # type: ignore[union-attr]
            prefix = spec.prefix.strip("/")
            if prefix in prefixes:
                raise CustomizationRouterError(
                    f"Route prefix collision: contributors {prefixes[prefix]!r} and {key!r} "
                    f"both use prefix {spec.prefix!r}",
                )
            prefixes[prefix] = key


class CustomizationRouterService(NemoService):
    """Sole ``nemo.services`` owner for ``/apis/customization``."""

    name: ClassVar[str] = "customization"
    dependencies: ClassVar[list[str]] = list(_ROUTER_BASE_DEPENDENCIES)

    def __init__(self) -> None:
        self._contributors = discover_customization_contributors()
        if not self._contributors:
            raise CustomizationRouterError(
                "Customization router is enabled but no contributors were discovered. "
                "Install a backend plugin (e.g. nemo-automodel) and ensure "
                f"'{CUSTOMIZATION_CONTRIBUTORS_GROUP}' entry points are registered.",
            )
        _assert_no_prefix_collisions(self._contributors)
        type(self).dependencies = merge_router_dependencies(self._contributors)

    def get_routers(self) -> list[RouterSpec]:
        router = APIRouter()

        @router.get("/healthz")
        async def healthz() -> dict[str, object]:
            return {
                "plugin": self.name,
                "status": "ok",
                "contributors": sorted(self._contributors.keys()),
            }

        specs: list[RouterSpec] = [
            RouterSpec(
                router=router,
                tag="Customization",
                description="Customization router health.",
                prefix="",
            ),
        ]

        for key in sorted(self._contributors.keys()):
            contributor = self._contributors[key]
            contributor_specs = contributor.get_routers()
            for spec in contributor_specs:
                specs.append(
                    RouterSpec(
                        router=spec.router,
                        tag=spec.tag or f"Customization {key}",
                        description=spec.description,
                        prefix=spec.prefix,
                    ),
                )
        return specs
