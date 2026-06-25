# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Authentication support for NemoClient.

Provides:

- :class:`TokenProvider` / :class:`AsyncTokenProvider` — protocols for any
  object that can supply an access token.
- :class:`StaticToken` — wraps a plain token string.
- :class:`OIDCTokenProvider` — thread-safe OIDC token refresh.
- OIDC provider factory helpers used by ``NemoClient.from_config()``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class TokenProvider(Protocol):
    """Sync protocol for objects that can supply an access token."""

    def get_access_token(self) -> str: ...


@runtime_checkable
class AsyncTokenProvider(Protocol):
    """Async protocol for objects that can supply an access token."""

    async def get_access_token(self) -> str: ...


# ---------------------------------------------------------------------------
# StaticToken
# ---------------------------------------------------------------------------


class StaticToken:
    """Wraps a plain token string into a TokenProvider."""

    def __init__(self, token: str) -> None:
        self._token = token

    def get_access_token(self) -> str:
        return self._token

    async def get_access_token_async(self) -> str:
        return self._token


# ---------------------------------------------------------------------------
# Auth errors
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Authentication-related error."""


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


def refresh_token_grant(
    token_endpoint: str,
    client_id: str,
    refresh_token: str,
    *,
    scope: str | None = None,
    timeout: float = 30.0,
) -> dict:
    """Execute OAuth refresh_token grant and return token response JSON."""
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

    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None

    @staticmethod
    def from_access_token(
        access_token: str,
        refresh_token: str | None = None,
    ) -> TokenSet:
        """Create a TokenSet, extracting expiry from the JWT's ``exp`` claim."""
        expires_at = None
        claims = decode_jwt_claims(access_token)
        if claims:
            expires_at = claims.get("exp")
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
    tokens: TokenSet = field(default_factory=lambda: TokenSet(access_token=""))
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
            new_refresh_token = token_data.get("refresh_token", self.tokens.refresh_token)

            self.tokens = TokenSet.from_access_token(new_access_token, new_refresh_token)
            logger.debug("Access token refreshed successfully (expires_at=%s)", self.tokens.expires_at)

            if self.on_tokens_refreshed:
                try:
                    self.on_tokens_refreshed(self.tokens)
                except Exception:
                    logger.warning("Failed to persist refreshed tokens", exc_info=True)

    def force_refresh(self) -> str:
        """Force a token refresh regardless of expiry. Returns the new access token."""
        with self._lock:
            self._refresh(force=True)
            return self.tokens.access_token


# ---------------------------------------------------------------------------
# OIDC provider factory (used by NemoClient.from_config)
# ---------------------------------------------------------------------------

# Guards _TOKEN_PROVIDER_CACHE; acquired only during dict lookup/insert (fast).
_TOKEN_PROVIDER_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class _ProviderCacheKey:
    """Composite key for the provider cache."""

    config_path: Path
    context_name: str
    token_endpoint: str
    client_id: str
    refresh_scope: str | None


# Process-wide cache: (config_path, context) → shared OIDCTokenProvider.
_TOKEN_PROVIDER_CACHE: dict[_ProviderCacheKey, OIDCTokenProvider] = {}


def _make_config_persister(context_name: str, config_path: Path | None = None) -> Callable[[TokenSet], None]:
    """Create an ``on_tokens_refreshed`` callback that writes new tokens to the config file."""

    def persist(tokens: TokenSet) -> None:
        from nemo_platform_plugin.client.config.config import Config
        from nemo_platform_plugin.client.config.models import ConfigParams

        params: ConfigParams = {"access_token": tokens.access_token}
        if tokens.refresh_token:
            params["refresh_token"] = tokens.refresh_token
        Config.write(params, context_name=context_name, config_path=config_path)
        logger.debug("Persisted refreshed tokens to nmp config (context=%s)", context_name)

    return persist


