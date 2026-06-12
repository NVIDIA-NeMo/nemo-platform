# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Safe Synthesizer plugin service implementation."""

from __future__ import annotations

from typing import ClassVar

from fastapi import Request
from nemo_platform_plugin.authz import (
    AuthzContribution,
    AuthzEndpointMethod,
    authz_for_workspace_job_collection,
    combine_authz_contributions,
)
from nemo_platform_plugin.service import ExceptionHandler, NemoService, RouterSpec
from pydantic import ValidationError
from starlette import status
from starlette.responses import JSONResponse

_SERVICE_NAME = "safe-synthesizer"
_JOBS_PERMISSION_PREFIX = f"{_SERVICE_NAME}.jobs"
_READ_SCOPES = [f"{_SERVICE_NAME}:read", "platform:read"]
_RESULT_DOWNLOAD_ALIASES = ("adapter", "evaluation-report", "summary", "synthetic-data")


def _read_method(permission: str) -> AuthzEndpointMethod:
    return AuthzEndpointMethod(permissions=[permission], scopes=list(_READ_SCOPES))


class SafeSynthesizerService(NemoService):
    """Safe Synthesizer service exposed as an NMP plugin."""

    name: ClassVar[str] = _SERVICE_NAME
    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files"]

    @classmethod
    def get_authz_contribution(cls) -> AuthzContribution:
        """Authorization policy matching the pre-plugin Safe Synthesizer service."""
        base = f"/apis/{cls.name}/v2/workspaces/{{workspace}}/jobs"
        read = f"{_JOBS_PERMISSION_PREFIX}.read"

        return combine_authz_contributions(
            authz_for_workspace_job_collection(
                api_area=cls.name,
                collection_suffix="/jobs",
                permission_prefix=_JOBS_PERMISSION_PREFIX,
            ),
            AuthzContribution(
                endpoints={
                    f"{base}/{{job}}/results/{name}/download": {
                        "get": _read_method(read),
                    }
                    for name in _RESULT_DOWNLOAD_ALIASES
                },
            ),
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
