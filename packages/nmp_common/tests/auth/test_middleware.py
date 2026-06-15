# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for authorization middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nmp.common.auth.client import AuthClient
from nmp.common.auth.jwt import TokenClaims, UnsignedJWTRejectedError
from nmp.common.auth.middleware import HEALTH_ENDPOINTS, PUBLIC_GET_PATHS, AuthorizationMiddleware
from nmp.common.auth.models import Principal
from nmp.common.config import AuthConfig, Configuration
from nmp.common.config.base import OIDCConfig


@pytest.fixture(autouse=True)
def _cleanup_config_overrides():
    """Clean up Configuration overrides set by create_test_app to prevent leaking to other tests."""
    yield
    Configuration.clear_override(AuthConfig)


@pytest.fixture
def oidc_config():
    """Create an OIDC config for testing."""
    return OIDCConfig(
        enabled=True,
        issuer="https://sso.example.com",
        client_id="test-client",
    )


@pytest.fixture
def auth_config_enabled(oidc_config):
    """Create an AuthConfig with auth and OIDC enabled."""
    return AuthConfig(
        enabled=True,
        policy_decision_point_base_url="http://localhost:8181",
        oidc=oidc_config,
    )


@pytest.fixture
def auth_config_disabled():
    """Create an AuthConfig with auth disabled."""
    return AuthConfig(
        enabled=False,
        policy_decision_point_base_url="http://localhost:8181",
    )


@pytest.fixture
def auth_config_oidc_disabled():
    """Create an AuthConfig with auth enabled but OIDC disabled."""
    return AuthConfig(
        enabled=True,
        policy_decision_point_base_url="http://localhost:8181",
        oidc=OIDCConfig(enabled=False),
    )


def create_test_app(auth_config: AuthConfig) -> FastAPI:
    """Create a test FastAPI app with auth middleware."""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok"}

    @app.get("/health")
    async def health_endpoint():
        return {"status": "healthy"}

    @app.get("/apis/auth/discovery")
    async def discovery_endpoint():
        return {"auth_enabled": True}

    @app.get("/apis/files/v2/hf/{workspace}/{name}/resolve/{revision}/{path:path}")
    async def hf_download_endpoint(workspace: str, name: str, revision: str, path: str):
        return {"workspace": workspace, "name": name, "path": path}

    Configuration.set_override(auth_config)
    app.add_middleware(AuthorizationMiddleware, service_name="test-service")

    return app


def create_test_app_with_platform_routes(auth_config: AuthConfig) -> FastAPI:
    """Test app including Entities and IAM routes used by internal-route tests."""
    app = create_test_app(auth_config)

    @app.get("/apis/entities/v2/workspaces")
    async def list_workspaces():
        return {"data": []}

    @app.post("/apis/entities/v2/workspaces")
    async def create_workspace():
        return {"data": {"name": "new-ws"}}

    @app.api_route("/apis/entities/v2/workspaces/{name}", methods=["GET", "PUT", "DELETE"])
    async def workspace_by_name(name: str):
        return {"name": name}

    @app.get("/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}")
    async def nested_entities(workspace: str, entity_type: str):
        return {"workspace": workspace, "entity_type": entity_type}

    @app.get("/apis/auth/v2/iam/role-bindings")
    async def iam_list():
        return {"data": []}

    return app


class TestHealthEndpointsBypass:
    """Tests for health endpoints bypassing authentication."""

    def test_health_endpoints_in_bypass_list(self):
        """Verify that health endpoints are in the bypass list."""
        assert "/status" in HEALTH_ENDPOINTS
        assert "/health/live" in HEALTH_ENDPOINTS
        assert "/health/ready" in HEALTH_ENDPOINTS
        assert "/metrics" in HEALTH_ENDPOINTS
        assert "/apis/auth/discovery" in HEALTH_ENDPOINTS

    def test_root_path_in_public_get_paths(self):
        assert "/" in PUBLIC_GET_PATHS

    @pytest.mark.parametrize("method", ["get", "head"])
    def test_root_bypasses_auth_for_safe_methods(self, auth_config_enabled, method):
        app = FastAPI()

        @app.api_route("/", methods=["GET", "HEAD"])
        async def root_handler():
            return {"status": "ok"}

        Configuration.set_override(auth_config_enabled)
        app.add_middleware(AuthorizationMiddleware, service_name="test-service")

        client = TestClient(app)
        with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
            mock_authorize.return_value = MagicMock(allowed=False)
            response = getattr(client, method)("/")

        assert response.status_code == 200
        mock_authorize.assert_not_called()


