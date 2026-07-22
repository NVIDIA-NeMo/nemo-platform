# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Workload identity token exchange endpoints."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from jwt.algorithms import RSAAlgorithm
from nmp.common.config import AuthConfig, get_auth_config, get_platform_config
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

TOKEN_EXCHANGE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
JWT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"
ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"

WORKLOAD_TOKEN_PATH = "/apis/auth/token"
WORKLOAD_JWKS_PATH = "/apis/auth/jwks"
DEFAULT_WORKLOAD_AUDIENCE = "nemo-platform"
DEFAULT_WORKLOAD_SCOPE = "openid email groups"

_TOKEN_EXCHANGE_FORM_REQUEST_BODY: dict[str, Any] = {
    "required": True,
    "content": {
        "application/x-www-form-urlencoded": {
            "schema": {
                "type": "object",
                "required": ["grant_type", "client_id", "subject_token", "subject_token_type"],
                "properties": {
                    "grant_type": {
                        "type": "string",
                        "description": "OAuth 2.0 token exchange grant type.",
                        "enum": [TOKEN_EXCHANGE_GRANT_TYPE],
                    },
                    "client_id": {
                        "type": "string",
                        "description": "Workload token exchange OAuth client ID.",
                    },
                    "subject_token": {
                        "type": "string",
                        "description": "JWT subject token to exchange.",
                    },
                    "subject_token_type": {
                        "type": "string",
                        "description": "Token type identifier for the subject token.",
                        "enum": [JWT_TOKEN_TYPE],
                    },
                    "requested_token_type": {
                        "type": "string",
                        "description": "Requested token type identifier for the issued token.",
                        "default": ACCESS_TOKEN_TYPE,
                        "enum": [ACCESS_TOKEN_TYPE],
                    },
                    "audience": {
                        "type": "string",
                        "description": "Requested audience for the issued access token.",
                    },
                    "scope": {
                        "type": "string",
                        "description": "Space-separated scopes requested for the issued access token.",
                    },
                },
            }
        }
    },
}

router = APIRouter(tags=["Workload Identity"])


@dataclass(frozen=True)
class _WorkloadSigningKey:
    private_key: rsa.RSAPrivateKey
    public_key: rsa.RSAPublicKey
    kid: str


@dataclass(frozen=True)
class _SubjectJWKSCacheEntry:
    jwks: dict[str, Any]
    fetched_at: float


@dataclass(frozen=True)
class _SubjectTokenDecoder:
    name: str
    decode: Callable[[], Awaitable[dict[str, Any]]]


class WorkloadTokenExchangeResponse(BaseModel):
    """RFC 8693 token exchange response for workload identity access tokens."""

    access_token: str = Field(description="JWT access token minted for the workload identity.")
    issued_token_type: str = Field(description="Token type identifier for the issued token.")
    token_type: str = Field(description="OAuth token type used in Authorization headers.")
    expires_in: int = Field(description="Lifetime of the access token in seconds.")
    scope: str | None = Field(default=None, description="Space-separated scopes granted to the access token.")


class WorkloadTokenExchangeErrorResponse(BaseModel):
    """RFC 8693 token exchange error response."""

    error: str = Field(
        description=(
            "OAuth 2.0 or RFC 8693 token exchange error code, such as invalid_client, "
            "invalid_request, invalid_grant, invalid_scope, or invalid_target."
        ),
    )
    error_description: str | None = Field(
        default=None,
        description="Human-readable ASCII text providing additional information about the error.",
    )
    error_uri: str | None = Field(
        default=None,
        description="URI identifying a human-readable web page with information about the error.",
    )


class JsonWebKey(BaseModel):
    """JSON Web Key object."""

    model_config = ConfigDict(extra="allow")


class JsonWebKeySetResponse(BaseModel):
    """JSON Web Key Set document."""

    keys: list[JsonWebKey] = Field(description="Public signing keys in the JWKS document.")


