# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for JWT validation."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt
import pytest
from nmp.common.auth.jwt import JWTValidator, TokenClaims, UnsignedJWTRejectedError
from nmp.common.config import AuthConfig
from nmp.common.config.base import OIDCConfig


@pytest.fixture
def oidc_config():
    """Create an OIDC config for testing."""
    return OIDCConfig(
        enabled=True,
        issuer="https://sso.example.com",
        client_id="test-client",
        audience="test-audience",
        email_claim="email",
        groups_claim="groups",
        subject_claim="sub",
    )


@pytest.fixture
def auth_config(oidc_config):
    """Create an AuthConfig with OIDC enabled."""
    return AuthConfig(
        enabled=True,
        policy_decision_point_base_url="http://localhost:8181",
        oidc=oidc_config,
    )


@pytest.fixture
def jwt_validator(auth_config):
    """Create a JWTValidator instance."""
    return JWTValidator(auth_config)


class TestTokenClaims:
    """Tests for the TokenClaims dataclass."""

    def test_token_claims_creation(self):
        """Test creating a TokenClaims instance."""
        claims = TokenClaims(
            subject="user123",
            email="user@example.com",
            groups=["admin", "users"],
            scopes=["openid", "profile"],
            raw_claims={"sub": "user123", "email": "user@example.com"},
        )

        assert claims.subject == "user123"
        assert claims.email == "user@example.com"
        assert claims.groups == ["admin", "users"]
        assert claims.scopes == ["openid", "profile"]
        assert claims.raw_claims == {"sub": "user123", "email": "user@example.com"}

    def test_token_claims_with_none_email(self):
        """Test TokenClaims with no email."""
        claims = TokenClaims(
            subject="user123",
            email=None,
            groups=[],
            scopes=[],
            raw_claims={"sub": "user123"},
        )

        assert claims.subject == "user123"
        assert claims.email is None


class TestOIDCConfigClaimDefaults:
    """Tests for issuer-based claim defaults."""

    def test_azure_issuer_keeps_generic_claim_defaults(self):
        """Microsoft issuer URL does not imply special claim names; set them explicitly in config."""
        config = OIDCConfig(
            enabled=True,
            issuer="https://login.microsoftonline.com/43083d15-7273-40c1-b7db-39efd9ccc17a/v2.0",
            client_id="test",
        )
        assert config.email_claim == "email"
        assert config.subject_claim == "sub"
        assert config.groups_claim == "groups"

    def test_non_azure_issuer_keeps_generic_defaults(self):
        """Non-Azure issuer keeps standard claim names."""
        config = OIDCConfig(
            enabled=True,
            issuer="https://sso.example.com",
            client_id="test",
        )
        assert config.email_claim == "email"
        assert config.subject_claim == "sub"
        assert config.groups_claim == "groups"


