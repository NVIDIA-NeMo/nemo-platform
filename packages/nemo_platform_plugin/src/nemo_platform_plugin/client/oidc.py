# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OIDC token management for NemoClient.

Provides:

- :class:`OIDCTokenProvider` — thread-safe OIDC token refresh.
- :class:`TokenSet` — access + refresh token pair with expiry.
- :class:`NMPOIDCConfig` — OIDC discovery response model.
- JWT decode helpers (no verification — for expiry extraction only).
- OIDC discovery and scope helpers.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class TokenRefreshError(RuntimeError):
    """Structured error raised for OAuth refresh_token grant failures."""

    def __init__(self, *, error: str, error_description: str) -> None:
        self.error = error
        self.error_description = error_description
        super().__init__(f"Token refresh failed: {error} - {error_description}")


# ---------------------------------------------------------------------------
# JWT helpers (decode only, no verification)
# ---------------------------------------------------------------------------


def _decode_jwt_segment(token: str, index: int) -> dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[index]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def decode_jwt_claims(token: str) -> dict[str, Any]:
    """Decode JWT claims without verification (for display/expiry extraction only)."""
    return _decode_jwt_segment(token, 1)


def decode_jwt_header(token: str) -> dict[str, Any]:
    """Decode JWT header without verification."""
    return _decode_jwt_segment(token, 0)


def _base64url_encode_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")