class ValidationError(BaseModel):
    """FastAPI validation error item."""

    loc: list[str | int] = Field(description="Location of the validation error.")
    msg: str = Field(description="Validation error message.")
    type: str = Field(description="Validation error type.")


class HTTPValidationError(BaseModel):
    """FastAPI request validation error response."""

    detail: list[ValidationError] | None = Field(default=None, description="Validation error details.")


_WORKLOAD_TOKEN_EXCHANGE_SERVICE_STATE_KEY = "workload_token_exchange_service"


def _platform_base_url_from_request(request: Request | None) -> str:
    if request is not None:
        return str(request.base_url).rstrip("/")
    return get_platform_config().base_url.rstrip("/")


def workload_token_endpoint_url(request: Request | None = None) -> str:
    """Return the externally reachable workload token exchange endpoint URL."""
    return f"{_platform_base_url_from_request(request)}{WORKLOAD_TOKEN_PATH}"


def workload_jwks_url(request: Request | None = None) -> str:
    """Return the externally reachable workload exchange JWKS URL."""
    return f"{_platform_base_url_from_request(request)}{WORKLOAD_JWKS_PATH}"


def _workload_token_issuer(config: AuthConfig, request: Request | None) -> str:
    return config.oidc.workload_token_issuer or f"{_platform_base_url_from_request(request)}/apis/auth"


def _workload_private_key_pem(config: AuthConfig) -> bytes:
    private_key_file = config.oidc.workload_token_private_key_file
    if private_key_file:
        try:
            return Path(private_key_file).read_bytes()
        except OSError as exc:
            raise RuntimeError(f"Could not read workload token private key file: {private_key_file}") from exc

    raise RuntimeError("workload_token_private_key_file must be configured for workload token exchange")


def _subject_token_key_id(subject_token: str) -> str:
    key_id = jwt.get_unverified_header(subject_token).get("kid")
    if not key_id:
        raise jwt.InvalidTokenError("subject token did not include a signing key id")
    return str(key_id)


def _find_subject_signing_key(key_id: str, jwks: dict[str, Any]) -> Any | None:
    jwk_set = jwt.PyJWKSet.from_dict(jwks)
    signing_keys = [jwk for jwk in jwk_set.keys if jwk.public_key_use in ("sig", None) and jwk.key_id]
    for jwk in signing_keys:
        if jwk.key_id == key_id:
            return jwk.key
    return None


def _validate_subject_jwks(jwks: dict[str, Any]) -> None:
    try:
        jwt.PyJWKSet.from_dict(jwks)
    except (jwt.PyJWTError, TypeError, ValueError, KeyError) as exc:
        raise jwt.InvalidTokenError("Subject token JWKS response was not a valid JWKS") from exc


