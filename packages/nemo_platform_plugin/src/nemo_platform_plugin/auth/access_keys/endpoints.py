# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from abc import abstractmethod

from nemo_platform_plugin.auth.access_keys.types import (
    AccessKeyCreateRequest,
    AccessKeyCreateResponse,
    AccessKeyListResponse,
)
from nemo_platform_plugin.client.endpoint import delete, get, post


@post("/apis/auth/v2/access-keys")
@abstractmethod
def create_access_key(*, body: AccessKeyCreateRequest) -> AccessKeyCreateResponse: ...


@get("/apis/auth/v2/access-keys")
@abstractmethod
def list_access_keys() -> AccessKeyListResponse: ...


@delete("/apis/auth/v2/access-keys/{jti}")
@abstractmethod
def revoke_access_key(*, jti: str) -> None: ...
