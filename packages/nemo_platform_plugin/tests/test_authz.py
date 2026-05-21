# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from nemo_platform_plugin.authz import AuthzContribution, authz_for_workspace_job_collection
from nemo_platform_plugin.authz_discovery import _collect_from_plugin_surface, discover_authz_contributions
from nemo_platform_plugin.service import NemoService


def test_authz_for_workspace_job_collection_paths() -> None:
    contrib = authz_for_workspace_job_collection(
        api_area="customization",
        collection_suffix="/automodel/jobs",
        permission_prefix="customization.automodel.jobs",
        include_healthz=True,
        healthz_suffix="/automodel/healthz",
    )
    assert "/apis/customization/v2/workspaces/{workspace}/automodel/jobs" in contrib.endpoints
    post = contrib.endpoints["/apis/customization/v2/workspaces/{workspace}/automodel/jobs"]["post"]
    assert post.permissions == ["customization.automodel.jobs.create"]
    assert "customization:write" in (post.scopes or [])
    assert "customization.automodel.jobs.create" in contrib.permissions


def test_service_class_get_authz_contribution_without_instance() -> None:
    """discover_services yields classes; get_authz_contribution must be a classmethod."""

    class _Svc(NemoService):
        name = "example-svc"
        dependencies = []

        @classmethod
        def get_authz_contribution(cls) -> AuthzContribution:
            return authz_for_workspace_job_collection(
                api_area="example-svc",
                collection_suffix="/jobs",
                permission_prefix="example-svc.jobs",
            )

        def get_routers(self):
            return []

    contribs = _collect_from_plugin_surface({"example-svc": _Svc}, surface="nemo.services")
    assert len(contribs) == 1
    assert "/apis/example-svc/v2/workspaces/{workspace}/jobs" in contribs[0].endpoints


def test_discover_includes_automodel_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """When nemo-automodel-plugin is installed, its contributor authz is discovered."""
    try:
        from nemo_automodel_plugin.contributor import AutomodelContributor
    except ImportError:
        pytest.skip("nemo-automodel-plugin not installed")

    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_customization_contributors",
        lambda: {"automodel": AutomodelContributor()},
    )
    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_services",
        lambda: {},
    )
    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_entry_points",
        lambda _group: {},
    )
    discover_authz_contributions.cache_clear()
    try:
        contributions = discover_authz_contributions()
    finally:
        discover_authz_contributions.cache_clear()

    assert len(contributions) >= 1
    paths = set()
    for contrib in contributions:
        paths.update(contrib.endpoints.keys())
    assert "/apis/customization/v2/workspaces/{workspace}/automodel/jobs" in paths
