# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for NemoClient first-class auth support (AIRCORE-828)."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import httpx
import pytest
import respx
import yaml
from nemo_platform_plugin.client.auth import (
    StaticToken,
    TokenProvider,
)
from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.config.config import Config
from nemo_platform_plugin.client.config.models import (
    NoAuthUser,
    OAuthUser,
)
from nemo_platform_plugin.client.oidc import (
    OIDCTokenProvider,
    TokenSet,
    generate_unsigned_jwt,
)
from nemo_platform_plugin.client_provider import (
    get_async_nemo_client,
    get_nemo_client,
)

# ---------------------------------------------------------------------------
# StaticToken
# ---------------------------------------------------------------------------


class TestStaticToken:
    def test_get_access_token(self):
        provider = StaticToken("my-token")
        assert provider.get_access_token() == "my-token"

    def test_satisfies_protocol(self):
        provider = StaticToken("t")
        assert isinstance(provider, TokenProvider)

    def test_async_get_access_token(self):
        provider = StaticToken("my-token")
        result = asyncio.run(provider.get_access_token_async())
        assert result == "my-token"


# ---------------------------------------------------------------------------
# NemoClient auth parameter
# ---------------------------------------------------------------------------


class TestNemoClientAuth:
    @respx.mock
    def test_string_auth_sets_bearer_header(self):
        """NemoClient(auth='token') sets Authorization header on requests."""
        route = respx.get("http://localhost:8080/test").mock(return_value=httpx.Response(200, json={"ok": True}))
        client = NemoClient(base_url="http://localhost:8080", auth="my-secret-token")

        from nemo_platform_plugin.client.types import PreparedRequest

        req = PreparedRequest(
            method="GET", path_template="/test", path_params={}, content=None, content_type=None, response_type=None
        )
        client.send(req)

        assert route.called
        assert route.calls[0].request.headers["Authorization"] == "Bearer my-secret-token"

    @respx.mock
    def test_custom_provider_called_per_request(self):
        """NemoClient(auth=CustomProvider()) calls get_access_token() per request."""
        route = respx.get("http://localhost:8080/test").mock(return_value=httpx.Response(200, json={"ok": True}))

        call_count = 0

        class CountingProvider:
            def get_access_token(self) -> str:
                nonlocal call_count
                call_count += 1
                return f"token-{call_count}"

        client = NemoClient(base_url="http://localhost:8080", auth=CountingProvider())

        from nemo_platform_plugin.client.types import PreparedRequest

        req = PreparedRequest(
            method="GET", path_template="/test", path_params={}, content=None, content_type=None, response_type=None
        )
        client.send(req)
        client.send(req)

        assert route.calls[0].request.headers["Authorization"] == "Bearer token-1"
        assert route.calls[1].request.headers["Authorization"] == "Bearer token-2"
        assert call_count == 2

    @respx.mock
    def test_no_auth_no_header(self):
        """NemoClient without auth does not add Authorization header."""
        route = respx.get("http://localhost:8080/test").mock(return_value=httpx.Response(200, json={"ok": True}))
        client = NemoClient(base_url="http://localhost:8080")

        from nemo_platform_plugin.client.types import PreparedRequest

        req = PreparedRequest(
            method="GET", path_template="/test", path_params={}, content=None, content_type=None, response_type=None
        )
        client.send(req)

        assert route.called
        assert "Authorization" not in route.calls[0].request.headers


# ---------------------------------------------------------------------------
# AsyncNemoClient auth parameter
# ---------------------------------------------------------------------------


