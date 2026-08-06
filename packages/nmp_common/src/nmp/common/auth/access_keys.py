# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from nemo_platform_plugin.auth.access_keys.issuer import (
    AccessKeyFeatureDisabledError,
    AccessKeyIssuer,
    AccessKeyOperationNotImplementedError,
)
from nemo_platform_plugin.auth.access_keys.types import (
    AccessKeyCreateRequest,
    AccessKeyCreateResponse,
    AccessKeyListResponse,
    AccessKeyRevokeResponse,
)
from nmp.common.config import AuthConfig, get_platform_config

from .jwks import DEFAULT_JWKS_CACHE_LIFESPAN, AsyncJWKSClient, signing_jwk_from_jwks
from .jwt import TokenClaims, groups_from_claim, scopes_from_claim
from .models import Principal
from .signing_keys import RSASigningKey, RSASigningKeyCache

ACCESS_KEY_TOKEN_TYPE = "access_key"
ACCESS_KEY_JWKS_PATH = "/apis/auth/jwks"
ACCESS_KEY_METADATA_VERSION = 2
LEGACY_ACCESS_KEY_METADATA_VERSION = 1

logger = logging.getLogger(__name__)


def platform_token_issuer(config: AuthConfig) -> str:
    if config.token_signing.issuer:
        return config.token_signing.issuer.rstrip("/")
    return f"{get_platform_config().base_url.rstrip('/')}/apis/auth"


def access_key_issuer(config: AuthConfig) -> str:
    return platform_token_issuer(config)


def access_key_jwks_uri(config: AuthConfig) -> str:
    return f"{get_platform_config().base_url.rstrip('/')}{ACCESS_KEY_JWKS_PATH}"


_ACCESS_KEY_SIGNING_KEY_CACHE = RSASigningKeyCache()
_ACCESS_KEY_MISSING_PRIVATE_KEY_MESSAGE = (
    "auth.token_signing.private_key_file must be configured to create Scoped Access Keys"
)
_ACCESS_KEY_INVALID_PRIVATE_KEY_MESSAGE = "auth.token_signing.private_key_file must contain an RSA private key"
_ACCESS_KEY_JWKS_CLIENTS: dict[str, AsyncJWKSClient] = {}
_EXPIRES_IN_SECONDS_FIELD = "expires_in_seconds"


class AccessKeyValidationError(ValueError):
    """Raised when a Scoped Access Key request conflicts with platform policy."""


@dataclass(frozen=True)
class _AccessKeyTokenPayload:
    claims: dict[str, Any]
    jti: str
    name: str | None
    description: str | None
    principal: str
    issuer: str
    audiences: list[str]
    created_at: datetime
    expires_at: datetime | None


def clear_access_key_signing_key_cache() -> None:
    _ACCESS_KEY_SIGNING_KEY_CACHE.clear()
    _ACCESS_KEY_JWKS_CLIENTS.clear()


def _groups_claim_for_gateway_header(groups: list[str]) -> str | None:
    groups_claim = ",".join(group.strip() for group in groups if group.strip())
    return groups_claim or None


def is_access_key_token_candidate(token: str) -> bool:
    """Return True when an untrusted token claims to be a Scoped Access Key."""
    try:
        unverified = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
                "verify_aud": False,
            },
        )
    except jwt.DecodeError:
        return False
    return unverified.get("nmp_token_type") == ACCESS_KEY_TOKEN_TYPE


def _access_key_signing_key(config: AuthConfig) -> RSASigningKey:
    return _ACCESS_KEY_SIGNING_KEY_CACHE.get_from_file(
        kid=config.token_signing.key_id,
        private_key_file=config.token_signing.private_key_file,
        missing_private_key_message=_ACCESS_KEY_MISSING_PRIVATE_KEY_MESSAGE,
        invalid_private_key_message=_ACCESS_KEY_INVALID_PRIVATE_KEY_MESSAGE,
    )


async def _access_key_signing_key_async(config: AuthConfig) -> RSASigningKey:
    return await _ACCESS_KEY_SIGNING_KEY_CACHE.get_from_file_async(
        kid=config.token_signing.key_id,
        private_key_file=config.token_signing.private_key_file,
        missing_private_key_message=_ACCESS_KEY_MISSING_PRIVATE_KEY_MESSAGE,
        invalid_private_key_message=_ACCESS_KEY_INVALID_PRIVATE_KEY_MESSAGE,
    )


def _private_key(config: AuthConfig) -> rsa.RSAPrivateKey:
    return _access_key_signing_key(config).private_key


