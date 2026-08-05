# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from nmp.common.auth.bearer import MalformedBearerTokenError, parse_bearer_authorization_header
from nmp.common.auth.jwt import TokenClaims
from nmp.common.auth.token_resolver import ResolvedBearerToken, ResolvedTokenKind, resolve_bearer_token
from nmp.common.config import AuthConfig, get_auth_config
from nmp.core.auth.api.v2.workload_token_exchange import (
    WorkloadTokenExchangeService,
    _allowed_audiences,
    _workload_token_issuer,
    get_workload_token_exchange_service,
)
from nmp.core.auth.app.access_keys import AccessKeyRegistry, get_access_key_registry
from pydantic import BaseModel, Field

router = APIRouter(tags=["Authentication"])
logger = logging.getLogger(__name__)


class AuthenticateErrorResponse(BaseModel):
    """Bearer token authentication error response."""

    detail: str


class AuthenticateResponse(BaseModel):
    """Successful bearer token authentication response for auth callouts."""

    principal: str
    email: str | None = Field(default=None, json_schema_extra={"nullable": True})
    groups: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    jti: str | None = Field(default=None, json_schema_extra={"nullable": True})
    token_kind: ResolvedTokenKind


_AUTHENTICATE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "description": "Missing or invalid bearer token",
        "model": AuthenticateErrorResponse,
    },
    500: {
        "description": "Bearer token authentication is misconfigured",
        "model": AuthenticateErrorResponse,
    },
}


@dataclass(frozen=True)
class AuthenticateDependencies:
    workload_token_exchange_service: WorkloadTokenExchangeService
    access_key_registry: AccessKeyRegistry


def get_authenticate_dependencies(
    workload_token_exchange_service: WorkloadTokenExchangeService = Depends(get_workload_token_exchange_service),
    access_key_registry: AccessKeyRegistry = Depends(get_access_key_registry),
) -> AuthenticateDependencies:
    return AuthenticateDependencies(
        workload_token_exchange_service=workload_token_exchange_service,
        access_key_registry=access_key_registry,
    )


AuthenticateDependency = Annotated[AuthenticateDependencies, Depends(get_authenticate_dependencies)]


def _bearer_token_from_request(request: Request) -> str:
    try:
        token = parse_bearer_authorization_header(request.headers.get("authorization"))
    except MalformedBearerTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return token


def _groups_from_claim(groups_claim: object) -> list[str]:
    if isinstance(groups_claim, str):
        return [group.strip() for group in groups_claim.split(",") if group.strip()]
    if isinstance(groups_claim, list):
        return [group for group in groups_claim if isinstance(group, str)]
    return []


def _scopes_from_claims(claims: dict[str, object]) -> list[str]:
    scope_claim = claims.get("scope") or claims.get("scp")
    if isinstance(scope_claim, str):
        return scope_claim.split()
    if isinstance(scope_claim, list):
        return [scope for scope in scope_claim if isinstance(scope, str)]
    return []


def _stamp_principal_headers(response: Response, resolved: ResolvedBearerToken) -> None:
    for header_name, header_value in resolved.principal_headers().items():
        response.headers[header_name] = header_value


def _response_from_claims(
    claims: TokenClaims,
    token_kind: ResolvedTokenKind,
) -> AuthenticateResponse:
    jti = claims.raw_claims.get("jti")
    return AuthenticateResponse(
        principal=claims.subject,
        email=claims.email,
        groups=claims.groups,
        scopes=claims.scopes,
        jti=jti if isinstance(jti, str) and jti else None,
        token_kind=token_kind,
    )


async def _validate_workload_access_token(
    config: AuthConfig,
    request: Request,
    token: str,
    workload_token_exchange_service: WorkloadTokenExchangeService,
) -> TokenClaims | None:
    if not config.oidc.workload_token_exchange_enabled:
        return None

    try:
        signing_key = await workload_token_exchange_service.workload_signing_key_async(config)
        public_key = signing_key.private_key.public_key()
    except Exception as exc:
        logger.exception("Failed to load workload access token signing key")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Workload token authentication is misconfigured",
        ) from exc

    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=list(_allowed_audiences(config)),
            issuer=_workload_token_issuer(config, request),
            options={"require": ["sub", "iat", "nbf", "exp"]},
            leeway=30,
        )
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            return None
        return TokenClaims(
            subject=subject,
            email=claims.get("email") if isinstance(claims.get("email"), str) else None,
            groups=_groups_from_claim(claims.get("groups", [])),
            scopes=_scopes_from_claims(claims),
            raw_claims=claims,
        )
    except jwt.PyJWTError:
        return None