class TestAsyncNemoClientAuth:
    @respx.mock
    def test_async_provider_called(self):
        """AsyncNemoClient(auth=AsyncProvider()) calls async get_access_token()."""
        route = respx.get("http://localhost:8080/test").mock(return_value=httpx.Response(200, json={"ok": True}))

        class AsyncProvider:
            async def get_access_token(self) -> str:
                return "async-token"

        client = AsyncNemoClient(base_url="http://localhost:8080", auth=AsyncProvider())

        from nemo_platform_plugin.client.types import PreparedRequest

        req = PreparedRequest(
            method="GET", path_template="/test", path_params={}, content=None, content_type=None, response_type=None
        )

        asyncio.run(client.send(req))

        assert route.called
        assert route.calls[0].request.headers["Authorization"] == "Bearer async-token"

    @respx.mock
    def test_sync_provider_works_in_async_client(self):
        """AsyncNemoClient accepts a sync TokenProvider too."""
        route = respx.get("http://localhost:8080/test").mock(return_value=httpx.Response(200, json={"ok": True}))
        client = AsyncNemoClient(base_url="http://localhost:8080", auth="sync-token")

        from nemo_platform_plugin.client.types import PreparedRequest

        req = PreparedRequest(
            method="GET", path_template="/test", path_params={}, content=None, content_type=None, response_type=None
        )

        asyncio.run(client.send(req))

        assert route.called
        assert route.calls[0].request.headers["Authorization"] == "Bearer sync-token"


# ---------------------------------------------------------------------------
# OIDCTokenProvider
# ---------------------------------------------------------------------------


def _make_jwt(exp: float | None = None, sub: str = "user") -> str:
    """Create a minimal unsigned JWT for testing."""
    return generate_unsigned_jwt(
        principal_id=sub,
        expires_in_seconds=int(exp - time.time()) if exp else 3600,
    )


