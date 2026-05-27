# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Authorization policy contributions for NeMo Platform plugins.

Plugins declare API routes and permissions so the auth service can authorize
requests without hand-editing ``static-authz.yaml`` for every new surface.

Contributions are merged at runtime when the OPA bundle is built, and can be
materialized into ``static-authz.yaml`` via ``auth-tools sync-plugins``.

Example (customization job collection)::

    from nemo_platform_plugin.authz import AuthzContribution, authz_for_workspace_job_collection

    class AutomodelContributor:
        ...
        def get_authz_contribution(self) -> AuthzContribution:
            return authz_for_workspace_job_collection(
                api_area="customization",
                collection_suffix="/automodel/jobs",
                permission_prefix="customization.automodel.jobs",
                include_healthz=True,
                healthz_suffix="/automodel/healthz",
            )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AuthzEndpointMethod:
    """One HTTP method binding for an API route."""

    permissions: list[str]
    scopes: list[str] | None = None


@dataclass
class AuthzContribution:
    """Authorization data contributed by a plugin."""

    permissions: dict[str, str] = field(default_factory=dict)
    """Flat registry entries: ``permission_id`` → human-readable description."""

    endpoints: dict[str, dict[str, AuthzEndpointMethod]] = field(default_factory=dict)
    """Full API paths (``/apis/...``) → lower-case HTTP method → spec."""

    role_permissions: dict[str, list[str]] = field(default_factory=dict)
    """Optional explicit role → permission grants (merged with defaults)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for :func:`nmp.common.auth.authz_merge.merge_authz_contributions`."""
        return {
            "permissions": dict(self.permissions),
            "endpoints": {
                path: {
                    method: {
                        "permissions": spec.permissions,
                        **({"scopes": spec.scopes} if spec.scopes is not None else {}),
                    }
                    for method, spec in methods.items()
                }
                for path, methods in self.endpoints.items()
            },
            "role_permissions": {role: list(perms) for role, perms in self.role_permissions.items()},
        }


def _scopes_for(api_area: str, write: bool) -> list[str]:
    verb = "write" if write else "read"
    return [f"{api_area}:{verb}", f"platform:{verb}"]


def _job_collection_permissions(permission_prefix: str) -> dict[str, str]:
    return {
        f"{permission_prefix}.create": f"Create {permission_prefix} jobs",
        f"{permission_prefix}.list": f"List {permission_prefix} jobs",
        f"{permission_prefix}.read": f"Read {permission_prefix} jobs",
        f"{permission_prefix}.delete": f"Delete {permission_prefix} jobs",
    }


def authz_for_workspace_job_collection(
    api_area: str,
    collection_suffix: str,
    permission_prefix: str,
    include_healthz: bool = False,
    healthz_suffix: str | None = None,
) -> AuthzContribution:
    """Build authz for standard CORE job routes under ``/apis/<area>/v2/workspaces/{workspace}...``.

    Args:
        api_area: URL segment after ``/apis/`` (e.g. ``customization``, ``safe-synthesizer``).
        collection_suffix: Path after workspace (e.g. ``/automodel/jobs`` or ``/jobs``).
        permission_prefix: Dot-separated permission namespace (e.g. ``customization.automodel.jobs``).
        include_healthz: When true, register GET healthz with empty permissions (authenticated only).
        healthz_suffix: Defaults to ``{first segment of collection_suffix}/healthz`` when omitted.
    """
    if not collection_suffix.startswith("/"):
        raise ValueError("collection_suffix must start with '/'")
    base = f"/apis/{api_area}/v2/workspaces/{{workspace}}{collection_suffix}"
    perms = _job_collection_permissions(permission_prefix)
    prefix = permission_prefix
    endpoints: dict[str, dict[str, AuthzEndpointMethod]] = {
        base: {
            "post": AuthzEndpointMethod(
                permissions=[f"{prefix}.create"],
                scopes=_scopes_for(api_area, write=True),
            ),
            "get": AuthzEndpointMethod(
                permissions=[f"{prefix}.list"],
                scopes=_scopes_for(api_area, write=False),
            ),
        },
        f"{base}/{{name}}": {
            "get": AuthzEndpointMethod(
                permissions=[f"{prefix}.read"],
                scopes=_scopes_for(api_area, write=False),
            ),
            "delete": AuthzEndpointMethod(
                permissions=[f"{prefix}.delete"],
                scopes=_scopes_for(api_area, write=True),
            ),
        },
    }
    if include_healthz:
        if healthz_suffix is None:
            first = collection_suffix.strip("/").split("/")[0]
            healthz_suffix = f"/{first}/healthz"
        if not healthz_suffix.startswith("/"):
            healthz_suffix = f"/{healthz_suffix}"
        health_path = f"/apis/{api_area}/v2/workspaces/{{workspace}}{healthz_suffix}"
        endpoints[health_path] = {
            "get": AuthzEndpointMethod(permissions=[], scopes=[]),
        }

    return AuthzContribution(permissions=perms, endpoints=endpoints)
