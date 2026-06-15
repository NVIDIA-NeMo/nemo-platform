# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from fastapi.routing import APIRoute
from nemo_deployments_plugin.service import DeploymentsService


def _mounted_paths() -> set[str]:
    service = DeploymentsService()
    paths: set[str] = set()
    for spec in service.get_routers():
        for route in spec.router.routes:
            if isinstance(route, APIRoute):
                paths.add(f"/apis/deployments{spec.prefix}{route.path}")
    return paths


def test_service_mounts_core_routes() -> None:
    paths = _mounted_paths()
    assert "/apis/deployments/v2/workspaces/{workspace}/deployment-configs" in paths
    assert "/apis/deployments/v2/workspaces/{workspace}/deployments" in paths
    assert "/apis/deployments/v2/workspaces/{workspace}/volumes" in paths
    assert "/apis/deployments/v2/workspaces/{workspace}/deployments/{name}/status" in paths
    assert "/apis/deployments/v2/workspaces/{workspace}/volumes/{name}/status" in paths


def test_service_name_matches_entry_point() -> None:
    assert DeploymentsService.name == "deployments"


def test_service_authz_covers_mounted_routes() -> None:
    contribution = DeploymentsService.get_authz_contribution()
    endpoint_paths = set(contribution.endpoints.keys())
    for path in _mounted_paths():
        assert path in endpoint_paths, f"missing authz entry for {path}"
        route_methods = {
            method.lower()
            for spec in DeploymentsService().get_routers()
            for route in spec.router.routes
            if isinstance(route, APIRoute) and f"/apis/deployments{spec.prefix}{route.path}" == path
            for method in route.methods or set()
        }
        for method in route_methods:
            assert method in contribution.endpoints[path], f"missing authz method {method} for {path}"