class TestOIDCTokenProvider:
    def test_returns_token_when_not_expired(self):
        token = _make_jwt(exp=time.time() + 3600)
        provider = OIDCTokenProvider(
            token_endpoint="https://idp/token",
            client_id="client",
            tokens=TokenSet.from_access_token(token),
        )
        assert provider.get_access_token() == token

    def test_refreshes_when_expired(self):
        expired_token = _make_jwt(exp=time.time() - 100)
        new_token = _make_jwt(exp=time.time() + 3600)

        provider = OIDCTokenProvider(
            token_endpoint="https://idp/token",
            client_id="client",
            tokens=TokenSet(access_token=expired_token, refresh_token="refresh-me", expires_at=time.time() - 100),
        )

        with patch("nemo_platform_plugin.client.oidc.refresh_token_grant") as mock_grant:
            mock_grant.return_value = {"access_token": new_token}
            result = provider.get_access_token()

        assert result == new_token
        mock_grant.assert_called_once()

    def test_persists_rotated_tokens(self):
        expired_token = _make_jwt(exp=time.time() - 100)
        new_token = _make_jwt(exp=time.time() + 3600)
        persisted = []

        provider = OIDCTokenProvider(
            token_endpoint="https://idp/token",
            client_id="client",
            tokens=TokenSet(access_token=expired_token, refresh_token="old-refresh", expires_at=time.time() - 100),
            on_tokens_refreshed=lambda ts: persisted.append(ts),
        )

        with patch("nemo_platform_plugin.client.oidc.refresh_token_grant") as mock_grant:
            mock_grant.return_value = {"access_token": new_token, "refresh_token": "new-refresh"}
            provider.get_access_token()

        assert len(persisted) == 1
        assert persisted[0].access_token == new_token
        assert persisted[0].refresh_token == "new-refresh"

    def test_raises_when_no_refresh_token(self):
        provider = OIDCTokenProvider(
            token_endpoint="https://idp/token",
            client_id="client",
            tokens=TokenSet(access_token="expired", expires_at=time.time() - 100),
        )
        with pytest.raises(RuntimeError, match="no refresh token"):
            provider.get_access_token()

    def test_invalid_grant_recovery_with_shared_tokens(self):
        """On invalid_grant, reload tokens from shared store and retry."""
        expired_token = _make_jwt(exp=time.time() - 100)
        fresh_token = _make_jwt(exp=time.time() + 3600)

        from nemo_platform_plugin.client.oidc import TokenRefreshError

        provider = OIDCTokenProvider(
            token_endpoint="https://idp/token",
            client_id="client",
            tokens=TokenSet(access_token=expired_token, refresh_token="stale-refresh", expires_at=time.time() - 100),
            load_tokens=lambda: TokenSet(
                access_token=fresh_token, refresh_token="fresh-refresh", expires_at=time.time() + 3600
            ),
        )

        with patch("nemo_platform_plugin.client.oidc.refresh_token_grant") as mock_grant:
            mock_grant.side_effect = TokenRefreshError(error="invalid_grant", error_description="token revoked")
            result = provider.get_access_token()

        # Should have recovered by reloading fresh tokens from the shared store
        assert result == fresh_token


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_load_and_resolve(self, tmp_path):
        config_data = {
            "current_context": "test",
            "clusters": [{"name": "test-cluster", "base_url": "http://localhost:9090"}],
            "users": [{"name": "test-user", "type": "oauth", "token": "my-token"}],
            "contexts": [{"name": "test", "cluster": "test-cluster", "user": "test-user", "workspace": "ws1"}],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump(config_data))

        config = Config.load(config_path=config_file)
        ctx = config.resolve()

        assert ctx.context_name == "test"
        assert str(ctx.cluster.base_url).rstrip("/") == "http://localhost:9090"
        assert ctx.workspace == "ws1"
        assert isinstance(ctx.user, OAuthUser)
        assert ctx.user.token.get_secret_value() == "my-token"

    def test_load_nonexistent_explicit_path_raises(self, tmp_path):
        missing = tmp_path / "does-not-exist.yaml"
        with pytest.raises(FileNotFoundError):
            Config.load(config_path=missing)

    def test_write_then_read_round_trip(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        Config.write(
            {"base_url": "http://localhost:9999", "access_token": "round-trip-token"},
            context_name="rt",
            config_path=config_file,
            set_current_on_create=True,
        )

        config = Config.load(config_path=config_file)
        ctx = config.resolve()
        assert ctx.context_name == "rt"
        assert str(ctx.cluster.base_url).rstrip("/") == "http://localhost:9999"
        assert isinstance(ctx.user, OAuthUser)
        assert ctx.user.token.get_secret_value() == "round-trip-token"

    def test_migrate_legacy_api_key_to_oauth(self, tmp_path):
        """Legacy api-key users are migrated to oauth on load."""
        config_data = {
            "current_context": "test",
            "clusters": [{"name": "test-cluster", "base_url": "http://localhost:9090"}],
            "users": [{"name": "test-user", "type": "api-key", "api_key": "my-api-key"}],
            "contexts": [{"name": "test", "cluster": "test-cluster", "user": "test-user"}],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump(config_data))

        config = Config.load(config_path=config_file)
        ctx = config.resolve()
        assert isinstance(ctx.user, OAuthUser)
        assert ctx.user.token.get_secret_value() == "my-api-key"

    def test_migrate_legacy_api_key_empty_becomes_no_auth(self, tmp_path):
        """Legacy api-key users with empty keys become no-auth."""
        config_data = {
            "current_context": "test",
            "clusters": [{"name": "test-cluster", "base_url": "http://localhost:9090"}],
            "users": [{"name": "test-user", "type": "api-key", "api_key": ""}],
            "contexts": [{"name": "test", "cluster": "test-cluster", "user": "test-user"}],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump(config_data))

        config = Config.load(config_path=config_file)
        ctx = config.resolve()
        assert isinstance(ctx.user, NoAuthUser)

    def test_resolve_no_auth_user(self, tmp_path):
        config_data = {
            "current_context": "test",
            "clusters": [{"name": "test-cluster", "base_url": "http://localhost:9090"}],
            "users": [{"name": "test-user", "type": "no-auth"}],
            "contexts": [{"name": "test", "cluster": "test-cluster", "user": "test-user"}],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump(config_data))

        config = Config.load(config_path=config_file)
        ctx = config.resolve()

        assert isinstance(ctx.user, NoAuthUser)


# ---------------------------------------------------------------------------
# NemoClient.from_config
# ---------------------------------------------------------------------------


class TestFromConfig:
    def test_from_config_with_oauth(self, tmp_path):
        token = _make_jwt()
        config_data = {
            "current_context": "test",
            "clusters": [{"name": "test-cluster", "base_url": "http://localhost:9090"}],
            "users": [{"name": "test-user", "type": "oauth", "token": token}],
            "contexts": [{"name": "test", "cluster": "test-cluster", "user": "test-user"}],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump(config_data))

        with patch("nemo_platform_plugin.client.oidc._discover_oidc_client_settings") as mock_discover:
            from nemo_platform_plugin.client.oidc import NMPOIDCConfig

            mock_discover.return_value = NMPOIDCConfig(
                auth_enabled=True,
                client_id="test-client",
                token_endpoint="https://idp/token",
            )
            client = NemoClient.from_config(config_path=config_file)

        assert client.base_url == "http://localhost:9090"
        assert client._auth is not None

    def test_from_config_with_no_auth(self, tmp_path):
        config_data = {
            "current_context": "test",
            "clusters": [{"name": "test-cluster", "base_url": "http://localhost:9090"}],
            "users": [{"name": "test-user", "type": "no-auth"}],
            "contexts": [{"name": "test", "cluster": "test-cluster", "user": "test-user"}],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump(config_data))

        client = NemoClient.from_config(config_path=config_file)
        assert client.base_url == "http://localhost:9090"
        assert client._auth is None

    def test_from_config_selects_context(self, tmp_path):
        """from_config(context='staging') uses the staging context, not the default."""
        config_data = {
            "current_context": "prod",
            "clusters": [
                {"name": "prod-cluster", "base_url": "http://prod:8080"},
                {"name": "staging-cluster", "base_url": "http://staging:9090"},
            ],
            "users": [
                {"name": "prod-user", "type": "no-auth"},
                {"name": "staging-user", "type": "no-auth"},
            ],
            "contexts": [
                {"name": "prod", "cluster": "prod-cluster", "user": "prod-user"},
                {"name": "staging", "cluster": "staging-cluster", "user": "staging-user"},
            ],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump(config_data))

        client = NemoClient.from_config(context="staging", config_path=config_file)
        assert client.base_url == "http://staging:9090"

    def test_from_config_nonexistent_path_raises(self, tmp_path):
        missing = tmp_path / "nope.yaml"
        with pytest.raises(FileNotFoundError):
            NemoClient.from_config(config_path=missing)

    def test_async_from_config(self, tmp_path):
        config_data = {
            "current_context": "test",
            "clusters": [{"name": "test-cluster", "base_url": "http://localhost:9090"}],
            "users": [{"name": "test-user", "type": "no-auth"}],
            "contexts": [{"name": "test", "cluster": "test-cluster", "user": "test-user"}],
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump(config_data))

        client = AsyncNemoClient.from_config(config_path=config_file)
        assert isinstance(client, AsyncNemoClient)
        assert client.base_url == "http://localhost:9090"


# ---------------------------------------------------------------------------
# get_nemo_client / get_async_nemo_client
# ---------------------------------------------------------------------------


class TestGetNemoClient:
    def test_returns_sync_client(self):
        client = get_nemo_client(as_service="test-svc", internal=True)
        assert isinstance(client, NemoClient)

    def test_returns_async_client(self):
        client = get_async_nemo_client(as_service="test-svc")
        assert isinstance(client, AsyncNemoClient)


# ---------------------------------------------------------------------------
# Security: token repr and endpoint validation
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_token_set_repr_hides_tokens(self):
        ts = TokenSet(access_token="secret-access", refresh_token="secret-refresh", expires_at=123.0)
        r = repr(ts)
        assert "secret-access" not in r
        assert "secret-refresh" not in r
        assert "123.0" in r  # expires_at is still visible

    def test_oidc_provider_repr_hides_tokens(self):
        provider = OIDCTokenProvider(
            token_endpoint="https://idp/token",
            client_id="client",
            tokens=TokenSet(access_token="secret", expires_at=999.0),
        )
        r = repr(provider)
        assert "secret" not in r
        assert "idp" in r  # non-sensitive fields are visible

    def test_refresh_token_grant_rejects_http_endpoint(self):
        from nemo_platform_plugin.client.oidc import _validate_token_endpoint

        # HTTPS is fine
        _validate_token_endpoint("https://idp.example.com/token")
        # HTTP loopback is fine
        _validate_token_endpoint("http://localhost:8080/token")
        _validate_token_endpoint("http://127.0.0.1:8080/token")
        # HTTP non-loopback is rejected
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_token_endpoint("http://evil.example.com/token")
