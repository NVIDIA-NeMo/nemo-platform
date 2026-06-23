# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from fastapi import FastAPI
from nemo_automodel_plugin.contributor import AutomodelContributor


def _route_paths(app: FastAPI) -> set[str]:
    """Collect all route paths, compatible with FastAPI 0.138+ _IncludedRouter."""
    paths: set[str] = set()
    queue = list(app.routes)
    while queue:
        route = queue.pop()
        if hasattr(route, "path"):
            paths.add(route.path)
        fn = getattr(route, "effective_candidates", None)
        if callable(fn):
            queue.extend(fn())  # type: ignore[arg-type]
    return paths


def test_contributor_mounts_job_collection() -> None:
    contributor = AutomodelContributor()
    app = FastAPI()
    for spec in contributor.get_routers():
        app.include_router(spec.router, prefix=spec.prefix)

    paths = _route_paths(app)
    assert "/v2/workspaces/{workspace}/automodel/healthz" in paths
    assert "/v2/workspaces/{workspace}/automodel/jobs" in paths


def test_contributor_get_cli_exposes_flat_verbs() -> None:
    import typer

    cli = AutomodelContributor().get_cli()
    assert isinstance(cli, typer.Typer)
    assert cli.info.name == "automodel"
    assert not any(g.name == "jobs" for g in cli.registered_groups)
    assert {cmd.name for cmd in cli.registered_commands} >= {"run", "submit", "explain"}


def test_contributor_exposes_sdk_resources() -> None:
    from nemo_automodel_plugin.sdk.resources import AsyncAutomodelCustomization, AutomodelCustomization

    sdk = AutomodelContributor().get_sdk_resources()
    assert sdk is not None
    assert sdk.sync_resource is AutomodelCustomization
    assert sdk.async_resource is AsyncAutomodelCustomization