class WorkloadTokenExchangeService:
    """Stateful helpers for workload token exchange endpoints."""

    def __init__(self) -> None:
        self._workload_signing_key_cache: dict[tuple[str, str], _WorkloadSigningKey] = {}
        self._subject_jwks_cache: dict[str, _SubjectJWKSCacheEntry] = {}

    def workload_signing_key(self, config: AuthConfig) -> _WorkloadSigningKey:
        kid = config.oidc.workload_token_key_id
        if not kid:
            raise RuntimeError("workload_token_key_id must be configured for workload token exchange")

        private_key_pem = _workload_private_key_pem(config)
        cache_key = (kid, sha256(private_key_pem).hexdigest())
        cached = self._workload_signing_key_cache.get(cache_key)
        if cached is not None:
            return cached

        private_key = serialization.load_pem_private_key(private_key_pem, password=None)
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise RuntimeError("workload token private key must be an RSA private key")

        signing_key = _WorkloadSigningKey(private_key=private_key, public_key=private_key.public_key(), kid=kid)
        self._workload_signing_key_cache[cache_key] = signing_key
        return signing_key

    def public_jwk(self, config: AuthConfig) -> dict[str, Any]:
        signing_key = self.workload_signing_key(config)
        jwk = json.loads(RSAAlgorithm.to_jwk(signing_key.public_key))
        jwk.update({"kid": signing_key.kid, "use": "sig", "alg": "RS256"})
        return jwk

    async def fetch_subject_jwks(self, config: AuthConfig, *, refresh: bool = False) -> dict[str, Any]:
        jwks_uri = config.oidc.workload_subject_jwks_uri
        if not jwks_uri:
            raise jwt.InvalidTokenError("JWT subject token validation is disabled")

        now = time.monotonic()
        cache_ttl = config.oidc.workload_subject_jwks_cache_ttl_seconds
        cached = self._subject_jwks_cache.get(jwks_uri)
        if cached is not None and cache_ttl > 0 and not refresh and (now - cached.fetched_at) < cache_ttl:
            return cached.jwks

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(jwks_uri)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise jwt.InvalidTokenError(f"Subject token JWKS request failed: {exc}") from exc

        jwks = response.json()
        if not isinstance(jwks, dict):
            raise jwt.InvalidTokenError("Subject token JWKS response was not an object")
        _validate_subject_jwks(jwks)
        if cache_ttl > 0:
            self._subject_jwks_cache[jwks_uri] = _SubjectJWKSCacheEntry(jwks=jwks, fetched_at=time.monotonic())
        return jwks

    async def get_subject_signing_key(self, config: AuthConfig, subject_token: str) -> Any:
        key_id = _subject_token_key_id(subject_token)
        jwks = await self.fetch_subject_jwks(config)
        signing_key = _find_subject_signing_key(key_id, jwks)
        if signing_key is not None:
            return signing_key

        jwks = await self.fetch_subject_jwks(config, refresh=True)
        signing_key = _find_subject_signing_key(key_id, jwks)
        if signing_key is not None:
            return signing_key

        raise jwt.InvalidTokenError(f'Unable to find a signing key that matches: "{key_id}"')

    async def decode_jwt_subject_token(self, config: AuthConfig, subject_token: str) -> dict[str, Any]:
        signing_key = await self.get_subject_signing_key(config, subject_token)
        claims = jwt.decode(
            subject_token,
            signing_key,
            algorithms=["RS256"],
            audience=_workload_subject_audience(config),
            leeway=30,
            options={"require": ["exp"]},
        )
        issuer = claims.get("iss")
        if issuer not in _allowed_subject_issuers(config):
            raise jwt.InvalidIssuerError(f"unexpected subject token issuer: {issuer!r}")
        return claims

    async def decode_subject_token(self, config: AuthConfig, subject_token: str, audience: str) -> dict[str, Any]:
        errors: list[str] = []
        for decoder in (
            _SubjectTokenDecoder("JWT subject token", lambda: self.decode_jwt_subject_token(config, subject_token)),
            _SubjectTokenDecoder(
                "Kubernetes TokenReview subject token",
                lambda: _decode_kubernetes_subject_token(config, subject_token, audience),
            ),
        ):
            try:
                return await decoder.decode()
            except jwt.InvalidTokenError as exc:
                message = str(exc) or exc.__class__.__name__
                errors.append(f"{decoder.name}: {message}")
        raise jwt.InvalidTokenError("; ".join(errors))


def get_workload_token_exchange_service(request: Request) -> WorkloadTokenExchangeService:
    service = getattr(request.app.state, _WORKLOAD_TOKEN_EXCHANGE_SERVICE_STATE_KEY, None)
    if isinstance(service, WorkloadTokenExchangeService):
        return service

    service = WorkloadTokenExchangeService()
    setattr(request.app.state, _WORKLOAD_TOKEN_EXCHANGE_SERVICE_STATE_KEY, service)
    return service


def _oauth_error(status_code: int, error: str, description: str) -> JSONResponse:
    # Keep descriptions passed to clients fixed and non-sensitive. Detailed
    # validation errors are logged at call sites instead of returned here.
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "error_description": description,
        },
    )


def _workload_client_id(config: AuthConfig) -> str:
    return config.oidc.workload_client_id or config.oidc.client_id