class TestBearerTokenAuth:
    """Tests for Bearer token authentication in middleware."""

    def test_bearer_token_oidc_not_configured(self, auth_config_oidc_disabled):
        """Test that Bearer token auth fails when OIDC is not configured."""
        app = create_test_app(auth_config_oidc_disabled)
        client = TestClient(app, raise_server_exceptions=False)

        # Mock PDP to allow auth check to pass for the test path
        with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
            mock_authorize.return_value = MagicMock(allowed=False)

            response = client.get(
                "/test",
                headers={"Authorization": "Bearer some-token"},
            )

            # Should return 401 because OIDC is not configured
            assert response.status_code == 401
            assert "Bearer token authentication not configured" in response.json()["detail"]
            mock_authorize.assert_not_called()

    def test_bearer_token_unsigned_jwt_accepted_when_allowed(self):
        """Test that unsigned JWTs are accepted when allow_unsigned_jwt is true, even without OIDC."""
        config = AuthConfig(
            enabled=True,
            allow_unsigned_jwt=True,
            policy_decision_point_base_url="http://localhost:8181",
            oidc=OIDCConfig(enabled=False),
        )
        app = create_test_app(config)
        client = TestClient(app, raise_server_exceptions=False)

        valid_claims = TokenClaims(
            subject="admin@example.com",
            email="admin@example.com",
            groups=[],
            scopes=[],
            raw_claims={},
        )

        with patch("nmp.common.auth.jwt.JWTValidator.validate_token") as mock_validate:
            mock_validate.return_value = valid_claims

            with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
                mock_authorize.return_value = MagicMock(allowed=True)

                response = client.get(
                    "/test",
                    headers={"Authorization": "Bearer unsigned-jwt-token"},
                )

                assert response.status_code == 200

    def test_bearer_token_invalid_token(self, auth_config_enabled):
        """Test that invalid Bearer tokens return 401."""
        app = create_test_app(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("nmp.common.auth.jwt.JWTValidator.validate_token") as mock_validate:
            mock_validate.return_value = None  # Invalid token

            response = client.get(
                "/test",
                headers={"Authorization": "Bearer invalid-token"},
            )

            assert response.status_code == 401
            assert "Invalid or expired token" in response.json()["detail"]

    def test_bearer_token_not_validated_when_auth_disabled(self):
        """Auth disabled allows requests even when local unsigned-JWT support is enabled."""
        config = AuthConfig(
            enabled=False,
            allow_unsigned_jwt=True,
            policy_decision_point_base_url="http://localhost:8181",
            oidc=OIDCConfig(enabled=False),
        )
        app = create_test_app(config)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("nmp.common.auth.jwt.JWTValidator.validate_token") as mock_validate:
            mock_validate.return_value = None

            response = client.get(
                "/test",
                headers={"Authorization": "Bearer not-used"},
            )

            assert response.status_code == 200
            mock_validate.assert_not_called()

    def test_bearer_token_unsigned_token_rejected_message(self, auth_config_enabled):
        """Test that unsigned JWT rejection returns actionable 401 detail."""
        app = create_test_app(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("nmp.common.auth.jwt.JWTValidator.validate_token") as mock_validate:
            mock_validate.side_effect = UnsignedJWTRejectedError(
                "Unsigned JWTs are not accepted. Set auth.allow_unsigned_jwt=true for local development."
            )

            response = client.get(
                "/test",
                headers={"Authorization": "Bearer unsigned-token"},
            )

            assert response.status_code == 401
            assert "Unsigned JWTs are not accepted" in response.json()["detail"]

    def test_bearer_token_valid_token_auth_disabled(self, auth_config_disabled):
        """Test Bearer token with valid token when auth is disabled."""
        auth_config_disabled.oidc = OIDCConfig(
            enabled=True,
            issuer="https://sso.example.com",
            client_id="test-client",
        )
        app = create_test_app(auth_config_disabled)
        client = TestClient(app, raise_server_exceptions=False)

        valid_claims = TokenClaims(
            subject="user@example.com",
            email="user@example.com",
            groups=["users"],
            scopes=["openid"],
            raw_claims={},
        )

        with patch("nmp.common.auth.jwt.JWTValidator.validate_token") as mock_validate:
            mock_validate.return_value = valid_claims

            response = client.get(
                "/test",
                headers={"Authorization": "Bearer valid-token"},
            )

            # Should succeed because auth is disabled
            assert response.status_code == 200

    def test_bearer_token_valid_token_pdp_allows(self, auth_config_enabled):
        """Test Bearer token with valid token when PDP allows."""
        app = create_test_app(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)

        valid_claims = TokenClaims(
            subject="user@example.com",
            email="user@example.com",
            groups=["users"],
            scopes=["openid"],
            raw_claims={},
        )

        with patch("nmp.common.auth.jwt.JWTValidator.validate_token") as mock_validate:
            mock_validate.return_value = valid_claims

            with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
                mock_authorize.return_value = MagicMock(allowed=True)

                response = client.get(
                    "/test",
                    headers={"Authorization": "Bearer valid-token"},
                )

                assert response.status_code == 200

    def test_bearer_token_valid_token_pdp_denies(self, auth_config_enabled):
        """Test Bearer token with valid token when PDP denies."""
        app = create_test_app(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)

        valid_claims = TokenClaims(
            subject="user@example.com",
            email="user@example.com",
            groups=["users"],
            scopes=["openid"],
            raw_claims={},
        )

        with patch("nmp.common.auth.jwt.JWTValidator.validate_token") as mock_validate:
            mock_validate.return_value = valid_claims

            with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
                mock_authorize.return_value = MagicMock(allowed=False)

                response = client.get(
                    "/test",
                    headers={"Authorization": "Bearer valid-token"},
                )

                assert response.status_code == 403


class TestPrincipalHeadersAuth:
    """Tests for X-NMP-Principal-* header authentication."""

    def test_principal_headers_with_principal_id(self, auth_config_enabled):
        """Principal is taken from X-NMP-Principal-Id when auth is enabled."""
        app = create_test_app(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
            mock_authorize.return_value = MagicMock(allowed=True)

            response = client.get(
                "/test",
                headers={"X-NMP-Principal-Id": "user@example.com"},
            )

            assert response.status_code == 200

    def test_principal_headers_auth_disabled(self, auth_config_disabled):
        """X-NMP-Principal-* headers still set principal when auth is disabled."""
        app = create_test_app(auth_config_disabled)
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/test",
            headers={"X-NMP-Principal-Id": "user@example.com"},
        )

        # Should succeed because auth is disabled
        assert response.status_code == 200


class TestServicePrincipalAuth:
    """Tests for service principal authentication."""

    def test_service_principal_uses_pdp(self, auth_config_enabled):
        """Service principals are authorized via PDP (same path as X-NMP-Principal-* users)."""
        app = create_test_app(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
            mock_authorize.return_value = MagicMock(allowed=True)

            response = client.get(
                "/test",
                headers={"X-NMP-Principal-Id": "service:my-service"},
            )

            assert response.status_code == 200
            mock_authorize.assert_called_once()


class TestHfEndpointAuth:
    """Tests for HuggingFace-compatible endpoint authentication.

    HF endpoints accept service principal tokens via Bearer header (HF_TOKEN),
    allowing huggingface-hub clients to authenticate with HF_TOKEN=service:<name>.
    """

    @pytest.mark.parametrize(
        "token,expected_status",
        [
            ("service:nim", 200),
            ("service:customizer", 200),
            ("invalid-token", 401),
        ],
    )
    def test_hf_endpoint_bearer_token(self, auth_config_enabled, token, expected_status):
        """HF endpoints accept service:* Bearer tokens, reject invalid tokens."""
        app = create_test_app(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)

        with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
            mock_authorize.return_value = MagicMock(allowed=expected_status == 200)

            response = client.get(
                "/apis/files/v2/hf/my-workspace/my-fileset/resolve/main/model.bin",
                headers={"Authorization": f"Bearer {token}"},
            )

            assert response.status_code == expected_status
            if expected_status == 200:
                mock_authorize.assert_called_once()


class TestInternalServiceOnlyRoutes:
    """IAM role-bindings and nested Entities APIs require service principals."""

    def test_iam_role_bindings_forbidden_for_user_principal(self, auth_config_enabled):
        app = create_test_app_with_platform_routes(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
            mock_authorize.return_value = MagicMock(allowed=False)
            response = client.get(
                "/apis/auth/v2/iam/role-bindings",
                headers={"X-NMP-Principal-Id": "user@example.com"},
            )
        assert response.status_code == 403

    def test_iam_role_bindings_allowed_for_service_principal(self, auth_config_enabled):
        app = create_test_app_with_platform_routes(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
            mock_authorize.return_value = MagicMock(allowed=True)
            response = client.get(
                "/apis/auth/v2/iam/role-bindings",
                headers={"X-NMP-Principal-Id": "service:integration-test"},
            )
        assert response.status_code == 200

    def test_nested_entities_forbidden_for_user_principal(self, auth_config_enabled):
        app = create_test_app_with_platform_routes(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
            mock_authorize.return_value = MagicMock(allowed=False)
            response = client.get(
                "/apis/entities/v2/workspaces/ws1/entities/evaluation_config",
                headers={"X-NMP-Principal-Id": "user@example.com"},
            )
        assert response.status_code == 403

    def test_workspace_list_allowed_for_user_principal(self, auth_config_enabled):
        app = create_test_app_with_platform_routes(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("nmp.common.auth.client.AuthClient.authorize_request") as mock_authorize:
            mock_authorize.return_value = MagicMock(allowed=True)
            response = client.get(
                "/apis/entities/v2/workspaces",
                headers={"X-NMP-Principal-Id": "user@example.com"},
            )
        assert response.status_code == 200

    def test_internal_routes_skipped_when_auth_disabled(self, auth_config_disabled):
        app = create_test_app_with_platform_routes(auth_config_disabled)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/apis/auth/v2/iam/role-bindings",
            headers={"X-NMP-Principal-Id": "user@example.com"},
        )
        assert response.status_code == 200


class TestServicePrincipalDelegationMiddleware:
    """Service + on-behalf-of headers: AuthClient principal exposes effective delegate claims."""

    def test_principal_parsed_for_delegation_has_effective_delegate_attributes(self, auth_config_enabled):
        app = create_test_app(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)
        principal_seen: dict = {}

        original_from_headers = Principal.from_headers

        def capturing_from_headers(headers):
            p = original_from_headers(headers)
            principal_seen["p"] = p
            return p

        with (
            patch.object(Principal, "from_headers", side_effect=capturing_from_headers),
            patch.object(AuthClient, "authorize_request", new_callable=AsyncMock) as mock_authorize,
        ):
            mock_authorize.return_value = MagicMock(allowed=True)
            response = client.get(
                "/test",
                headers={
                    "x-nmp-principal-id": "service:worker",
                    "x-nmp-principal-on-behalf-of": "user@example.com",
                    "x-nmp-principal-on-behalf-of-groups": "ws-editors",
                    "x-nmp-principal-on-behalf-of-email": "user@example.com",
                },
            )

        assert response.status_code == 200
        p = principal_seen["p"]
        assert p is not None
        assert p.id == "service:worker"
        assert p.on_behalf_of == "user@example.com"
        assert p.effective_groups == ["ws-editors"]
        assert p.effective_email == "user@example.com"

    def test_service_delegation_returns_403_when_pdp_denies(self, auth_config_enabled):
        app = create_test_app(auth_config_enabled)
        client = TestClient(app, raise_server_exceptions=False)

        mock_authorize = AsyncMock(return_value=MagicMock(allowed=False))

        with patch.object(AuthClient, "authorize_request", mock_authorize):
            response = client.get(
                "/test",
                headers={
                    "x-nmp-principal-id": "service:worker",
                    "x-nmp-principal-on-behalf-of": "user@example.com",
                    "x-nmp-principal-on-behalf-of-groups": "no-access",
                },
            )

        assert response.status_code == 403