class TestJWTValidator:
    """Tests for the JWTValidator class."""

    @pytest.mark.asyncio
    async def test_discover_oidc_config(self, jwt_validator):
        """Test OIDC discovery document fetching."""
        discovery_doc = {
            "issuer": "https://sso.example.com",
            "jwks_uri": "https://sso.example.com/.well-known/jwks.json",
            "authorization_endpoint": "https://sso.example.com/authorize",
            "token_endpoint": "https://sso.example.com/token",
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = discovery_doc
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await jwt_validator._discover_oidc_config()

            assert result == discovery_doc
            mock_client.get.assert_called_once_with(
                "https://sso.example.com/.well-known/openid-configuration",
                timeout=10.0,
            )

    @pytest.mark.asyncio
    async def test_discover_oidc_config_caches_result(self, jwt_validator):
        """Test that discovery results are cached within TTL."""
        discovery_doc = {"issuer": "https://sso.example.com"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = discovery_doc
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            # Call twice
            result1 = await jwt_validator._discover_oidc_config()
            result2 = await jwt_validator._discover_oidc_config()

            # Should only have made one HTTP call
            assert mock_client.get.call_count == 1
            assert result1 == result2

    @pytest.mark.asyncio
    async def test_discover_oidc_config_refetches_after_ttl(self, jwt_validator):
        """Test that discovery cache is refreshed after TTL expires."""
        discovery_doc_v1 = {"issuer": "https://sso.example.com", "jwks_uri": "https://sso.example.com/jwks-v1"}
        discovery_doc_v2 = {"issuer": "https://sso.example.com", "jwks_uri": "https://sso.example.com/jwks-v2"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = discovery_doc_v1
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            # First call populates cache
            result1 = await jwt_validator._discover_oidc_config()
            assert result1 == discovery_doc_v1

            # Simulate TTL expiry by backdating the cache timestamp
            jwt_validator._discovery_cache_time -= 7200  # 2 hours ago

            # Update mock to return new document
            mock_response.json.return_value = discovery_doc_v2

            # Second call should re-fetch
            result2 = await jwt_validator._discover_oidc_config()
            assert result2 == discovery_doc_v2
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_validate_token_expired(self, jwt_validator):
        """Test that expired tokens return None."""
        # Create a mock signing key
        with patch.object(jwt_validator, "_get_jwks_client") as mock_get_jwks:
            mock_jwks = MagicMock()
            mock_signing_key = MagicMock()
            mock_signing_key.key = "test-key"
            mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_jwks.return_value = mock_jwks

            # Make jwt.decode raise ExpiredSignatureError
            with patch("jwt.decode", side_effect=jwt.ExpiredSignatureError("Token expired")):
                result = await jwt_validator.validate_token("expired.token.here")

            assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_invalid_audience(self, jwt_validator):
        """Test that tokens with invalid audience return None."""
        with patch.object(jwt_validator, "_get_jwks_client") as mock_get_jwks:
            mock_jwks = MagicMock()
            mock_signing_key = MagicMock()
            mock_signing_key.key = "test-key"
            mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_jwks.return_value = mock_jwks

            with patch("jwt.decode", side_effect=jwt.InvalidAudienceError("Invalid audience")):
                result = await jwt_validator.validate_token("invalid.audience.token")

            assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_invalid_issuer(self, jwt_validator):
        """Test that tokens with invalid issuer return None."""
        with patch.object(jwt_validator, "_get_jwks_client") as mock_get_jwks:
            mock_jwks = MagicMock()
            mock_signing_key = MagicMock()
            mock_signing_key.key = "test-key"
            mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_jwks.return_value = mock_jwks

            with patch("jwt.decode", side_effect=jwt.InvalidIssuerError("Invalid issuer")):
                result = await jwt_validator.validate_token("invalid.issuer.token")

            assert result is None

    @pytest.mark.asyncio
    async def test_validate_unsigned_token_rejected_when_disabled(self, jwt_validator):
        """Unsigned JWTs should raise a specific error when disabled."""
        with patch("jwt.get_unverified_header", return_value={"alg": "none"}):
            with pytest.raises(UnsignedJWTRejectedError, match="Unsigned JWTs are not accepted"):
                await jwt_validator.validate_token("unsigned.token.value")

    @pytest.mark.asyncio
    async def test_validate_unsigned_token_expired_when_allowed(self):
        """Unsigned JWTs with expired exp claims return None."""
        config = AuthConfig(
            enabled=True,
            allow_unsigned_jwt=True,
            policy_decision_point_base_url="http://localhost:8181",
            oidc=OIDCConfig(enabled=False),
        )
        validator = JWTValidator(config)
        now = int(time.time())
        token = jwt.encode(
            {
                "sub": "user123",
                "iat": now - 7200,
                "nbf": now - 7200,
                "exp": now - 3600,
            },
            key="",
            algorithm="none",
        )

        result = await validator.validate_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_unsigned_token_success_when_allowed(self):
        """Unsigned JWTs with valid exp claims are accepted when allowed."""
        config = AuthConfig(
            enabled=True,
            allow_unsigned_jwt=True,
            policy_decision_point_base_url="http://localhost:8181",
            oidc=OIDCConfig(enabled=False),
        )
        validator = JWTValidator(config)
        now = int(time.time())
        token = jwt.encode(
            {
                "sub": "user123",
                "email": "user@example.com",
                "groups": ["admin"],
                "scope": "openid profile",
                "iat": now,
                "nbf": now,
                "exp": now + 3600,
            },
            key="",
            algorithm="none",
        )

        result = await validator.validate_token(token)

        assert result is not None
        assert result.subject == "user123"
        assert result.email == "user@example.com"
        assert result.groups == ["admin"]
        assert result.scopes == ["openid", "profile"]

    @pytest.mark.asyncio
    async def test_validate_unsigned_token_future_iat_when_allowed(self):
        """Unsigned JWTs with future iat claims return None."""
        config = AuthConfig(
            enabled=True,
            allow_unsigned_jwt=True,
            policy_decision_point_base_url="http://localhost:8181",
            oidc=OIDCConfig(enabled=False),
        )
        validator = JWTValidator(config)
        now = int(time.time())
        token = jwt.encode(
            {
                "sub": "user123",
                "iat": now + 3600,
                "nbf": now,
                "exp": now + 7200,
            },
            key="",
            algorithm="none",
        )

        result = await validator.validate_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_unsigned_token_future_nbf_when_allowed(self):
        """Unsigned JWTs with future nbf claims return None."""
        config = AuthConfig(
            enabled=True,
            allow_unsigned_jwt=True,
            policy_decision_point_base_url="http://localhost:8181",
            oidc=OIDCConfig(enabled=False),
        )
        validator = JWTValidator(config)
        now = int(time.time())
        token = jwt.encode(
            {
                "sub": "user123",
                "iat": now,
                "nbf": now + 3600,
                "exp": now + 7200,
            },
            key="",
            algorithm="none",
        )

        result = await validator.validate_token(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_success(self, jwt_validator):
        """Test successful token validation."""
        valid_claims = {
            "sub": "user123",
            "email": "user@example.com",
            "groups": ["admin", "users"],
            "scope": "openid profile email",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "aud": "test-audience",
            "iss": "https://sso.example.com",
        }

        with patch.object(jwt_validator, "_get_jwks_client") as mock_get_jwks:
            mock_jwks = MagicMock()
            mock_signing_key = MagicMock()
            mock_signing_key.key = "test-key"
            mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_jwks.return_value = mock_jwks

            with patch("jwt.decode", return_value=valid_claims):
                result = await jwt_validator.validate_token("valid.token.here")

            assert result is not None
            assert result.subject == "user123"
            assert result.email == "user@example.com"
            assert result.groups == ["admin", "users"]
            assert result.scopes == ["openid", "profile", "email"]

    @pytest.mark.asyncio
    async def test_validate_token_with_string_groups(self, jwt_validator):
        """Test token validation with comma-separated groups string."""
        valid_claims = {
            "sub": "user123",
            "groups": "admin,users,developers",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "aud": "test-audience",
            "iss": "https://sso.example.com",
        }

        with patch.object(jwt_validator, "_get_jwks_client") as mock_get_jwks:
            mock_jwks = MagicMock()
            mock_signing_key = MagicMock()
            mock_signing_key.key = "test-key"
            mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_jwks.return_value = mock_jwks

            with patch("jwt.decode", return_value=valid_claims):
                result = await jwt_validator.validate_token("valid.token.here")

            assert result is not None
            assert result.groups == ["admin", "users", "developers"]

    @pytest.mark.asyncio
    async def test_validate_token_with_cognito_groups(self, jwt_validator):
        """Test token validation with AWS Cognito groups claim."""
        valid_claims = {
            "sub": "user123",
            "cognito:groups": ["cognito-admin", "cognito-users"],
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "aud": "test-audience",
            "iss": "https://sso.example.com",
        }

        with patch.object(jwt_validator, "_get_jwks_client") as mock_get_jwks:
            mock_jwks = MagicMock()
            mock_signing_key = MagicMock()
            mock_signing_key.key = "test-key"
            mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_jwks.return_value = mock_jwks

            with patch("jwt.decode", return_value=valid_claims):
                result = await jwt_validator.validate_token("valid.token.here")

            assert result is not None
            # Should fall back to cognito:groups when groups claim is not present
            assert result.groups == ["cognito-admin", "cognito-users"]

    @pytest.mark.asyncio
    async def test_validate_token_skips_audience_when_not_configured(self):
        """Test that audience validation is skipped when audience is not configured."""
        config = OIDCConfig(
            enabled=True,
            issuer="https://sso.example.com",
            client_id="test-client",
            # audience is intentionally left as None
        )
        auth_cfg = AuthConfig(
            enabled=True,
            policy_decision_point_base_url="http://localhost:8181",
            oidc=config,
        )
        validator = JWTValidator(auth_cfg)

        valid_claims = {
            "sub": "user123",
            "email": "user@example.com",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "aud": "some-other-audience",
            "iss": "https://sso.example.com",
        }

        with patch.object(validator, "_get_jwks_client") as mock_get_jwks:
            mock_jwks = MagicMock()
            mock_signing_key = MagicMock()
            mock_signing_key.key = "test-key"
            mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_jwks.return_value = mock_jwks

            with patch("jwt.decode", return_value=valid_claims) as mock_decode:
                result = await validator.validate_token("valid.token.here")

            # Verify audience=None and verify_aud=False were passed
            call_kwargs = mock_decode.call_args
            assert call_kwargs[1]["audience"] is None
            assert call_kwargs[1]["options"]["verify_aud"] is False

        assert result is not None
        assert result.subject == "user123"

    @pytest.mark.asyncio
    async def test_validate_token_validates_audience_when_configured(self):
        """Test that audience is validated when explicitly configured."""
        config = OIDCConfig(
            enabled=True,
            issuer="https://sso.example.com",
            client_id="test-client",
            audience="expected-audience",
        )
        auth_cfg = AuthConfig(
            enabled=True,
            policy_decision_point_base_url="http://localhost:8181",
            oidc=config,
        )
        validator = JWTValidator(auth_cfg)

        valid_claims = {
            "sub": "user123",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "aud": "expected-audience",
            "iss": "https://sso.example.com",
        }

        with patch.object(validator, "_get_jwks_client") as mock_get_jwks:
            mock_jwks = MagicMock()
            mock_signing_key = MagicMock()
            mock_signing_key.key = "test-key"
            mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_get_jwks.return_value = mock_jwks

            with patch("jwt.decode", return_value=valid_claims) as mock_decode:
                result = await validator.validate_token("valid.token.here")

            # Verify audience is passed as a list with the configured value
            call_kwargs = mock_decode.call_args
            assert call_kwargs[1]["audience"] == ["expected-audience"]
            assert "verify_aud" not in call_kwargs[1]["options"]

        assert result is not None
        assert result.subject == "user123"

    @pytest.mark.asyncio
    async def test_validate_token_http_error(self, jwt_validator):
        """Test token validation when JWKS fetch fails."""
        with patch.object(jwt_validator, "_get_jwks_client") as mock_get_jwks:
            mock_get_jwks.side_effect = httpx.HTTPError("Connection failed")

            result = await jwt_validator.validate_token("some.token.here")

            assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_uses_configured_jwks_uri(self, auth_config):
        """Test that configured JWKS URI is used instead of discovery."""
        from nmp.common.auth.jwt import _JWKS_CACHE_LIFESPAN

        auth_config.oidc.jwks_uri = "https://custom.example.com/jwks"
        validator = JWTValidator(auth_config)

        with patch("nmp.common.auth.jwt.PyJWKClient") as mock_jwk_client_class:
            mock_jwks = MagicMock()
            mock_jwk_client_class.return_value = mock_jwks

            await validator._get_jwks_client()

            mock_jwk_client_class.assert_called_once_with(
                "https://custom.example.com/jwks",
                cache_keys=True,
                lifespan=_JWKS_CACHE_LIFESPAN,
            )
