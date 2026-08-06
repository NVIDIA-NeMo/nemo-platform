# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Literal

from nemo_platform_plugin.auth.access_keys.types import AccessKeyCreateRequest as AccessKeyCreateRequest
from nemo_platform_plugin.auth.access_keys.types import AccessKeyCreateResponse as AccessKeyCreateResponse
from nemo_platform_plugin.auth.access_keys.types import AccessKeyListResponse as AccessKeyListResponse
from nemo_platform_plugin.auth.access_keys.types import (
    AccessKeyNotImplementedErrorResponse as AccessKeyNotImplementedErrorResponse,
)
from nemo_platform_plugin.auth.access_keys.types import AccessKeyRevokeResponse as AccessKeyRevokeResponse
from pydantic import BaseModel, Field


class AccessKeyErrorResponse(BaseModel):
    """Scoped Access Key error response."""

    detail: str
    code: Literal["access_keys_disabled"] | None = Field(
        default=None,
        json_schema_extra={"nullable": True},
        description="Set to access_keys_disabled when the Scoped Access Key feature is disabled.",
    )