async def _resolve_workload_access_token(
    config: AuthConfig,
    request: Request,
    workload_token_exchange_service: WorkloadTokenExchangeService,
    token: str,
) -> ResolvedBearerToken | None:
    claims = await _validate_workload_access_token(config, request, token, workload_token_exchange_service)
    if claims is None:
        return None
    return ResolvedBearerToken(claims=claims, token_kind="workload_access_token")


async def _resolve_workload_subject_token(
    config: AuthConfig,
    workload_token_exchange_service: WorkloadTokenExchangeService,
    token: str,
) -> ResolvedBearerToken | None:
    if not config.oidc.workload_token_exchange_enabled or not config.oidc.workload_subject_jwks_uri:
        return None

    try:
        claims = await workload_token_exchange_service.decode_jwt_subject_token(config, token)
    except jwt.PyJWTError:
        return None

    subject = claims.get(config.oidc.subject_claim, claims.get("sub"))
    if not isinstance(subject, str) or not subject:
        return None

    email = claims.get(config.oidc.email_claim)
    token_claims = TokenClaims(
        subject=subject,
        email=email if isinstance(email, str) else None,
        groups=_groups_from_claim(claims.get(config.oidc.groups_claim, claims.get("groups", []))),
        scopes=_scopes_from_claims(claims),
        raw_claims=claims,
    )
    return ResolvedBearerToken(claims=token_claims, token_kind="workload_subject_token")


async def _authenticate_bearer_token(
    request: Request,
    response: Response,
    workload_token_exchange_service: WorkloadTokenExchangeService,
    access_key_registry: AccessKeyRegistry,
) -> AuthenticateResponse:
    token = _bearer_token_from_request(request)
    config = get_auth_config()

    async def resolve_workload_access(candidate: str) -> ResolvedBearerToken | None:
        return await _resolve_workload_access_token(config, request, workload_token_exchange_service, candidate)

    async def resolve_workload_subject(candidate: str) -> ResolvedBearerToken | None:
        return await _resolve_workload_subject_token(config, workload_token_exchange_service, candidate)

    resolved = await resolve_bearer_token(
        config,
        token,
        extra_resolvers=[resolve_workload_access, resolve_workload_subject],
    )
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    if resolved.token_kind == "access_key":
        jti = resolved.claims.raw_claims.get("jti")
        if not isinstance(jti, str) or not jti:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
        if not await access_key_registry.is_active(jti, resolved.claims.subject, claims=resolved.claims):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    _stamp_principal_headers(response, resolved)
    return _response_from_claims(resolved.claims, resolved.token_kind)


@router.get(
    "/authenticate",
    response_model=AuthenticateResponse,
    operation_id="get_authenticate_bearer_token",
    responses=_AUTHENTICATE_ERROR_RESPONSES,
)
async def authenticate_bearer_token_get(
    request: Request,
    response: Response,
    dependencies: AuthenticateDependency,
) -> AuthenticateResponse:
    return await _authenticate_bearer_token(
        request,
        response,
        dependencies.workload_token_exchange_service,
        dependencies.access_key_registry,
    )


@router.post(
    "/authenticate",
    response_model=AuthenticateResponse,
    operation_id="post_authenticate_bearer_token",
    responses=_AUTHENTICATE_ERROR_RESPONSES,
)
async def authenticate_bearer_token_post(
    request: Request,
    response: Response,
    dependencies: AuthenticateDependency,
) -> AuthenticateResponse:
    return await _authenticate_bearer_token(
        request,
        response,
        dependencies.workload_token_exchange_service,
        dependencies.access_key_registry,
    )


@router.api_route(
    "/authenticate",
    methods=["DELETE", "PATCH", "PUT", "OPTIONS"],
    response_model=AuthenticateResponse,
    include_in_schema=False,
)
async def authenticate_bearer_token_callout_methods(
    request: Request,
    response: Response,
    dependencies: AuthenticateDependency,
) -> AuthenticateResponse:
    return await _authenticate_bearer_token(
        request,
        response,
        dependencies.workload_token_exchange_service,
        dependencies.access_key_registry,
    )


@router.api_route(
    "/authenticate/{original_path:path}",
    methods=["DELETE", "GET", "PATCH", "POST", "PUT", "OPTIONS"],
    response_model=AuthenticateResponse,
    include_in_schema=False,
)
async def authenticate_bearer_token_prefixed_callout(
    request: Request,
    response: Response,
    original_path: str,
    dependencies: AuthenticateDependency,
) -> AuthenticateResponse:
    _ = original_path
    return await _authenticate_bearer_token(
        request,
        response,
        dependencies.workload_token_exchange_service,
        dependencies.access_key_registry,
    )
