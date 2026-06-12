# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Safe Synthesizer plugin service implementation."""

from __future__ import annotations

from typing import ClassVar

from fastapi import Request
from nemo_platform_plugin.authz import AuthzContribution, AuthzEndpointMethod
from nemo_platform_plugin.service import ExceptionHandler, NemoService, RouterSpec
from pydantic import ValidationError
from starlette import status
from starlette.responses import JSONResponse

_SERVICE_NAME = "safe-synthesizer"
_JOBS_PERMISSION_PREFIX = f"{_SERVICE_NAME}.jobs"
_READ_SCOPES = [f"{_SERVICE_NAME}:read", "platform:read"]
_WRITE_SCOPES = [f"{_SERVICE_NAME}:write", "platform:write"]


def _read_method(permission: str) -> AuthzEndpointMethod:
    return AuthzEndpointMethod(permissions=[permission], scopes=list(_READ_SCOPES))


def _write_method(permission: str) -> AuthzEndpointMethod:
    return AuthzEndpointMethod(permissions=[permission], scopes=list(_WRITE_SCOPES))


class SafeSynthesizerService(NemoService):
    """Safe Synthesizer service exposed as an NMP plugin."""

    name: ClassVar[str] = _SERVICE_NAME
    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files"]

    @classmethod
    def get_authz_contribution(cls) -> AuthzContribution:
        """Authorization policy matching the pre-plugin Safe Synthesizer service."""
        base = f"/apis/{cls.name}/v2/workspaces/{{workspace}}/jobs"
        create = f"{_JOBS_PERMISSION_PREFIX}.create"
        list_ = f"{_JOBS_PERMISSION_PREFIX}.list"
        read = f"{_JOBS_PERMISSION_PREFIX}.read"
        delete = f"{_JOBS_PERMISSION_PREFIX}.delete"
        cancel = f"{_JOBS_PERMISSION_PREFIX}.cancel"

        return AuthzContribution(
            permissions={
                cancel: "Cancel safe synthesizer jobs",
                create: "Create safe synthesizer jobs",
                delete: "Delete safe synthesizer jobs",
                list_: "List safe synthesizer jobs",
                read: "Read safe synthesizer jobs",
            },
            endpoints={
                base: {
                    "get": _read_method(list_),
                    "post": _write_method(create),
                },
                f"{base}/{{job}}/results/adapter/download": {
                    "get": _read_method(read),
                },
                f"{base}/{{job}}/results/evaluation-report/download": {
                    "get": _read_method(read),
                },
                f"{base}/{{job}}/results/summary/download": {
                    "get": _read_method(read),
                },
                f"{base}/{{job}}/results/synthetic-data/download": {
                    "get": _read_method(read),
                },
                f"{base}/{{job}}/results/{{name}}": {
                    "get": _read_method(read),
                },
                f"{base}/{{job}}/results/{{name}}/download": {
                    "get": _read_method(read),
                },
                f"{base}/{{name}}": {
                    "delete": _write_method(delete),
                    "get": _read_method(read),
                },
                f"{base}/{{name}}/cancel": {
                    "post": _write_method(cancel),
                },
                f"{base}/{{name}}/logs": {
                    "get": _read_method(read),
                },
                f"{base}/{{name}}/results": {
                    "get": _read_method(read),
                },
                f"{base}/{{name}}/status": {
                    "get": _read_method(read),
                },
            },
        )

    def get_routers(self) -> list[RouterSpec]:
        from nemo_safe_synthesizer_plugin.api.v2.jobs import endpoints as jobs

        return [
            RouterSpec(
                jobs.router,
                prefix="/v2/workspaces/{workspace}",
                tag="Safe Synthesizer",
                description="Job endpoints",
            )
        ]

    def get_exception_handlers(self) -> dict[type[Exception], ExceptionHandler]:
        async def validation_error_handler(_request: Request, ex: Exception):
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={"detail": str(ex)},
            )

        return {ValidationError: validation_error_handler}