def _workload_subject_audience(config: AuthConfig) -> str:
    return _workload_client_id(config) or DEFAULT_WORKLOAD_AUDIENCE


def _default_workload_audience(config: AuthConfig) -> str:
    return config.oidc.workload_audience or config.oidc.audience or DEFAULT_WORKLOAD_AUDIENCE


def _allowed_audiences(config: AuthConfig) -> set[str]:
    return {_default_workload_audience(config), *config.oidc.workload_allowed_audiences}


def _validated_audience(config: AuthConfig, requested_audience: Any) -> str:
    audience = str(requested_audience or _default_workload_audience(config))
    if audience not in _allowed_audiences(config):
        raise jwt.InvalidAudienceError(f"unexpected requested audience: {audience!r}")
    return audience


def _groups_claim_for_gateway_header(groups: Any) -> str | None:
    if isinstance(groups, str):
        return groups
    if isinstance(groups, list):
        return ",".join(str(group).strip() for group in groups if str(group).strip())
    return None


def _allowed_subject_issuers(config: AuthConfig) -> set[str]:
    return {issuer for issuer in config.oidc.workload_subject_issuers if issuer}


def _kubernetes_reviewer_credentials() -> tuple[str, str]:
    service_account_dir = Path("/var/run/secrets/kubernetes.io/serviceaccount")
    reviewer_token = (service_account_dir / "token").read_text(encoding="utf-8").strip()
    ca_path = service_account_dir / "ca.crt"
    return reviewer_token, str(ca_path)


async def _decode_kubernetes_subject_token(
    config: AuthConfig,
    subject_token: str,
    audience: str,
) -> dict[str, Any]:
    if not config.oidc.workload_kubernetes_token_review_enabled:
        raise jwt.InvalidTokenError("Kubernetes TokenReview subject token validation is disabled")

    import os

    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    if not host:
        raise jwt.InvalidTokenError("Kubernetes service environment is unavailable")

    reviewer_token, ca_path = _kubernetes_reviewer_credentials()
    token_review_url = f"https://{host}:{port}/apis/authentication.k8s.io/v1/tokenreviews"
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=ca_path) as client:
            response = await client.post(
                token_review_url,
                json={
                    "apiVersion": "authentication.k8s.io/v1",
                    "kind": "TokenReview",
                    "spec": {
                        "token": subject_token,
                        "audiences": [audience],
                    },
                },
                headers={
                    "Authorization": f"Bearer {reviewer_token}",
                    "Content-Type": "application/json",
                },
            )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise jwt.InvalidTokenError(f"Kubernetes TokenReview request failed: {exc}") from exc

    token_review = response.json()
    if not isinstance(token_review, dict):
        raise jwt.InvalidTokenError("Kubernetes TokenReview response was not an object")

    status = token_review.get("status", {})
    if not isinstance(status, dict):
        raise jwt.InvalidTokenError("Kubernetes TokenReview response did not include a status object")
    if not status.get("authenticated"):
        raise jwt.InvalidTokenError(status.get("error") or "Kubernetes TokenReview rejected subject token")

    user = status.get("user", {})
    if not isinstance(user, dict):
        raise jwt.InvalidTokenError("Kubernetes TokenReview response did not include a user object")
    subject = user.get("username")
    if not subject:
        raise jwt.InvalidTokenError("Kubernetes TokenReview response did not include a username")

    return {
        "sub": subject,
        "groups": user.get("groups", []),
    }


@router.get(
    "/jwks",
    summary="Workload identity token exchange JWKS",
    description="Return the public signing key for workload identity access tokens minted by the NeMo auth service.",
    response_model=JsonWebKeySetResponse,
)
async def jwks(
    workload_token_exchange_service: WorkloadTokenExchangeService = Depends(get_workload_token_exchange_service),
) -> JsonWebKeySetResponse:
    """Return workload identity exchange signing keys."""
    return JsonWebKeySetResponse(keys=[JsonWebKey(**workload_token_exchange_service.public_jwk(get_auth_config()))])


