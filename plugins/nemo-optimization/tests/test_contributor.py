# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nemo_optimization.contributor import OptimizationContributor
from nemo_platform_plugin.customization_contributor import CustomizationContributor


def test_contributor_matches_protocol() -> None:
    contributor = OptimizationContributor()
    assert isinstance(contributor, CustomizationContributor)
    assert contributor.name == "optimize"


def test_contributor_mounts_optimize_routes() -> None:
    specs = OptimizationContributor().get_routers()
    prefixes = {spec.prefix for spec in specs}
    assert "/v2/workspaces/{workspace}/optimize" in prefixes
    assert "/v2/workspaces/{workspace}" in prefixes

    paths = {
        f"{spec.prefix}{route.path}"
        for spec in specs
        for route in spec.router.routes
    }
    assert any(p.endswith("/optimize/healthz") for p in paths)
    assert any("/optimize/jobs" in p for p in paths)


def test_contributor_cli_named_optimize() -> None:
    app = OptimizationContributor().get_cli()
    assert app.info.name == "optimize"


def test_contributor_discoverable_via_entrypoint() -> None:
    from nemo_platform_plugin.discovery import discover_customization_contributors

    discover_customization_contributors.cache_clear()
    contributors = discover_customization_contributors()
    assert "optimize" in contributors