def public_jwk_from_private_key_pem(config: AuthConfig) -> dict[str, Any]:
    return dict(_access_key_signing_key(config).public_jwk)


async def public_jwk_from_private_key_pem_async(config: AuthConfig) -> dict[str, Any]:
    signing_key = await _access_key_signing_key_async(config)
    return dict(signing_key.public_jwk)


def _access_key_jwks_client(config: AuthConfig) -> AsyncJWKSClient:
    jwks_uri = access_key_jwks_uri(config)
    client = _ACCESS_KEY_JWKS_CLIENTS.get(jwks_uri)
    if client is None:
        client = AsyncJWKSClient(jwks_uri, lifespan=DEFAULT_JWKS_CACHE_LIFESPAN)
        _ACCESS_KEY_JWKS_CLIENTS[jwks_uri] = client
    return client


async def _access_key_signing_key_from_remote_jwks(config: AuthConfig, token: str) -> Any:
    return (await _access_key_jwks_client(config).get_signing_key_from_jwt(token)).key


def _resolve_expires_in_seconds(config: AuthConfig, request: AccessKeyCreateRequest) -> int | None:
    max_expires_in_seconds = config.access_keys.max_expires_in_seconds
    expires_in_seconds_was_set = _EXPIRES_IN_SECONDS_FIELD in request.model_fields_set
    if expires_in_seconds_was_set:
        expires_in_seconds = request.expires_in_seconds
    else:
        expires_in_seconds = config.access_keys.default_expires_in_seconds

    if expires_in_seconds is None:
        if max_expires_in_seconds is not None:
            if expires_in_seconds_was_set:
                raise AccessKeyValidationError(
                    "expires_in_seconds=null requires auth.access_keys.max_expires_in_seconds to be disabled"
                )
            raise AccessKeyValidationError(
                "expires_in_seconds is required when auth.access_keys.default_expires_in_seconds is null "
                "and auth.access_keys.max_expires_in_seconds is finite"
            )
        return None

    if max_expires_in_seconds is not None and expires_in_seconds > max_expires_in_seconds:
        raise AccessKeyValidationError(
            "expires_in_seconds must be less than or equal to "
            f"auth.access_keys.max_expires_in_seconds ({max_expires_in_seconds})"
        )
    return expires_in_seconds


class AccessKeyIssuerService(AccessKeyIssuer):
    """AccessKeyIssuer implementation that signs Scoped Access Key JWTs in the auth service."""

    def __init__(
        self,
        *,
        config: AuthConfig,
        principal: Principal,
        now: Callable[[], int] | None = None,
    ) -> None:
        self._config = config
        self._principal = principal
        self._now = now or (lambda: int(time.time()))

    def _ensure_enabled(self) -> None:
        if not self._config.access_keys.enabled:
            raise AccessKeyFeatureDisabledError("Scoped Access Keys are not enabled")

    def create(self, request: AccessKeyCreateRequest) -> AccessKeyCreateResponse:
        self._ensure_enabled()
        expires_in_seconds = _resolve_expires_in_seconds(self._config, request)
        return _create_access_key_token(
            self._config,
            principal=self._principal,
            name=request.name,
            description=request.description,
            expires_in_seconds=expires_in_seconds,
            now=self._now(),
        )

    async def create_async(self, request: AccessKeyCreateRequest) -> AccessKeyCreateResponse:
        self._ensure_enabled()
        expires_in_seconds = _resolve_expires_in_seconds(self._config, request)
        return await _create_access_key_token_async(
            self._config,
            principal=self._principal,
            name=request.name,
            description=request.description,
            expires_in_seconds=expires_in_seconds,
            now=self._now(),
        )

    def list(self, *, page: int = 1, page_size: int = 100) -> AccessKeyListResponse:  # noqa: ARG002
        self._ensure_enabled()
        raise AccessKeyOperationNotImplementedError("Scoped Access Key listing is not implemented.")

    def revoke(self, jti: str) -> AccessKeyRevokeResponse:
        self._ensure_enabled()
        raise AccessKeyOperationNotImplementedError(f"Scoped Access Key revocation for {jti} is not implemented.")


def _create_access_key_token(
    config: AuthConfig,
    *,
    principal: Principal,
    name: str | None = None,
    description: str | None = None,
    expires_in_seconds: int | None = None,
    now: int,
) -> AccessKeyCreateResponse:
    payload = _build_access_key_token_payload(
        config,
        principal=principal,
        name=name,
        description=description,
        expires_in_seconds=expires_in_seconds,
        now=now,
    )
    return _access_key_response_from_payload(payload, _access_key_signing_key(config))