@router.post(
    "/token",
    summary="Exchange a workload identity subject token",
    description="Exchange a configured workload identity subject token for a NeMo Platform access token.",
    response_model=WorkloadTokenExchangeResponse,
    responses={
        400: {
            "description": "RFC 8693 token exchange error",
            "model": WorkloadTokenExchangeErrorResponse,
        },
        401: {
            "description": "OAuth 2.0 invalid_client error",
            "model": WorkloadTokenExchangeErrorResponse,
        },
    },
    openapi_extra={"requestBody": _TOKEN_EXCHANGE_FORM_REQUEST_BODY},
)
async def token_exchange(
    request: Request,
    workload_token_exchange_service: WorkloadTokenExchangeService = Depends(get_workload_token_exchange_service),
) -> WorkloadTokenExchangeResponse | JSONResponse:
    """Exchange an RFC 8693 workload identity subject token for a NeMo access token."""
    config = get_auth_config()
    if not config.oidc.workload_token_exchange_enabled:
        return _oauth_error(400, "invalid_request", "Workload token exchange is not enabled")

    form = await request.form()
    client_id = _workload_client_id(config)

    if form.get("grant_type") != TOKEN_EXCHANGE_GRANT_TYPE:
        return _oauth_error(400, "unsupported_grant_type", "Only RFC 8693 token exchange is supported")
    if form.get("client_id") != client_id:
        return _oauth_error(401, "invalid_client", "Unknown workload token exchange client")
    if form.get("subject_token_type") != JWT_TOKEN_TYPE:
        return _oauth_error(400, "invalid_request", "subject_token_type must be a JWT token type")
    if form.get("requested_token_type", ACCESS_TOKEN_TYPE) != ACCESS_TOKEN_TYPE:
        return _oauth_error(400, "invalid_request", "requested_token_type must be access_token")

    subject_token = form.get("subject_token")
    if not subject_token:
        return _oauth_error(400, "invalid_request", "subject_token is required")

    try:
        audience = _validated_audience(config, form.get("audience"))
    except jwt.InvalidAudienceError as exc:
        logger.info("Requested token audience validation failed: %s", exc)
        return _oauth_error(400, "invalid_target", "Requested audience is not allowed")

    try:
        subject_claims = await workload_token_exchange_service.decode_subject_token(
            config, str(subject_token), _workload_subject_audience(config)
        )
        subject = subject_claims.get("sub")
        if not subject:
            raise jwt.InvalidTokenError("Subject token did not include a subject")
    except jwt.InvalidTokenError as exc:
        logger.info("Subject token validation failed: %s", exc)
        # RFC 8693 clients only need a stable invalid_request response. Avoid
        # returning decoder details that may include infrastructure internals.
        return _oauth_error(400, "invalid_request", "Could not validate subject token")

    now = int(time.time())
    scope = str(form.get("scope") or config.oidc.workload_scope or DEFAULT_WORKLOAD_SCOPE)
    exchanged_claims: dict[str, Any] = {
        "iss": _workload_token_issuer(config, request),
        "sub": subject,
        "aud": audience,
        "iat": now,
        "nbf": now,
        "exp": now + config.oidc.workload_token_ttl_seconds,
        "scope": scope,
    }
    if "email" in subject_claims:
        exchanged_claims["email"] = subject_claims["email"]
    if "groups" in subject_claims:
        groups_claim = _groups_claim_for_gateway_header(subject_claims["groups"])
        if groups_claim:
            exchanged_claims["groups"] = groups_claim

    signing_key = workload_token_exchange_service.workload_signing_key(config)
    access_token = jwt.encode(
        exchanged_claims,
        signing_key.private_key,
        algorithm="RS256",
        headers={"kid": signing_key.kid},
    )
    return WorkloadTokenExchangeResponse(
        access_token=access_token,
        issued_token_type=ACCESS_TOKEN_TYPE,
        token_type="Bearer",
        expires_in=config.oidc.workload_token_ttl_seconds,
        scope=scope,
    )
