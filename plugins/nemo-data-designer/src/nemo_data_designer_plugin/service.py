# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Data Designer plugin service implementation."""

from __future__ import annotations

from typing import ClassVar

from data_designer.engine.errors import DataDesignerRuntimeError
from data_designer.errors import DataDesignerError
from data_designer_nemo.errors import NDDInternalError, NDDInvalidConfigError
from fastapi import Request
from nemo_platform_plugin.service import NemoService, RouterSpec
from pydantic import ValidationError
from starlette import status
from starlette.responses import JSONResponse


class DataDesignerService(NemoService):
    """Data Designer service for NeMo Platform."""

    name: ClassVar[str] = "data-designer"
    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files", "inference-gateway"]

    def get_routers(self) -> list[RouterSpec]:
        from nemo_data_designer_plugin.functions.preview import PreviewFunction
        from nemo_data_designer_plugin.jobs.create import CreateJob
        from nemo_platform_plugin.authz import AuthzScope
        from nemo_platform_plugin.functions.routes import add_function_routes
        from nemo_platform_plugin.jobs.routes import add_job_routes

        scope = AuthzScope("data-designer")
        return [
            RouterSpec(
                add_function_routes(
                    PreviewFunction,
                    authz=scope,
                    permission_description="Preview a Data Designer config",
                ),
                prefix="/v2/workspaces/{workspace}",
                tag="Data Designer",
                description="Streaming preview of a Data Designer config.",
            ),
            RouterSpec(
                add_job_routes(CreateJob, authz=scope),
                prefix="/v2/workspaces/{workspace}",
                tag="Data Designer",
                description="Job endpoints",
            ),
        ]

    def get_exception_handlers(self) -> dict:
        async def validation_error_handler(_request: Request, ex: ValidationError):
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={"detail": str(ex)},
            )

        async def data_designer_error_handler(_request: Request, ex: DataDesignerError):
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={"detail": str(ex)},
            )

        async def data_designer_runtime_error_handler(_request: Request, ex: DataDesignerRuntimeError):
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": str(ex)},
            )

        async def ndd_internal_error_handler(_request: Request, ex: NDDInternalError):
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": str(ex)},
            )

        async def ndd_bad_request_error_handler(_request: Request, ex: NDDInvalidConfigError):
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={"detail": str(ex)},
            )

        return {
            ValidationError: validation_error_handler,
            DataDesignerError: data_designer_error_handler,
            DataDesignerRuntimeError: data_designer_runtime_error_handler,
            NDDInternalError: ndd_internal_error_handler,
            NDDInvalidConfigError: ndd_bad_request_error_handler,
        }
