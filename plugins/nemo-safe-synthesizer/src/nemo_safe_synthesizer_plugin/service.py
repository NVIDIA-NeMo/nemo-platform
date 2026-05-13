# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Safe Synthesizer plugin service implementation."""

from __future__ import annotations

from typing import ClassVar

from fastapi import Request
from nemo_platform_plugin.service import ExceptionHandler, NemoService, RouterSpec
from pydantic import ValidationError
from starlette import status
from starlette.responses import JSONResponse


class SafeSynthesizerService(NemoService):
    """Safe Synthesizer service exposed as an NMP plugin."""

    name: ClassVar[str] = "safe-synthesizer"
    dependencies: ClassVar[list[str]] = ["entities", "auth", "jobs", "secrets", "files"]

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