async def _create_access_key_token_async(
    config: AuthConfig,
    *,
    principal: Principal,
    name: str | None = None,
    description: str | None = None,
    expires_in_seconds: int | None = None,
    now: int,
) -> AccessKeyCreateResponse:
    payload = _build_access_key_token_payload(
        config,
        principal=principal,
        name=name,
        description=description,
        expires_in_seconds=expires_in_seconds,
        now=now,
    )
    signing_key = await _access_key_signing_key_async(config)
    return _access_key_response_from_payload(payload, signing_key)


def _build_access_key_token_payload(
    config: AuthConfig,
    *,
    principal: Principal,
    name: str | None,
    description: str | None,
    expires_in_seconds: int | None,
    now: int,
) -> _AccessKeyTokenPayload:
    if not config.access_keys.enabled:
        raise AccessKeyFeatureDisabledError("Scoped Access Keys are not enabled")
    if principal.id.startswith("service:"):
        raise AccessKeyValidationError("Scoped Access Keys cannot be created for service principals")

    issued_at = now
    jti = f"ak_{uuid.uuid4().hex}"
    access_key_metadata: dict[str, Any] = {"version": ACCESS_KEY_METADATA_VERSION}
    if name is not None:
        access_key_metadata["name"] = name
    issuer = access_key_issuer(config)
    audiences = [config.access_keys.audience]
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": config.access_keys.audience,
        "sub": principal.id,
        "iat": issued_at,
        "nbf": issued_at,
        "jti": jti,
        "nmp_token_type": ACCESS_KEY_TOKEN_TYPE,
        "nmp_access_key": access_key_metadata,
    }
    if principal.email:
        claims["email"] = principal.email
    if principal.groups:
        groups_claim = _groups_claim_for_gateway_header(principal.groups)
        if groups_claim:
            claims["groups"] = groups_claim
    expires_at = None
    if expires_in_seconds is not None:
        expires_at_timestamp = issued_at + expires_in_seconds
        claims["exp"] = expires_at_timestamp
        expires_at = datetime.fromtimestamp(expires_at_timestamp, tz=UTC)

    return _AccessKeyTokenPayload(
        claims=claims,
        jti=jti,
        name=name,
        description=description,
        principal=principal.id,
        issuer=issuer,
        audiences=audiences,
        created_at=datetime.fromtimestamp(issued_at, tz=UTC),
        expires_at=expires_at,
    )


def _access_key_response_from_payload(
    payload: _AccessKeyTokenPayload,
    signing_key: RSASigningKey,
) -> AccessKeyCreateResponse:
    token = jwt.encode(
        payload.claims,
        signing_key.private_key,
        algorithm="RS256",
        headers={"kid": signing_key.kid},
    )
    return AccessKeyCreateResponse(
        jti=payload.jti,
        name=payload.name,
        description=payload.description,
        token=token,
        token_type="Bearer",
        principal=payload.principal,
        status="ACTIVE",
        issuer=payload.issuer,
        audiences=payload.audiences,
        created_at=payload.created_at,
        expires_at=payload.expires_at,
    )


async def validate_access_key_token(
    config: AuthConfig,
    token: str,
    *,
    jwks_override: dict[str, Any] | None = None,
    now: int | None = None,
) -> TokenClaims | None:
    if not config.access_keys.enabled:
        return None
    if "jwt" not in config.access_keys.accepted_formats:
        return None

    try:
        unverified = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
                "verify_aud": False,
            },
        )
        if unverified.get("nmp_token_type") != ACCESS_KEY_TOKEN_TYPE:
            return None

        if jwks_override is None:
            signing_key = await _access_key_signing_key_from_remote_jwks(config, token)
        else:
            signing_key = signing_jwk_from_jwks(token, jwks_override).key

        options: dict[str, Any] = {"require": ["sub", "iat", "nbf", "jti"]}
        decode_kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "audience": config.access_keys.audience,
            "issuer": access_key_issuer(config),
            "options": options,
            "leeway": 30,
        }
        if now is not None:
            decode_kwargs["current_time"] = now
        claims = jwt.decode(token, signing_key, **decode_kwargs)

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or subject.startswith("service:"):
            return None

        groups = groups_from_claim(claims.get("groups", []))
        scope_claim = claims.get("scope") or claims.get("scp")
        return TokenClaims(
            subject=subject,
            email=claims.get("email") if isinstance(claims.get("email"), str) else None,
            groups=groups,
            scopes=scopes_from_claim(scope_claim),
            raw_claims=claims,
        )
    except httpx.HTTPError:
        raise
    except Exception as exc:
        logger.warning("Access key token validation failed: %s", exc, exc_info=True)
        return None