def generate_unsigned_jwt(
    principal_id: str,
    *,
    email: str | None = None,
    groups: list[str] | None = None,
    scopes: list[str] | None = None,
    expires_in_seconds: int | None = 3600,
    issued_at: int | None = None,
    audience: str | None = None,
    issuer: str | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Generate an unsigned JWT (``alg=none``) for local development and testing."""
    now = issued_at if issued_at is not None else int(time.time())
    claims: dict[str, Any] = {
        "sub": principal_id,
        "iat": now,
    }

    if email:
        claims["email"] = email
    if groups:
        claims["groups"] = groups
    if scopes:
        claims["scope"] = " ".join(scopes)
    if expires_in_seconds is not None:
        claims["exp"] = now + expires_in_seconds
    if audience:
        claims["aud"] = audience
    if issuer:
        claims["iss"] = issuer
    if extra_claims:
        claims.update(extra_claims)

    header_segment = _base64url_encode_json({"alg": "none", "typ": "JWT"})
    claims_segment = _base64url_encode_json(claims)
    return f"{header_segment}.{claims_segment}."


# ---------------------------------------------------------------------------
# OIDC discovery
# ---------------------------------------------------------------------------

DEFAULT_OAUTH_SCOPES = "openid profile email offline_access"


@dataclass(frozen=True)
class NMPOIDCConfig:
    """OIDC configuration discovered from the NeMo Platform."""

    auth_enabled: bool
    issuer: str | None = None
    client_id: str | None = None
    token_endpoint: str | None = None
    device_authorization_endpoint: str | None = None
    default_scopes: str = DEFAULT_OAUTH_SCOPES
    scope_prefix: str | None = None


def discover_nmp_config(base_url: str, timeout: float = 10.0) -> NMPOIDCConfig:
    """Fetch OIDC configuration from the NeMo Platform auth discovery endpoint."""
    response = httpx.get(
        f"{base_url.rstrip('/')}/apis/auth/discovery",
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    oidc = data.get("oidc") or {}
    return NMPOIDCConfig(
        auth_enabled=data.get("auth_enabled", False),
        issuer=oidc.get("issuer"),
        client_id=oidc.get("client_id"),
        token_endpoint=oidc.get("token_endpoint"),
        device_authorization_endpoint=oidc.get("device_authorization_endpoint"),
        default_scopes=oidc.get("default_scopes", DEFAULT_OAUTH_SCOPES),
        scope_prefix=oidc.get("scope_prefix"),
    )


def _discover_oidc_client_settings(base_url: str) -> NMPOIDCConfig:
    """Fetch OIDC config with a safe fallback if unreachable."""
    try:
        return discover_nmp_config(base_url)
    except Exception:
        logger.debug("Could not discover OIDC settings from %s", base_url, exc_info=True)
        return NMPOIDCConfig(
            auth_enabled=False,
            client_id="",
            token_endpoint="",
            default_scopes="openid profile email",
            scope_prefix=None,
        )


def _normalize_scope_prefix(prefix: str | None) -> str:
    if not prefix:
        return ""
    return prefix if prefix.endswith("/") else f"{prefix}/"


def build_effective_scope(requested_scopes: str, scope_prefix: str | None) -> str:
    """Prepend scope_prefix to custom scopes (those with ':' or ending with '.default')."""
    prefix = _normalize_scope_prefix(scope_prefix)
    if not prefix:
        return requested_scopes
    expanded = []
    for s in requested_scopes.split():
        if ":" in s or s.endswith(".default"):
            expanded.append(f"{prefix}{s}")
        else:
            expanded.append(s)
    return " ".join(expanded)


# ---------------------------------------------------------------------------
# OAuth refresh_token grant
# ---------------------------------------------------------------------------

# Refresh proactively when less than this many seconds remain before expiry.
DEFAULT_REFRESH_MARGIN_SECONDS = 60


def _validate_token_endpoint(token_endpoint: str) -> None:
    """Reject non-HTTPS token endpoints (except loopback for local dev)."""
    parsed = urlparse(token_endpoint)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return
    raise ValueError(
        f"OIDC token endpoint must use HTTPS (got {token_endpoint!r}). "
        "HTTP is only allowed for loopback addresses (localhost, 127.0.0.1, ::1)."
    )


def refresh_token_grant(
    token_endpoint: str,
    client_id: str,
    refresh_token: str,
    *,
    scope: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Execute OAuth refresh_token grant and return token response JSON."""
    _validate_token_endpoint(token_endpoint)
    data: dict[str, str] = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if scope:
        data["scope"] = scope

    response = httpx.post(token_endpoint, data=data, timeout=timeout)

    if response.status_code != 200:
        error_data: dict[str, str] = {}
        if response.headers.get("content-type", "").startswith("application/json"):
            try:
                error_data = response.json()
            except (json.JSONDecodeError, ValueError):
                error_data = {}
        error = error_data.get("error", "unknown_error")
        error_description = error_data.get("error_description", response.text)
        raise TokenRefreshError(error=error, error_description=error_description)

    return response.json()


# ---------------------------------------------------------------------------
# TokenSet
# ---------------------------------------------------------------------------


@dataclass
class TokenSet:
    """A pair of access + refresh tokens with expiry metadata."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    expires_at: float | None = None

    @staticmethod
    def from_access_token(
        access_token: str,
        refresh_token: str | None = None,
        *,
        expires_in: int | float | None = None,
    ) -> TokenSet:
        """Create a TokenSet, extracting expiry from the JWT's ``exp`` claim.

        Falls back to ``expires_in`` (seconds from now) for opaque tokens
        that don't contain a JWT ``exp`` claim.
        """
        expires_at = None
        claims = decode_jwt_claims(access_token)
        if claims:
            expires_at = claims.get("exp")
        if expires_at is None and expires_in is not None:
            expires_at = time.time() + float(expires_in)
        return TokenSet(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=float(expires_at) if expires_at is not None else None,
        )

    def is_expired(self, margin_seconds: float = DEFAULT_REFRESH_MARGIN_SECONDS) -> bool:
        """Check if the access token is expired or about to expire."""
        if self.expires_at is None:
            return False
        return time.time() >= (self.expires_at - margin_seconds)


# ---------------------------------------------------------------------------
# OIDCTokenProvider
# ---------------------------------------------------------------------------


@dataclass
class OIDCTokenProvider:
    """Provides access tokens with automatic refresh via the OAuth2 refresh_token grant.

    This is the core component for SDK-level token management. It:
    - Holds the current access + refresh tokens
    - Proactively refreshes the access token before it expires
    - Is thread-safe (uses a lock for concurrent access)
    - Optionally persists refreshed tokens via a callback
    """

    token_endpoint: str
    client_id: str
    tokens: TokenSet = field(default_factory=lambda: TokenSet(access_token=""), repr=False)
    refresh_margin_seconds: float = DEFAULT_REFRESH_MARGIN_SECONDS
    refresh_scope: str | None = None
    load_tokens: Callable[[], TokenSet | None] | None = None
    refresh_lock: Callable[[], AbstractContextManager[None]] | None = None
    on_tokens_refreshed: Callable[[TokenSet], None] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        with self._lock:
            if self.tokens.is_expired(self.refresh_margin_seconds):
                self._refresh()
            return self.tokens.access_token

    async def get_access_token_async(self) -> str:
        """Return a valid access token in async contexts.

        Runs refresh logic in a worker thread so token refresh does not block the
        event loop.
        """
        return await asyncio.to_thread(self.get_access_token)

    def reload_tokens(self) -> bool:
        """Reload tokens from a shared store, if configured."""
        with self._lock:
            return self._reload_tokens_from_source()

    def _reload_tokens_from_source(self) -> bool:
        if self.load_tokens is None:
            return False

        try:
            loaded_tokens = self.load_tokens()
        except Exception:
            logger.warning("Failed to reload shared tokens", exc_info=True)
            return False

        if loaded_tokens is None or loaded_tokens == self.tokens:
            return False

        self.tokens = loaded_tokens
        logger.debug("Reloaded shared tokens (expires_at=%s)", self.tokens.expires_at)
        return True

    def _refresh(self, *, force: bool = False) -> None:
        """Refresh the access token using the refresh_token grant."""
        lock_context = self.refresh_lock() if self.refresh_lock is not None else nullcontext()
        with lock_context:
            self._reload_tokens_from_source()
            if not force and not self.tokens.is_expired(self.refresh_margin_seconds):
                return

            if not self.tokens.refresh_token:
                raise RuntimeError(
                    "Access token has expired and no refresh token is available. "
                    "Re-authenticate with `nemo auth login` to obtain new tokens."
                )

            logger.debug("Refreshing access token via %s", self.token_endpoint)

            token_data: dict
            try:
                token_data = refresh_token_grant(
                    token_endpoint=self.token_endpoint,
                    client_id=self.client_id,
                    refresh_token=self.tokens.refresh_token,
                    scope=self.refresh_scope,
                )
            except TokenRefreshError as exc:
                if exc.error != "invalid_grant":
                    raise

                if not self._reload_tokens_from_source():
                    raise

                if not force and not self.tokens.is_expired(self.refresh_margin_seconds):
                    logger.debug("Recovered from invalid_grant with shared tokens")
                    return

                if not self.tokens.refresh_token:
                    raise RuntimeError(
                        "Access token has expired and no refresh token is available. "
                        "Re-authenticate with `nemo auth login` to obtain new tokens."
                    )

                token_data = refresh_token_grant(
                    token_endpoint=self.token_endpoint,
                    client_id=self.client_id,
                    refresh_token=self.tokens.refresh_token,
                    scope=self.refresh_scope,
                )

            new_access_token = token_data["access_token"]
            # The IdP may rotate the refresh token.
            old_refresh_token = self.tokens.refresh_token
            new_refresh_token = token_data.get("refresh_token", old_refresh_token)
            refresh_token_rotated = new_refresh_token != old_refresh_token

            self.tokens = TokenSet.from_access_token(
                new_access_token, new_refresh_token, expires_in=token_data.get("expires_in")
            )
            logger.debug("Access token refreshed successfully (expires_at=%s)", self.tokens.expires_at)

            if self.on_tokens_refreshed:
                try:
                    self.on_tokens_refreshed(self.tokens)
                except Exception:
                    if refresh_token_rotated:
                        # The IdP rotated the refresh token but we failed to
                        # persist it. The old refresh token is now invalid, so
                        # swallowing this would silently lose the user's session.
                        raise
                    logger.warning("Failed to persist refreshed tokens", exc_info=True)

    def force_refresh(self) -> str:
        """Force a token refresh regardless of expiry. Returns the new access token."""
        with self._lock:
            self._refresh(force=True)
            return self.tokens.access_token
