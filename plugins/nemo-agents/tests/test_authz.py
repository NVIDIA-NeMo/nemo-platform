# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Authorization derivation for the agents plugin.

Asserts that every mounted route carries a valid ``@path_rule`` whose permissions all
share the ``agents`` namespace (so ``_derive_service_contribution`` reports no problems
and derives the catalog from the routes), and spot-checks the shapes that matter: a CRUD
binding, the gateway proxy binding (PRINCIPAL + ``agents.gateway.invoke`` across the
wildcard path and every proxied method), and a job-factory binding.
"""

from __future__ import annotations

from nemo_agents_plugin.service import AgentsService
from nemo_platform_plugin.authz import AuthzContribution
from nemo_platform_plugin.authz_discovery import _derive_service_contribution

_BASE = "/apis/agents/v2/workspaces/{workspace}"
_GATEWAY_AGENT = f"{_BASE}/agents/{{name}}/-/{{trailing_uri:path}}"
# Every method the gateway forwards (see gateway._PROXY_METHODS), lower-cased
# for the wire format.
_PROXY_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


def _contribution() -> AuthzContribution:
    contrib, problems = _derive_service_contribution(AgentsService())
    # No problems is the load-bearing assertion: every route is ruled and every
    # referenced permission shares the inferred ``agents`` namespace.
    assert problems == [], problems
    return contrib


def test_agents_service_derivation_has_no_problems() -> None:
    contrib = _contribution()
    # All derived permissions live under the agents namespace.
    assert contrib.permissions
    assert all(perm_id.startswith("agents.") for perm_id in contrib.permissions)
    # Every derived permission carries a non-empty description.
    assert all(desc for desc in contrib.permissions.values())


def test_crud_binding_agent_create() -> None:
    contrib = _contribution()
    binding = contrib.endpoints[f"{_BASE}/agents"]["post"]
    assert binding.permissions == ["agents.agents.create"]
    assert binding.scopes == ["agents:write", "platform:write"]
    assert binding.callers == ["principal"]
    assert not binding.deny
    # The corresponding permission id is declared with a description.
    assert "agents.agents.create" in contrib.permissions


def test_crud_binding_deployment_read_covers_logs() -> None:
    contrib = _contribution()
    # The two log routes are read-only and share the deployments.read permission.
    for path in (f"{_BASE}/deployments/{{name}}/logs", f"{_BASE}/deployments/{{name}}/logs/stream"):
        binding = contrib.endpoints[path]["get"]
        assert binding.permissions == ["agents.deployments.read"]
        assert binding.scopes == ["agents:read", "platform:read"]
        assert binding.callers == ["principal"]


def test_gateway_proxy_binding() -> None:
    contrib = _contribution()
    methods = contrib.endpoints[_GATEWAY_AGENT]
    # The single @path_rule covers the wildcard ``{trailing_uri:path}`` route
    # across every proxied HTTP method.
    assert set(methods) == _PROXY_METHODS
    for method, binding in methods.items():
        assert binding.permissions == ["agents.gateway.invoke"], method
        assert binding.callers == ["principal"], method
        assert binding.scopes == ["agents:write", "platform:write"], method
        assert not binding.deny, method
    # The deployment-name proxy route is annotated identically.
    deployment_gw = f"{_BASE}/deployments/{{name}}/-/{{trailing_uri:path}}"
    assert set(contrib.endpoints[deployment_gw]) == _PROXY_METHODS
    assert contrib.endpoints[deployment_gw]["post"].permissions == ["agents.gateway.invoke"]
    # The coarse permission is declared.
    assert "agents.gateway.invoke" in contrib.permissions


def test_job_factory_binding() -> None:
    contrib = _contribution()
    # evaluate-suite maps to the ``agents.suite`` sub-namespace; its collection
    # POST is a create, item DELETE is a delete, both PRINCIPAL.
    collection = f"{_BASE}/jobs/evaluate-suite"
    create = contrib.endpoints[collection]["post"]
    assert create.permissions == ["agents.suite.create"]
    assert create.scopes == ["agents:write", "platform:write"]
    assert create.callers == ["principal"]

    delete = contrib.endpoints[f"{collection}/{{name}}"]["delete"]
    assert delete.permissions == ["agents.suite.delete"]

    # Every job-factory permission for all five collections is declared.
    expected_job_perms = {
        f"agents.{sub}.{verb}"
        for sub in ("evaluate", "suite", "optimize-skills", "analyze", "optimize")
        for verb in ("create", "list", "read", "delete", "cancel")
    }
    assert expected_job_perms <= set(contrib.permissions)
