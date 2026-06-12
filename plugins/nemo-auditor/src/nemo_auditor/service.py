# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Service surface for the auditor plugin."""

from __future__ import annotations

from typing import ClassVar

from fastapi import APIRouter
from nemo_platform_plugin.authz import AuthzContribution, AuthzEndpointMethod
from nemo_platform_plugin.service import NemoService, RouterSpec

_READ_SCOPES = ["auditor:read", "platform:read"]
_WRITE_SCOPES = ["auditor:write", "platform:write"]


class AuditorPluginService(NemoService):
    """Auditor plugin service. Exposes healthz and CRUD over audit configs/targets."""

    name: ClassVar[str] = "auditor"
    dependencies: ClassVar[list[str]] = ["entities"]

    @classmethod
    def get_authz_contribution(cls) -> AuthzContribution:
        base = f"/apis/{cls.name}/v2/workspaces/{{workspace}}"
        endpoints: dict[str, dict[str, AuthzEndpointMethod]] = {
            f"/apis/{cls.name}/v1/healthz": {
                "get": AuthzEndpointMethod(permissions=[], scopes=[]),
            },
        }
        permissions: dict[str, str] = {}
        for resource in ("configs", "targets"):
            permissions.update(
                {
                    f"{cls.name}.{resource}.create": f"Create auditor {resource}",
                    f"{cls.name}.{resource}.list": f"List auditor {resource}",
                    f"{cls.name}.{resource}.read": f"Read auditor {resource}",
                    f"{cls.name}.{resource}.update": f"Update auditor {resource}",
                    f"{cls.name}.{resource}.delete": f"Delete auditor {resource}",
                }
            )
            endpoints[f"{base}/{resource}"] = {
                "post": AuthzEndpointMethod(
                    permissions=[f"{cls.name}.{resource}.create"],
                    scopes=_WRITE_SCOPES,
                ),
                "get": AuthzEndpointMethod(
                    permissions=[f"{cls.name}.{resource}.list"],
                    scopes=_READ_SCOPES,
                ),
            }
            endpoints[f"{base}/{resource}/{{name}}"] = {
                "get": AuthzEndpointMethod(
                    permissions=[f"{cls.name}.{resource}.read"],
                    scopes=_READ_SCOPES,
                ),
                "put": AuthzEndpointMethod(
                    permissions=[f"{cls.name}.{resource}.update"],
                    scopes=_WRITE_SCOPES,
                ),
                "delete": AuthzEndpointMethod(
                    permissions=[f"{cls.name}.{resource}.delete"],
                    scopes=_WRITE_SCOPES,
                ),
            }

        return AuthzContribution(permissions=permissions, endpoints=endpoints)

    def get_routers(self) -> list[RouterSpec]:
        from nemo_auditor.api.v2 import configs, targets

        healthz_router = APIRouter()

        @healthz_router.get("/healthz")
        async def healthz() -> dict[str, object]:
            return {
                "plugin": self.name,
                "status": "ok",
                "mode": "sdk-backed-job-scaffold",
                "jobs": ["auditor.audit"],
                "entities": ["auditor_audit_config", "auditor_audit_target"],
            }

        crud_prefix = "/v2/workspaces/{workspace}"
        return [
            RouterSpec(
                router=healthz_router,
                tag="Auditor Plugin",
                description="Auditor plugin scaffold routes.",
                prefix="/v1",
            ),
            RouterSpec(
                router=configs.router,
                tag="Auditor Configs",
                description="Audit configuration CRUD.",
                prefix=crud_prefix,
            ),
            RouterSpec(
                router=targets.router,
                tag="Auditor Targets",
                description="Audit target CRUD.",
                prefix=crud_prefix,
            ),
        ]
