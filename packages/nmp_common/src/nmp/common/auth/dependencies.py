# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI dependencies and utilities for authentication."""

import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Generator, Optional

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException, Request
from nmp.common.config import get_auth_config

if TYPE_CHECKING:
    from .client import AuthClient

from .models import NMP_ORIGIN_WORKSPACE_HEADER, Principal

_SERVICE_BEARER_TOKEN_PREFIX = "nmp-service-v2."
_SERVICE_BEARER_TOKEN_AUDIENCE = "nmp-files-hf"
_SERVICE_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62})$")

# Context variable to store the current auth client (set by middleware or tasks runtime)
auth_client_context: ContextVar[Optional["AuthClient"]] = ContextVar("auth_client_context", default=None)


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


def get_principal_auth_headers() -> Dict[str, str]:
    """Get principal authentication headers from the current auth context.

    This is a utility function for services that need to forward principal
    authentication headers when making HTTP calls to other NeMo Platform services.
    It retrieves the current auth client from the context variable and
    extracts the principal headers for identity propagation.

    Returns:
        Dictionary of principal authentication headers to forward, or empty dict
        if no auth context. Headers include:

        - X-NMP-Principal-Id: The principal's unique identifier
        - X-NMP-Principal-Email: The principal's email (if available)
        - X-NMP-Principal-Groups: Comma-separated list of groups (if available)
        - X-NMP-Principal-On-Behalf-Of: On-behalf-of principal (if available)
        - X-NMP-Principal-On-Behalf-Of-Groups: On-behalf-of principal groups (if available)
        - X-NMP-Principal-On-Behalf-Of-Email: On-behalf-of principal email (if available)

    Example:
        ```python
        import httpx
        from nmp.common.auth import get_principal_auth_headers

        async def fetch_from_entities_service(resource_id: str):
            headers = get_principal_auth_headers()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{entities_url}/v2/models/{resource_id}",
                    headers=headers
                )
                return response.json()
        ```
    """
    auth_client = auth_client_context.get()
    if auth_client and auth_client.principal:
        headers = auth_client.principal.get_headers()
        if auth_client.outbound_origin_workspace:
            headers[NMP_ORIGIN_WORKSPACE_HEADER] = auth_client.outbound_origin_workspace
        return headers
    return {}


def build_service_principal_headers(service_name: str) -> Dict[str, str]:
    """Build NeMo Platform auth headers for outbound service-to-service calls.

    Returns:
    - `X-NMP-Principal-Id: service:<service_name>` so the downstream service
      can authorize the call.
    - When the current auth context is a non-service principal, also forwards
      `X-NMP-Principal-On-Behalf-Of`, `-Email`, and `-Groups` from
      ``Principal.effective_principal`` so downstream PDP checks evaluate the
      acting user (not the elevated service row alone).

    Args:
        service_name: The calling service's name (ex. "guardrails").

    Returns:
        Header dictionary ready to merge into an outbound request.
    """
    headers: Dict[str, str] = {"X-NMP-Principal-Id": f"service:{service_name}"}

    auth_client = auth_client_context.get()
    if auth_client is None or not auth_client.principal or not auth_client.principal.id:
        return headers

    if auth_client.outbound_origin_workspace:
        headers[NMP_ORIGIN_WORKSPACE_HEADER] = auth_client.outbound_origin_workspace

    effective = auth_client.principal.effective_principal
    if effective.id.startswith("service:"):
        return headers

    headers["X-NMP-Principal-On-Behalf-Of"] = effective.id
    if effective.email:
        headers["X-NMP-Principal-On-Behalf-Of-Email"] = effective.email
    if effective.groups:
        headers["X-NMP-Principal-On-Behalf-Of-Groups"] = ",".join(effective.groups)
    return headers


def build_service_principal_bearer_token(
    service_name: str,
    *,
    on_behalf_of: Principal,
    origin_workspace: str,
    source_workspace: str,
) -> str:
    """Sign delegated service context for clients limited to a Bearer token.

    The Hugging Face client used by model pullers cannot send the platform's
    ``X-NMP-*`` headers. Its token therefore carries signed service/delegate
    context, scoped to the Files HF API and one source workspace.
    """
    if not _SERVICE_NAME_RE.fullmatch(service_name):
        raise ValueError(f"Invalid service name: {service_name!r}")
    if not origin_workspace:
        raise ValueError("origin_workspace is required for delegated service bearer tokens")
    if not source_workspace:
        raise ValueError("source_workspace is required for delegated service bearer tokens")

    effective = on_behalf_of.effective_principal
    payload: dict[str, Any] = {
        "aud": _SERVICE_BEARER_TOKEN_AUDIENCE,
        "iat": int(time.time()),
        "iss": _service_bearer_token_issuer(),
        "sub": effective.id,
        "service": service_name,
        "principal_id": effective.id,
        "origin_workspace": origin_workspace,
        "source_workspace": source_workspace,
    }
    if effective.email:
        payload["principal_email"] = effective.email
    # Group claims are intentionally not persisted into durable runtime
    # credentials. Replaying a creation-time group snapshot would retain access
    # after the user is removed from that identity-provider group.
    private_key, key_id = _service_bearer_signing_key()
    encoded = jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": key_id},
    )
    token = f"{_SERVICE_BEARER_TOKEN_PREFIX}{encoded}"
    if len(token) > 16_384:
        raise ValueError("Delegated service bearer token exceeds the maximum supported size")
    return token


