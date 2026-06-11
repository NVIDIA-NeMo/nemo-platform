# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from nemo_platform_plugin.authz import (
    AuthzContribution,
    AuthzEndpointMethod,
    authz_for_workspace_job_collection,
    combine_authz_contributions,
)
from nemo_platform_plugin.authz_discovery import (
    AUTHZ_GROUP,
    _collect_from_plugin_surface,
    discover_authz_contributions,
)
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.scheduler import NemoJobScheduler
from nemo_platform_plugin.service import NemoService


def _example_automodel_authz() -> AuthzContribution:
    """Example policy for a customization job collection (see authz module docstring)."""
    return authz_for_workspace_job_collection(
        api_area="customization",
        collection_suffix="/automodel/jobs",
        permission_prefix="customization.automodel.jobs",
        include_healthz=True,
        healthz_suffix="/automodel/healthz",
    )


class _ExampleSubmitJob(NemoJob):
    name = "example-submit"
    description = "Job used to verify authenticated remote submit."

    def run(self, config: dict) -> dict:
        return config


_ExampleSubmitJob.__module__ = "example_plugin.jobs.example_submit"


def test_authz_for_workspace_job_collection_paths() -> None:
    contrib = _example_automodel_authz()
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


def test_combine_authz_contributions_merges_endpoints_and_permissions() -> None:
    a = authz_for_workspace_job_collection(
        api_area="customization",
        collection_suffix="/automodel/jobs",
        permission_prefix="customization.automodel.jobs",
    )
    b = authz_for_workspace_job_collection(
        api_area="customization",
        collection_suffix="/unsloth/jobs",
        permission_prefix="customization.unsloth.jobs",
    )
    merged = combine_authz_contributions(a, b)
    assert "customization.automodel.jobs.create" in merged.permissions
    assert "customization.unsloth.jobs.create" in merged.permissions
    assert "/apis/customization/v2/workspaces/{workspace}/automodel/jobs" in merged.endpoints
    assert "/apis/customization/v2/workspaces/{workspace}/unsloth/jobs" in merged.endpoints


def test_customization_router_authz_discovered_via_nemo_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """Customization hub aggregates backend authz through nemo.services discovery."""

    class _FakeContributor:
        def get_authz_contribution(self) -> AuthzContribution:
            return _example_automodel_authz()

    class _CustomizationHub(NemoService):
        name = "customization"
        dependencies = []

        @classmethod
        def get_authz_contribution(cls) -> AuthzContribution:
            from nemo_platform_plugin.discovery import discover_customization_contributors

            hub = AuthzContribution(
                endpoints={
                    "/apis/customization/healthz": {
                        "get": AuthzEndpointMethod(permissions=[], scopes=[]),
                    },
                },
            )
            backend_parts = [
                contributor.get_authz_contribution() for contributor in discover_customization_contributors().values()
            ]
            return combine_authz_contributions(hub, *backend_parts)

        def get_routers(self):
            return []

    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_entry_points",
        lambda group: {},
    )
    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_services",
        lambda: {"customization": _CustomizationHub},
    )
    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_customization_contributors",
        lambda: {"automodel": _FakeContributor()},
    )
    discover_authz_contributions.cache_clear()
    try:
        contributions = discover_authz_contributions()
    finally:
        discover_authz_contributions.cache_clear()

    assert len(contributions) == 1
    paths = set(contributions[0].endpoints.keys())
    assert "/apis/customization/healthz" in paths
    assert "/apis/customization/v2/workspaces/{workspace}/automodel/jobs" in paths
    assert "/apis/customization/v2/workspaces/{workspace}/automodel/healthz" in paths


def test_nemo_authz_entry_point_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plugins can register authz via a nemo.authz entry point callable."""
    ep = MagicMock()
    ep.load.return_value = _example_automodel_authz

    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_entry_points",
        lambda group: {"automodel": ep} if group == AUTHZ_GROUP else {},
    )
    monkeypatch.setattr(
        "nemo_platform_plugin.discovery.discover_services",
        lambda: {},
    )
    discover_authz_contributions.cache_clear()
    try:
        contributions = discover_authz_contributions()
    finally:
        discover_authz_contributions.cache_clear()

    assert len(contributions) == 1
    paths = set(contributions[0].endpoints.keys())
    assert "/apis/customization/v2/workspaces/{workspace}/automodel/jobs" in paths
    assert "/apis/customization/v2/workspaces/{workspace}/automodel/healthz" in paths


def test_submit_remote_forwards_authorization_header() -> None:
    """Authenticated CLI submit passes Authorization to the protected job route."""
    capture: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capture["headers"] = dict(request.headers)
        return httpx.Response(200, json={"id": "job-123", "status": "queued"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    scheduler = NemoJobScheduler()

    result = scheduler.submit_remote(
        _ExampleSubmitJob,
        {"foo": "bar"},
        base_url="https://nmp.test",
        workspace="ws-a",
        headers={"Authorization": "Bearer test-token"},
        http_client=client,
    )

    assert result == {"id": "job-123", "status": "queued"}
    headers = capture["headers"]
    assert isinstance(headers, dict)
    assert headers.get("authorization") == "Bearer test-token"