def _make_config_token_loader(context_name: str, config_path: Path) -> Callable[[], TokenSet | None]:
    """Create a ``load_tokens`` callback that re-reads tokens from the config file."""

    def load_tokens() -> TokenSet | None:
        from nemo_platform_plugin.client.config.config import Config
        from nemo_platform_plugin.client.config.models import ConfigParams, OAuthUser

        overrides: ConfigParams = {"current_context": context_name}
        try:
            config = Config.load(config_path=config_path, overrides=overrides)
            resolved = config.resolve()
        except Exception:
            logger.debug("Failed to reload tokens from nmp config (context=%s)", context_name, exc_info=True)
            return None

        if not isinstance(resolved.user, OAuthUser):
            return None

        return TokenSet.from_access_token(
            resolved.user.token.get_secret_value(),
            resolved.user.refresh_token.get_secret_value() if resolved.user.refresh_token else None,
        )

    return load_tokens


def _build_refresh_lock_path(config_path: Path, context_name: str) -> Path:
    safe_context = context_name.replace(os.sep, "_")
    if os.altsep:
        safe_context = safe_context.replace(os.altsep, "_")
    return config_path.with_name(f"{config_path.name}.{safe_context}.oauth-refresh.lock")


def _make_refresh_lock(config_path: Path, context_name: str) -> Callable[[], AbstractContextManager[None]]:
    """Create a cross-process file lock for serializing token refreshes."""
    lock_path = _build_refresh_lock_path(config_path, context_name)

    @contextmanager
    def refresh_lock():
        try:
            import fcntl
        except ImportError:
            # Windows: no fcntl — skip cross-process locking.
            yield
            return

        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return refresh_lock


def _normalize_config_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _get_or_create_provider(
    key: _ProviderCacheKey,
    create_provider: Callable[[], OIDCTokenProvider],
) -> OIDCTokenProvider:
    """Return the cached provider for *key*, or create and cache a new one."""
    with _TOKEN_PROVIDER_CACHE_LOCK:
        provider = _TOKEN_PROVIDER_CACHE.get(key)
        if provider is None:
            provider = create_provider()
            _TOKEN_PROVIDER_CACHE[key] = provider
            return provider

    # Provider already existed — reload tokens from disk in case another
    # process refreshed them since we last checked.
    provider.reload_tokens()
    return provider


def resolve_oidc_provider(
    *,
    base_url: str,
    context_name: str,
    access_token: str,
    refresh_token: str | None,
    config_exists: bool,
    config_path: Path,
    explicit_access_token: bool = False,
) -> OIDCTokenProvider:
    """Build or retrieve a cached OIDCTokenProvider for a resolved config context.

    This is the bridge between ``NemoClient.from_config()`` and the OIDC machinery.
    """
    oidc_config = _discover_oidc_client_settings(base_url)
    tokens = TokenSet.from_access_token(access_token, refresh_token)

    token_endpoint = oidc_config.token_endpoint or ""
    client_id = oidc_config.client_id or ""
    refresh_scope = build_effective_scope(oidc_config.default_scopes, oidc_config.scope_prefix)

    # Only share the provider (and enable persistence/locking) when reading
    # from an actual config file.  If the caller passed an explicit
    # access_token, they own the token lifecycle.
    share_provider = config_exists and not explicit_access_token

    if share_provider:
        normalized_config_path = _normalize_config_path(config_path)
        provider_key = _ProviderCacheKey(
            config_path=normalized_config_path,
            context_name=context_name,
            token_endpoint=token_endpoint,
            client_id=client_id,
            refresh_scope=refresh_scope,
        )
        on_refreshed = _make_config_persister(context_name, config_path)
        load_tokens_cb = _make_config_token_loader(context_name, config_path)
        refresh_lock = _make_refresh_lock(config_path, context_name)

        return _get_or_create_provider(
            provider_key,
            lambda: OIDCTokenProvider(
                token_endpoint=token_endpoint,
                client_id=client_id,
                tokens=tokens,
                refresh_margin_seconds=DEFAULT_REFRESH_MARGIN_SECONDS,
                refresh_scope=refresh_scope,
                load_tokens=load_tokens_cb,
                refresh_lock=refresh_lock,
                on_tokens_refreshed=on_refreshed,
            ),
        )

    # Ephemeral provider: no persistence, no file locking, no caching.
    return OIDCTokenProvider(
        token_endpoint=token_endpoint,
        client_id=client_id,
        tokens=tokens,
        refresh_margin_seconds=DEFAULT_REFRESH_MARGIN_SECONDS,
        refresh_scope=refresh_scope,
    )