def _service_bearer_token_issuer() -> str:
    config = get_auth_config()
    return config.oidc.workload_token_issuer or "nmp-internal-service"


def _service_bearer_signing_key() -> tuple[bytes, str]:
    config = get_auth_config()
    key_file = config.oidc.workload_token_private_key_file
    if not key_file:
        raise ValueError("auth.oidc.workload_token_private_key_file is required for Files runtime tokens")
    try:
        key_path = Path(key_file)
        stat = key_path.stat()
        private_key_pem, _ = _load_service_bearer_key(key_file, stat.st_mtime_ns, stat.st_size)
        return private_key_pem, config.oidc.workload_token_key_id
    except OSError as exc:
        raise ValueError(f"Could not read Files runtime token signing key: {key_file}") from exc


@lru_cache(maxsize=4)
def _load_service_bearer_key(
    key_file: str,
    _mtime_ns: int,
    _size: int,
) -> tuple[bytes, rsa.RSAPublicKey]:
    private_key_pem = Path(key_file).read_bytes()
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError("Files runtime token signing key must be an RSA private key")
    return private_key_pem, private_key.public_key()


def _service_bearer_verification_key() -> tuple[rsa.RSAPublicKey, str]:
    config = get_auth_config()
    key_file = config.oidc.workload_token_private_key_file
    if not key_file:
        raise ValueError("auth.oidc.workload_token_private_key_file is required for Files runtime tokens")
    try:
        key_path = Path(key_file)
        stat = key_path.stat()
        _, public_key = _load_service_bearer_key(key_file, stat.st_mtime_ns, stat.st_size)
        return public_key, config.oidc.workload_token_key_id
    except OSError as exc:
        raise ValueError(f"Could not read Files runtime token signing key: {key_file}") from exc


def parse_service_principal_bearer_token(
    token: str,
    *,
    expected_source_workspace: str,
) -> Dict[str, str] | None:
    """Validate an internal Files runtime token into normalized principal headers."""
    if token.startswith("service:") and not get_auth_config().enabled:
        return {"x-nmp-principal-id": token}
    if not token.startswith(_SERVICE_BEARER_TOKEN_PREFIX):
        return None

    encoded = token.removeprefix(_SERVICE_BEARER_TOKEN_PREFIX)
    if not encoded or len(encoded) > 16_384:
        return None
    try:
        signing_key, key_id = _service_bearer_verification_key()
        header = jwt.get_unverified_header(encoded)
        if header.get("kid") != key_id:
            return None
        payload = jwt.decode(
            encoded,
            signing_key,
            algorithms=["RS256"],
            audience=_SERVICE_BEARER_TOKEN_AUDIENCE,
            issuer=_service_bearer_token_issuer(),
            options={"require": ["aud", "iat", "iss", "sub"]},
        )
    except (ValueError, TypeError, jwt.PyJWTError):
        return None

    service_name = payload.get("service")
    principal_id = payload.get("principal_id")
    origin_workspace = payload.get("origin_workspace")
    source_workspace = payload.get("source_workspace")
    principal_email = payload.get("principal_email")
    if (
        not isinstance(service_name, str)
        or not _SERVICE_NAME_RE.fullmatch(service_name)
        or not isinstance(principal_id, str)
        or not principal_id
        or payload.get("sub") != principal_id
        or not isinstance(origin_workspace, str)
        or not origin_workspace
        or source_workspace != expected_source_workspace
        or (principal_email is not None and not isinstance(principal_email, str))
    ):
        return None

    headers = {
        "x-nmp-principal-id": f"service:{service_name}",
        "x-nmp-principal-on-behalf-of": principal_id,
        "x-nmp-origin-workspace": origin_workspace,
    }
    if principal_email:
        headers["x-nmp-principal-on-behalf-of-email"] = principal_email
    return headers


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
