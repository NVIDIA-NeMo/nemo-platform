# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI dependencies and utilities for authentication."""

from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator, Optional

from fastapi import HTTPException, Request

# The ContextVar + plugin-safe header helpers live in nemo_platform_plugin.auth
# so plugins can read auth-propagation state without pulling nmp.common's heavy
# server-side deps. Server-side middleware sets the same ContextVar via this
# re-export, so identity is preserved across the import paths.
from nemo_platform_plugin.auth.dependencies import (
    auth_client_context as auth_client_context,
)
from nemo_platform_plugin.auth.dependencies import (
    build_service_principal_headers as build_service_principal_headers,
)
from nemo_platform_plugin.auth.dependencies import (
    get_principal_auth_headers as get_principal_auth_headers,
)

if TYPE_CHECKING:
    from .client import AuthClient


def get_auth_client(request: Request) -> "AuthClient":
    """Get the authorization client for the current request.

    This is the primary FastAPI dependency for all auth-related needs.
    It provides:

    - auth_client.principal: The authenticated principal (id, email, groups)
    - auth_client.authorize_request(method, path): Check if request is allowed
    - auth_client.has_permissions(workspace, perms): Check if principal has permissions
    - auth_client.wait_permissions(workspace, perms): Poll until permissions granted
    - auth_client.wait_role(principal, workspace, role): Poll until role granted/revoked

    Args:
        request: The FastAPI request object (unused, kept for FastAPI Depends signature)

    Returns:
        The AuthClient object with principal and authorization methods

    Raises:
        HTTPException: If no auth context is found (middleware not configured)

    Example:
        ```python
        @router.get("/v2/workspaces/{workspace}/models")
        async def list_models(
            workspace: str,
            auth_client: AuthClient = Depends(get_auth_client)
        ):
            # Access principal
            principal_id = auth_client.principal.id

            # Check permissions
            if await auth_client.has_permissions(workspace, ["models.read"]):
                ...
        ```
    """
    auth_client = auth_client_context.get()
    if auth_client is None:
        raise HTTPException(
            status_code=500,
            detail="No auth context found. Authorization middleware may not be configured.",
        )
    return auth_client


@contextmanager
def auth_as_service(service: Optional[str] = None) -> Generator[None, None, None]:
    """Context manager to run code with service principal credentials.

    Creates a new AuthClient with service principal credentials and sets it
    in the context variable. This isolates the elevated credentials to the
    current async context without affecting concurrent code.

    The service principal (e.g., "service:auth") has elevated permissions in the
    OPA policy, allowing internal service-to-service calls.

    This can be used both within request handlers (where auth context exists)
    and in background tasks/startup code (where it creates a fresh context).

    Note:
        Currently all service principals are treated equally with full permissions.
        In the future, service principals may be restricted based on scope - e.g.,
        "service:evaluator" would not have access to data designer resources.

    Args:
        service: Service name for the principal (e.g., "evaluator").
                 Defaults to the current client's configured service name, or
                 "unknown" if no context exists and no service is specified.

    Example:
        ```python
        from nmp.common.auth import auth_as_service

        async def refresh_policy_data(entities_client):
            with auth_as_service():
                # Uses default service name from config
                data = await entities_client.list(RoleBindingEntity, ...)

        async def cross_service_call():
            with auth_as_service(service="evaluator"):
                # Uses "service:evaluator" as principal
                data = await other_client.fetch(...)
        ```
    """
    from nmp.common.config import get_auth_config

    from .client import AuthClient
    from .models import Principal

    # Get current auth client if it exists
    current_client = auth_client_context.get()

    # Determine service name and config
    if current_client is not None:
        auth_config = current_client.config
    else:
        # No existing context - create fresh config from global settings
        auth_config = get_auth_config()

    # Use provided service name, or default to "unknown"
    service_name = service if service is not None else "unknown"

    # Create new AuthClient with service principal
    service_principal = Principal(
        id=f"service:{service_name}",
        email=None,
        groups=[],
    )
    service_client = AuthClient(principal=service_principal, config=auth_config)

    # Set new client in context (isolated to this async context)
    token = auth_client_context.set(service_client)
    try:
        yield
    finally:
        auth_client_context.reset(token)
