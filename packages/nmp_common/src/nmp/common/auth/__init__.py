# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Authentication and authorization utilities for NeMo Platform."""

from nmp.common.config import AuthConfig

from .client import AuthClient, AuthorizationResult
from .dependencies import (
    auth_as_service,
    auth_client_context,
    build_service_principal_bearer_token,
    build_service_principal_headers,
    get_auth_client,
    get_principal_auth_headers,
)
from .exceptions import AuthorizationError, InvalidPermissionFormatError, InvalidScopeFormatError
from .middleware import AuthorizationMiddleware
from .models import (
    NMP_ORIGIN_WORKSPACE_ENVVAR,
    NMP_ORIGIN_WORKSPACE_HEADER,
    NMP_PRINCIPAL_ENVVAR,
    AuthContext,
    Principal,
)
from .permissions import ALL_WORKSPACES, compute_accessible_workspaces
from .tasks import principal_from_env

# Testing utilities are NOT exported here to avoid importing dev dependencies (respx)
# at runtime. Import directly from nmp.common.auth.testing when needed in tests.

__all__ = [
    "ALL_WORKSPACES",
    "AuthClient",
    "AuthContext",
    "AuthConfig",
    "AuthorizationError",
    "InvalidPermissionFormatError",
    "InvalidScopeFormatError",
    "AuthorizationMiddleware",
    "AuthorizationResult",
    "NMP_ORIGIN_WORKSPACE_ENVVAR",
    "NMP_ORIGIN_WORKSPACE_HEADER",
    "NMP_PRINCIPAL_ENVVAR",
    "Principal",
    "auth_as_service",
    "auth_client_context",
    "build_service_principal_bearer_token",
    "build_service_principal_headers",
    "principal_from_env",
    "compute_accessible_workspaces",
    "get_auth_client",
    "get_principal_auth_headers",
]
